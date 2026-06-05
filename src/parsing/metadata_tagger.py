"""메타데이터 태거 (순수함수). RawChunk -> Chunk(Chroma 적재 단위).

ID = f"{error_code}_{page_no:03d}", 충돌 시 "_{ordinal:02d}" 지연 가드.
메타데이터 값은 전부 Chroma 스칼라(str/int). 설계: docs/parsing-pipeline.md §2.7.
"""

from __future__ import annotations

from . import constants
from .models import Chunk, RawChunk


def tag(chunks: list[RawChunk]) -> list[Chunk]:
    """RawChunk 리스트에 ID·메타데이터를 부여해 Chunk 리스트로 변환한다."""
    seen: dict[str, int] = {}
    result: list[Chunk] = []
    for raw in chunks:
        result.append(
            Chunk(id=_make_id(raw, seen), content=raw.content, metadata=_make_metadata(raw))
        )
    return result


def _make_id(raw: RawChunk, seen: dict[str, int]) -> str:
    """결정적 ID. 같은 (코드,페이지)가 2회 이상이면 ordinal 접미(가정: 정상은 1회)."""
    code = raw.error_code or "NOCODE"
    base = f"{code}_{raw.page_no:03d}"
    count = seen.get(base, 0)
    seen[base] = count + 1
    return base if count == 0 else f"{base}_{count:02d}"


def _make_metadata(raw: RawChunk) -> dict:
    return {
        "error_code": raw.error_code or "",
        "page_no": raw.page_no,
        "title": raw.title or "",
        "content_type": constants.CONTENT_TYPE_TROUBLESHOOTING,
        "severity_hint": constants.detect_severity_hint(raw.content),
        "parsed_by": raw.parsed_by,
        "related_codes": ",".join(raw.related_codes),
    }
