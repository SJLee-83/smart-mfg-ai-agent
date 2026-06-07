"""A6 후속 — 변형 입력 라우팅 견고성 테스트 (experiments PoC, 버려도 됨).

A6 본 측정(run_eval.py)은 '정상 형식' 입력에서 라우팅 정확도 100%를 보였다. 이
스크립트는 그 한계를 직접 찌른다: 소문자/공백/오타/별칭/코드-only/복수코드 같은
**변형 입력**에서 orchestrate의 코드 감지(CODE_RE = SRVO-?\\d{3}, IGNORECASE +
canonical_code 정규화)가 어디서 깨지는지 본다. (검증 기록 §5 후속 과제)

각 케이스마다 ask()를 호출해 retrieval_mode를 관측하고, 기대값과 PASS/FAIL 비교.
검색(임베딩)은 실제 호출, 답변(LLM)은 스텁 — 라우팅만 측정하므로 답변 텍스트 불요.

실행: .venv/Scripts/python.exe experiments/a6_routing_quality/run_robustness_eval.py
출력: 콘솔 + experiments/a6_routing_quality/result_robustness.txt (gitignore: result_*.txt)
"""

from __future__ import annotations

import re
import sys
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

RESULT_PATH = SCRIPT_DIR / "result_robustness.txt"
PERSIST_DIR = ROOT / "chroma_db"

# (카테고리, 입력 질의, 기대 retrieval_mode). 기대값은 '견고하다면 이래야 한다'는
# 목표치 — 현행 규칙이 못 맞히면 FAIL로 드러나는 게 이 테스트의 목적이다.
CASES: list[tuple[str, str, str]] = [
    ("1.소문자", "srvo-062 배터리 알람", "filtered"),
    ("1.소문자", "srvo062 배터리", "filtered"),            # 하이픈 없음
    ("2.오타", "SRVO-06 2 배터리", "unfiltered"),          # 공백 삽입
    ("2.오타", "SRV0-062 배터리", "unfiltered"),           # O→0 오타
    ("3.별칭/증상", "BZAL 알람 해결법", "unfiltered"),      # 코드 없음
    ("3.별칭/증상", "배터리 방전 알람", "unfiltered"),
    ("4.코드만", "SRVO-062", "filtered"),
    ("4.코드만", "SRVO-105", "filtered"),
    ("5.복수코드", "SRVO-062랑 SRVO-105 동시에 떴어", "filtered"),  # 첫 코드 감지
]


class _StubAnswerClient:
    """답변 LLM 스텁 — generate_content만 가로채 고정 문자열 반환(라우팅만 측정)."""

    class _Models:
        @staticmethod
        def generate_content(*args, **kwargs):
            class _Resp:
                text = "(스텁 답변 — 견고성 테스트는 라우팅만 측정)"

            return _Resp()

    models = _Models()


_buffer: list[str] = []


def out(line: str = "") -> None:
    print(line)
    _buffer.append(line)


def detected_code(query: str) -> str | None:
    """orchestrate와 동일하게 CODE_RE로 코드를 추출(진단용). 없으면 None."""
    match = CODE_RE.search(query)
    return match.group(0) if match else None


def run() -> bool:
    retriever = Retriever(persist_dir=str(PERSIST_DIR))
    client = _StubAnswerClient()

    out("=" * 78)
    out("A6 후속 — 변형 입력 라우팅 견고성 테스트")
    out("=" * 78)
    ignorecase = bool(CODE_RE.flags & re.IGNORECASE)
    out(f"CODE_RE = {CODE_RE.pattern!r}  (IGNORECASE={ignorecase}, canonical_code 정규화 적용)")
    out("검색: 실제 Chroma/임베딩 호출 · 답변: 스텁(LLM 미호출)")
    out("")

    records: list[dict] = []
    for category, query, expected in CASES:
        result = ask(query, n_results=3, retriever=retriever, client=client)
        actual = result.get("retrieval_mode", "none")
        passed = actual == expected
        records.append(
            {
                "category": category,
                "query": query,
                "expected": expected,
                "actual": actual,
                "passed": passed,
                "code": detected_code(query),
            }
        )

    out("[케이스별 결과]")
    out("-" * 78)
    for r in records:
        mark = "PASS" if r["passed"] else "FAIL"
        out(f"  [{mark}] {r['category']}")
        out(f"      입력          : {r['query']}")
        out(f"      CODE_RE 감지   : {r['code']}")
        out(f"      기대 mode      : {r['expected']}")
        out(f"      실제 mode      : {r['actual']}")
    out("")

    total = len(records)
    passed = sum(1 for r in records if r["passed"])
    out("=" * 78)
    out(f"[요약] {passed}/{total} PASS")
    fails = [r for r in records if not r["passed"]]
    if fails:
        out("  FAIL 케이스:")
        for r in fails:
            out(f"    - '{r['query']}'  기대={r['expected']} 실제={r['actual']} (감지코드={r['code']})")
    out("=" * 78)

    RESULT_PATH.write_text("\n".join(_buffer) + "\n", encoding="utf-8", errors="replace")
    print(f"\n[저장됨] {RESULT_PATH}")
    return True  # 견고성 노출이 목적 — FAIL이 있어도 측정 자체는 정상 종료


if __name__ == "__main__":
    run()
