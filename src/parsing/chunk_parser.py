"""SRVO 코드 단위 청크 파서 (순수함수, I/O 없음).

페이지들을 연결해 "(N) SRVO-NNN" 정의 헤더를 경계로 코드 블록을 분리하고,
(Explanation)/(Action) 마커로 구조 파싱한다. 마커가 없으면 폴백.
페이지 경계는 청크 경계가 아니다(코드 블록은 다음 정의 헤더까지 통째 유지).
설계: docs/parsing-pipeline.md §2.2/2.5/2.6.
"""

from __future__ import annotations

from bisect import bisect_right

from . import constants
from .models import PageText, RawChunk


def parse(pages: list[PageText]) -> list[RawChunk]:
    """페이지 리스트 -> RawChunk 리스트. 코드가 없으면 빈 리스트."""
    if not pages:
        return []

    full, starts, page_nos = _concatenate(pages)
    headers = list(constants.DEF_HEADER_RE.finditer(full))

    chunks: list[RawChunk] = []
    for i, h in enumerate(headers):
        start = h.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(full)
        block = full[start:end].strip()
        page_no = _page_of(start, starts, page_nos)
        code = h.group("code")
        title = f"{code}{h.group('rest')}".strip()
        chunks.append(_build_chunk(code, title, block, page_no))
    return chunks


def _concatenate(pages: list[PageText]) -> tuple[str, list[int], list[int]]:
    """페이지를 줄바꿈으로 연결하고 페이지 시작 오프셋을 추적한다.

    각 페이지 텍스트에 strip_noise를 한 번 더 적용(로더가 이미 했어도 멱등·안전).
    반환: (연결 텍스트, 각 페이지 char 시작오프셋, 페이지번호).
    """
    parts: list[str] = []
    starts: list[int] = []
    page_nos: list[int] = []
    cursor = 0
    sep = "\n"
    for p in pages:
        text = constants.strip_noise(p.text)
        starts.append(cursor)
        page_nos.append(p.page_no)
        parts.append(text)
        cursor += len(text) + len(sep)
    return sep.join(parts), starts, page_nos


def _page_of(char_index: int, starts: list[int], page_nos: list[int]) -> int:
    """char_index가 속한 페이지 번호(시작 오프셋 이진탐색) = 코드 시작 페이지."""
    idx = bisect_right(starts, char_index) - 1
    idx = max(0, min(idx, len(page_nos) - 1))
    return page_nos[idx]


def _build_chunk(code: str, title: str, block: str, page_no: int) -> RawChunk:
    explanation = _extract_explanation(block)
    actions = _extract_actions(block)
    related = _extract_related_codes(block, own_code=code)
    parsed_by = "marker" if (explanation is not None or actions) else "fallback"
    return RawChunk(
        error_code=code,
        content=block,
        page_no=page_no,
        title=title,
        explanation=explanation,
        actions=actions,
        related_codes=related,
        parsed_by=parsed_by,
    )


def _extract_explanation(block: str) -> str | None:
    m = constants.EXPLANATION_RE.search(block)
    if not m:
        return None
    seg = block[m.end() : _next_marker_start(block, m.end())].strip()
    return seg or None


def _extract_actions(block: str) -> list[str]:
    actions: list[str] = []
    for m in constants.ACTION_RE.finditer(block):
        seg = block[m.end() : _next_marker_start(block, m.end())].strip()
        if seg:
            actions.append(seg)
    return actions


def _next_marker_start(block: str, after: int) -> int:
    """after 이후 첫 (Explanation)/(Action) 마커 시작 위치. 없으면 len(block)."""
    candidates: list[int] = []
    me = constants.EXPLANATION_RE.search(block, after)
    if me:
        candidates.append(me.start())
    ma = constants.ACTION_RE.search(block, after)
    if ma:
        candidates.append(ma.start())
    return min(candidates) if candidates else len(block)


def _extract_related_codes(block: str, own_code: str) -> list[str]:
    """블록 내 괄호 교차참조 (SRVO-NNN) 추출. 자기코드 제외, 첫등장 순서·중복제거."""
    seen: list[str] = []
    for m in constants.XREF_RE.finditer(block):
        code = m.group(1)
        if code != own_code and code not in seen:
            seen.append(code)
    return seen
