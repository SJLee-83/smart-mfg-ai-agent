"""에이전트 파이프라인 — 검색 + 답변 생성 오케스트레이션.

흐름: query -> Retriever.search -> generate_answer -> {answer, sources, query}.
설계 근거: ADR-003/004, docs/parsing-pipeline.md.
"""

from __future__ import annotations

from pathlib import Path

from parsing import Chunk
from retrieval.retriever import Retriever

from .answer_generator import generate_answer


def _to_source(chunk: Chunk) -> dict:
    """청크를 출처 메타데이터(dict)로 변환한다 — error_code/page_no/parsed_by."""
    meta = chunk.metadata
    return {
        "error_code": meta.get("error_code", ""),
        "page_no": meta.get("page_no"),
        "parsed_by": meta.get("parsed_by", ""),
    }


def ask(
    query: str,
    n_results: int = 3,
    error_code: str | None = None,
    *,
    persist_dir: str | Path = "chroma_db",
    retriever: Retriever | None = None,
) -> dict:
    """질문에 대해 검색 후 한국어 답변과 출처를 생성한다.

    Args:
        query: 사용자 질문.
        n_results: 검색할 최대 청크 수.
        error_code: 지정 시 해당 코드 메타데이터로 검색을 필터링.
        persist_dir: Chroma 영속 디렉터리(retriever 미주입 시 사용).
        retriever: 주입용 Retriever(테스트). None이면 persist_dir로 생성.

    Returns:
        {"answer": str, "sources": list[dict], "query": str}.
        sources 각 원소: {"error_code", "page_no", "parsed_by"}.
    """
    retriever = retriever or Retriever(persist_dir=persist_dir)
    chunks = retriever.search(query, n_results=n_results, error_code=error_code)
    answer = generate_answer(query, chunks)
    return {
        "answer": answer,
        "sources": [_to_source(c) for c in chunks],
        "query": query,
    }
