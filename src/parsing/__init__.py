"""R-Mate FANUC 매뉴얼 파싱 파이프라인.

흐름: load_pages -> parse -> tag -> list[Chunk]
(임베딩/Chroma 적재는 별도 모듈). 설계: docs/parsing-pipeline.md
"""

from .chunk_parser import parse
from .metadata_tagger import tag
from .models import Chunk, PageText, RawChunk
from .pdf_loader import load_pages

__all__ = ["PageText", "RawChunk", "Chunk", "load_pages", "parse", "tag"]
