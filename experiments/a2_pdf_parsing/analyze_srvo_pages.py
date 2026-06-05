"""
A2 PDF 파싱 검증 — 추가 측정: SRVO 페이지 심층 분석 (experiments PoC, 버려도 되는 검증용)

explore_pdf_structure.py가 남긴 '미확정 사항' 2개를 49개 SRVO 페이지에서 정량 측정한다:
  [A] (SRVO-NNN) 괄호 역참조(교차참조) 빈도
      → 'Cross-Reference' 가정(코드↔코드 교차참조) 확정/기각 근거
  [B] '(Explanation)' / '(Action)' 마커 일관성
      → 'SRVO 1코드 = 1청크' 청킹 규칙이 일관되게 적용 가능한지 검증

경로는 하드코딩하지 않고 .env의 MANUAL_PDF_PATH에서 읽는다.
실행: python experiments/a2_pdf_parsing/analyze_srvo_pages.py
의존성: pdfplumber, python-dotenv
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv

# Windows 콘솔 기본 인코딩(cp949)에서 한글·특수문자가 깨져 크래시하지 않도록 UTF-8 강제.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]          # experiments/a2_pdf_parsing -> 프로젝트 루트
RESULT_PATH = SCRIPT_DIR / "result_srvo_analysis.txt"

_buffer: list[str] = []


def out(line: str = "") -> None:
    """화면과 결과 파일 버퍼에 동시 기록."""
    print(line)
    _buffer.append(line)


def resolve_pdf_path() -> Path:
    load_dotenv(PROJECT_ROOT / ".env")
    raw = os.getenv("MANUAL_PDF_PATH")
    if not raw:
        out("[ERROR] .env에 MANUAL_PDF_PATH가 정의되어 있지 않다.")
        sys.exit(1)
    p = Path(raw)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    return p


def pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):.1f}%" if total else "N/A"


def main() -> None:
    pdf_path = resolve_pdf_path()

    out("=" * 72)
    out("A2 PDF 파싱 검증 — 추가 측정: SRVO 페이지 심층 분석")
    out("=" * 72)
    out(f"PDF 경로 : {pdf_path}")
    if not pdf_path.exists():
        out(f"[ERROR] PDF가 존재하지 않는다: {pdf_path}")
        sys.exit(1)
    out("")

    code_re = re.compile(r"SRVO-\d{3}")              # 모든 SRVO 코드 언급(괄호 무관)
    xref_re = re.compile(r"\(\s*(SRVO-\d{3})\s*\)")  # 괄호로 묶인 역참조 (SRVO-NNN)
    expl_re = re.compile(r"\(Explanation\)")
    action_re = re.compile(r"\(Action")

    # ---- 1차 스캔: SRVO- 등장 페이지와 그 텍스트 수집 ----
    srvo_pages: list[int] = []
    page_text: dict[int, str] = {}
    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if code_re.search(text):
                srvo_pages.append(i)
                page_text[i] = text

    n = len(srvo_pages)
    out(f"전체 페이지: {total_pages}  /  SRVO- 등장 페이지: {n}")
    out(f"대상 페이지 목록: {srvo_pages}")
    out("")

    # ---- [A] (SRVO-NNN) 괄호 역참조 빈도 ----
    all_mentions: Counter[str] = Counter()   # 모든 SRVO-NNN 언급
    xref_counter: Counter[str] = Counter()   # (SRVO-NNN) 괄호 역참조
    pages_with_xref = 0
    for p in srvo_pages:
        t = page_text[p]
        for m in code_re.findall(t):
            all_mentions[m] += 1
        xrefs = xref_re.findall(t)
        if xrefs:
            pages_with_xref += 1
        for c in xrefs:
            xref_counter[c] += 1

    total_mentions = sum(all_mentions.values())
    total_xref = sum(xref_counter.values())

    out("[A] (SRVO-NNN) 괄호 역참조(교차참조) 빈도")
    out("    측정 패턴: \\(SRVO-\\d{3}\\)  (괄호로 단독 묶인 코드 = 교차참조 신호)")
    out(f"    - SRVO-NNN 전체 언급(괄호 무관): {total_mentions}회, 고유 코드 {len(all_mentions)}개")
    out(f"    - (SRVO-NNN) 괄호 역참조: 총 {total_xref}회")
    out(f"    - 역참조가 가리킨 고유 알람코드: {len(xref_counter)}개")
    out(f"    - 역참조 1회 이상 등장 페이지: {pages_with_xref} / {n} ({pct(pages_with_xref, n)})")
    out("    - 역참조 빈도 상위(코드: 횟수):")
    if xref_counter:
        for code, cnt in xref_counter.most_common(20):
            out(f"        {code}: {cnt}")
    else:
        out("        (괄호 역참조 없음)")
    out("")

    # ---- [B] (Explanation) / (Action) 마커 일관성 ----
    pages_expl = pages_action = pages_both = pages_either = 0
    for p in srvo_pages:
        t = page_text[p]
        has_e = bool(expl_re.search(t))
        has_a = bool(action_re.search(t))
        pages_expl += int(has_e)
        pages_action += int(has_a)
        pages_both += int(has_e and has_a)
        pages_either += int(has_e or has_a)

    out("[B] (Explanation) / (Action) 마커 일관성 (SRVO 페이지 49개 기준)")
    out(f"    - (Explanation) 마커 등장 페이지: {pages_expl} / {n} ({pct(pages_expl, n)})")
    out(f"    - (Action 마커 등장 페이지      : {pages_action} / {n} ({pct(pages_action, n)})")
    out(f"    - 둘 다 등장 페이지             : {pages_both} / {n} ({pct(pages_both, n)})")
    out(f"    - 둘 중 하나라도 등장 페이지     : {pages_either} / {n} ({pct(pages_either, n)})")
    out("")

    out("=" * 72)
    out("분석 완료")
    out("=" * 72)

    RESULT_PATH.write_text("\n".join(_buffer) + "\n", encoding="utf-8", errors="replace")
    print(f"\n[저장됨] 결과 파일: {RESULT_PATH}")


if __name__ == "__main__":
    main()
