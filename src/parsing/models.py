"""src/parsing 데이터 모델 (stdlib dataclass).

PageText -> RawChunk -> Chunk. 설계: docs/parsing-pipeline.md §1.3/1.4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from . import constants


@dataclass(frozen=True)
class PageText:
    """PDF 한 페이지의 (노이즈 제거된) 텍스트."""

    page_no: int  # 1-based
    text: str


@dataclass
class RawChunk:
    """chunk_parser 출력. 한 SRVO 코드 = 한 RawChunk (결정 B).

    content는 헤더(코드+title)줄을 포함한 전체 블록 = 임베딩 대상 텍스트(앵커링).
    explanation/actions는 추가 구조 필드. 폴백 시 explanation=None, actions=[].
    """

    error_code: str | None  # "SRVO-094" | None
    content: str
    page_no: int  # 코드가 '시작'한 페이지
    title: str | None  # "(N) " 제거한 코드+제목(앵커). 폴백 시 None 가능
    explanation: str | None
    actions: list[str] = field(default_factory=list)
    related_codes: list[str] = field(default_factory=list)  # 블록 내 (SRVO-NNN) 교차참조
    parsed_by: str = "marker"  # "marker" | "fallback"

    def __post_init__(self) -> None:
        if self.error_code is not None and not constants.CODE_RE.fullmatch(self.error_code):
            raise ValueError(f"error_code 형식 오류: {self.error_code!r}")
        if self.parsed_by not in ("marker", "fallback"):
            raise ValueError(f"parsed_by must be 'marker'|'fallback': {self.parsed_by!r}")


class ChunkMetadata(TypedDict):
    """Chunk.metadata 스키마(문서용 — 런타임 강제 아님). 값은 Chroma 스칼라(str/int)."""

    error_code: str
    page_no: int
    title: str
    content_type: str
    severity_hint: str
    parsed_by: str
    related_codes: str  # comma-join, "" if none


@dataclass(frozen=True)
class Chunk:
    """metadata_tagger 출력. Chroma 적재 단위."""

    id: str
    content: str
    metadata: dict  # ChunkMetadata 스키마. 실제 타입은 dict(런타임 유연성).
