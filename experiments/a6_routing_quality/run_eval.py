"""A6 검증 — 라우팅 정확도 & 비필터 재시도 오답률 실측 (experiments PoC, 버려도 됨).

EXPERIMENT_PLAN.md의 25질의 테스트셋(dataset.jsonl)을 agent.pipeline.ask()로
실행해 두 메트릭을 측정한다(설계: EXPERIMENT_PLAN.md §3):

  M1 라우팅 정확도 — 질의가 기대한 가지(retrieval_mode)로 라우팅된 비율.
  M2 재시도 오답률 — retrieval_mode == "unfiltered_fallback"인 질의 중, sources의
     error_code가 질의의 요청 코드(CODE_RE 추출)와 (어느 것도) 일치하지 않는 비율.

측정 범위(정직 고지):
  - 검색(쿼리 임베딩 + Chroma)은 **실제로 호출**한다 — 라우팅·출처가 실데이터에
    의존하므로 측정의 핵심이다.
  - 답변 생성(LLM)은 **스텁으로 대체**한다. M1/M2는 retrieval_mode와 sources만
    보고 답변 텍스트와 무관하므로, 25회 LLM 호출은 측정에 기여하지 않고 비용·
    네트워크 변동만 늘린다. ask()의 client 주입 훅(테스트용 설계)을 사용한다.

실행: .venv/Scripts/python.exe experiments/a6_routing_quality/run_eval.py
출력: 콘솔 + experiments/a6_routing_quality/result_eval.txt (gitignore: result_*.txt)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# Windows 콘솔 기본 인코딩(cp949)에서 한글이 깨져 크래시하지 않도록 UTF-8 강제.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import find_dotenv, load_dotenv  # noqa: E402

from agent.pipeline import ask  # noqa: E402
from parsing.constants import CODE_RE  # noqa: E402
from retrieval.retriever import Retriever  # noqa: E402

load_dotenv(find_dotenv(usecwd=True))

DATASET_PATH = SCRIPT_DIR / "dataset.jsonl"
RESULT_PATH = SCRIPT_DIR / "result_eval.txt"
PERSIST_DIR = ROOT / "chroma_db"


class _StubAnswerClient:
    """답변 LLM 스텁 — generate_content만 가로채 고정 문자열을 돌려준다.

    M1/M2는 retrieval_mode·sources만 측정하므로 답변 텍스트는 불필요하다. 검색
    임베딩은 실제 호출되며, 이 스텁은 answer 노드(LLM)만 무력화한다.
    """

    class _Models:
        @staticmethod
        def generate_content(*args, **kwargs):
            class _Resp:
                text = "(스텁 답변 — A6 라우팅 실험은 답변 텍스트를 측정하지 않음)"

            return _Resp()

    models = _Models()


_buffer: list[str] = []


def out(line: str = "") -> None:
    print(line)
    _buffer.append(line)


def load_dataset(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def requested_code(query: str) -> str | None:
    """질의 텍스트에서 SRVO 코드를 추출(M2의 '요청 코드'). 없으면 None."""
    match = CODE_RE.search(query)
    return match.group(0) if match else None


def run() -> bool:
    rows = load_dataset(DATASET_PATH)
    retriever = Retriever(persist_dir=str(PERSIST_DIR))
    client = _StubAnswerClient()

    records: list[dict] = []
    for row in rows:
        result = ask(
            row["query"],
            n_results=row.get("n_results", 3),
            retriever=retriever,
            client=client,
        )
        observed = result.get("retrieval_mode", "none")
        source_codes = [s.get("error_code", "") for s in result.get("sources", [])]
        records.append(
            {
                "id": row["id"],
                "group": row["group"],
                "query": row["query"],
                "expected_modes": row["expected_modes"],
                "observed_mode": observed,
                "source_codes": source_codes,
                "req_code": requested_code(row["query"]),
                "correct": observed in row["expected_modes"],
            }
        )

    out("=" * 78)
    out("A6 실측 — 라우팅 정확도(M1) & 비필터 재시도 오답률(M2)")
    out("=" * 78)
    out(f"테스트셋: {DATASET_PATH.name} (총 {len(records)}질의)")
    out(f"검색: 실제 Chroma/임베딩 호출 · 답변: 스텁(LLM 미호출)")
    out("")

    # --- 질의별 상세 ---
    out("[질의별 결과]  (✓ 기대 가지 적중 / ✗ 불일치)")
    out("-" * 78)
    for r in records:
        mark = "✓" if r["correct"] else "✗"
        exp = "|".join(r["expected_modes"])
        out(f"  {mark} {r['id']} [{r['group']:9}] obs={r['observed_mode']:20} exp={exp}")
        out(f"      Q: {r['query']}")
        out(f"      sources.error_code={r['source_codes']}  req_code={r['req_code']}")
    out("")

    # --- M1 라우팅 정확도 ---
    total = len(records)
    correct = sum(1 for r in records if r["correct"])
    out("=" * 78)
    out("[M1] 라우팅 정확도")
    out("-" * 78)
    out(f"  전체: {correct}/{total} = {correct / total:.1%}")
    for group in ("A_code", "B_nocode", "C_miss"):
        g = [r for r in records if r["group"] == group]
        gc = sum(1 for r in g if r["correct"])
        out(f"  {group:9}: {gc}/{len(g)} = {gc / len(g):.1%}")
    # 관측된 라우팅 모드 분포
    dist = Counter(r["observed_mode"] for r in records)
    out(f"  관측 모드 분포: {dict(dist)}")
    out("")

    # --- M2 재시도 오답률 ---
    fallback = [r for r in records if r["observed_mode"] == "unfiltered_fallback"]
    wrong = [r for r in fallback if r["req_code"] not in r["source_codes"]]
    out("=" * 78)
    out("[M2] 재시도(unfiltered_fallback) 오답률 — 출처 코드 ≠ 요청 코드 비율")
    out("-" * 78)
    out(f"  fallback 경로 진입: {len(fallback)}건")
    if fallback:
        out(f"  출처 코드 불일치: {len(wrong)}/{len(fallback)} = {len(wrong) / len(fallback):.1%}")
        for r in fallback:
            flag = "불일치" if r in wrong else "일치"
            out(f"    - {r['id']} req={r['req_code']} sources={r['source_codes']} → {flag}")
    else:
        out("  fallback 경로로 라우팅된 질의 없음 (측정 불가).")
    out("")
    out("  주의: M2는 '출처 코드 불일치'를 프록시로 쓰는 자동 측정값이다. 이 테스트셋의")
    out("  fallback은 전부 '인덱스에 없는 코드' 질의(그룹 C)에서만 발생하므로, 출처가")
    out("  요청 코드와 일치하는 것은 구조적으로 불가능하다(=오답률 100%는 정의상 결과).")
    out("  자세한 해석은 docs/validation/A6-routing-quality-eval.md 참조.")
    out("")
    out("=" * 78)

    RESULT_PATH.write_text("\n".join(_buffer) + "\n", encoding="utf-8", errors="replace")
    print(f"\n[저장됨] {RESULT_PATH}")
    return correct == total or True  # 측정 자체가 목적 — 정확도 미달도 정상 종료


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
