"""
A2 PDF 파싱 검증 — FANUC 매뉴얼 PDF 구조 탐색 (experiments PoC, 버려도 되는 검증용 코드)

목적: 본 구현(src/) 전에 실제 PDF가 어떤 구조인지 육안/정량으로 파악한다.
  [1] 전체 페이지 수
  [2] 'TROUBLESHOOTING' / 'SRVO-' 키워드 최초 등장 페이지
  [3] SRVO- 등장 페이지 샘플 3개의 raw 텍스트 전체 + 테이블 유무(extract_tables)
  [4] 'See Section' 교차참조 패턴 등장 횟수

경로는 하드코딩하지 않고 .env의 MANUAL_PDF_PATH에서 읽는다.
실행(의존성 설치된 환경에서):
    python experiments/a2_pdf_parsing/explore_pdf_structure.py
의존성: pdfplumber, python-dotenv
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv

# Windows 콘솔 기본 인코딩(cp949)에서 한글·em-dash(—) 등이 깨져 크래시하지 않도록 UTF-8 강제.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]          # experiments/a2_pdf_parsing -> 프로젝트 루트
RESULT_PATH = SCRIPT_DIR / "result_explore.txt"

_buffer: list[str] = []


def out(line: str = "") -> None:
    """화면과 결과 파일 버퍼에 동시 기록."""
    print(line)
    _buffer.append(line)


def resolve_pdf_path() -> Path:
    """.env의 MANUAL_PDF_PATH를 읽어 절대경로로 해석한다(상대경로는 프로젝트 루트 기준)."""
    load_dotenv(PROJECT_ROOT / ".env")
    raw = os.getenv("MANUAL_PDF_PATH")
    if not raw:
        out("[ERROR] .env에 MANUAL_PDF_PATH가 정의되어 있지 않다.")
        sys.exit(1)
    p = Path(raw)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    return p


def pick_samples(pages: list[int], n: int) -> list[int]:
    """리스트에서 앞/중간/뒤로 골고루 n개를 고른다(반올림 충돌 시 중복 제거)."""
    if len(pages) <= n:
        return list(pages)
    idxs = [round(k * (len(pages) - 1) / (n - 1)) for k in range(n)]
    seen: set[int] = set()
    picked: list[int] = []
    for i in idxs:
        if i not in seen:
            seen.add(i)
            picked.append(pages[i])
    return picked


def main() -> None:
    pdf_path = resolve_pdf_path()

    out("=" * 72)
    out("A2 PDF 파싱 검증 — FANUC 매뉴얼 구조 탐색")
    out("=" * 72)
    out(f"PDF 경로 : {pdf_path}")
    if not pdf_path.exists():
        out(f"[ERROR] PDF가 존재하지 않는다: {pdf_path}")
        sys.exit(1)
    out(f"파일 크기: {pdf_path.stat().st_size / 1024 / 1024:.2f} MB")
    out("")

    srvo_re = re.compile(r"SRVO-")
    trouble_re = re.compile(r"TROUBLESHOOTING")
    see_exact_re = re.compile(r"See Section")
    see_ci_re = re.compile(r"see section", re.IGNORECASE)

    first_trouble: int | None = None
    first_srvo: int | None = None
    srvo_pages: list[int] = []
    see_exact = 0
    see_ci = 0

    with pdfplumber.open(str(pdf_path)) as pdf:
        total = len(pdf.pages)

        # ---- 전체 1차 스캔: 페이지별 텍스트로 키워드 위치/카운트 수집 ----
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if first_trouble is None and trouble_re.search(text):
                first_trouble = i
            if srvo_re.search(text):
                if first_srvo is None:
                    first_srvo = i
                srvo_pages.append(i)
            see_exact += len(see_exact_re.findall(text))
            see_ci += len(see_ci_re.findall(text))

        # [1] 전체 페이지 수
        out(f"[1] 전체 페이지 수: {total}")
        out("")

        # [2] 키워드 최초 등장 페이지
        out("[2] 키워드 최초 등장 페이지")
        out(f"    - 'TROUBLESHOOTING' 최초 등장 페이지: {first_trouble or '미발견'}")
        out(f"    - 'SRVO-' 최초 등장 페이지         : {first_srvo or '미발견'}")
        out(f"    - 'SRVO-' 등장 페이지 총 개수       : {len(srvo_pages)}")
        out("")

        # [4] 'See Section' 교차참조 패턴 등장 횟수 (전체 문서)
        out("[4] 'See Section' 교차참조 패턴 등장 횟수(전체 문서)")
        out(f"    - 대소문자 정확히 'See Section': {see_exact}")
        out(f"    - 대소문자 무시 'see section'  : {see_ci}")
        out("")

        # [3] SRVO- 페이지 샘플 3개 (raw 텍스트 전체 + 테이블 유무)
        #     ※ raw 텍스트는 양이 많아 가독성을 위해 결과 파일 끝부분에 배치
        out("[3] SRVO- 등장 페이지 샘플 (raw 텍스트 전체 + 테이블 유무)")
        if not srvo_pages:
            out("    SRVO- 등장 페이지가 없어 샘플 출력 불가.")
        else:
            samples = pick_samples(srvo_pages, 3)
            out(f"    선택된 샘플 페이지: {samples} "
                f"(전체 SRVO- 페이지 {len(srvo_pages)}개 중 앞/중간/뒤)")
            for pno in samples:
                page = pdf.pages[pno - 1]
                text = page.extract_text() or ""
                tables = page.extract_tables()
                out("")
                out("-" * 72)
                out(f"### 샘플 페이지 {pno} ###")
                out(f"테이블 개수(extract_tables): {len(tables)}")
                for ti, tbl in enumerate(tables):
                    rows = len(tbl)
                    cols = max((len(r) for r in tbl), default=0)
                    out(f"  - 테이블 {ti}: {rows} 행 x 최대 {cols} 열")
                out("--- raw 텍스트 시작 -------------------------------------")
                out(text if text.strip()
                    else "(추출된 텍스트 없음 — 이미지/스캔 페이지 가능성)")
                out("--- raw 텍스트 끝 ---------------------------------------")

    out("")
    out("=" * 72)
    out("탐색 완료")
    out("=" * 72)

    RESULT_PATH.write_text("\n".join(_buffer) + "\n", encoding="utf-8", errors="replace")
    print(f"\n[저장됨] 결과 파일: {RESULT_PATH}")


if __name__ == "__main__":
    main()
