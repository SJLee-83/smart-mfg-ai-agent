"""인덱싱 파이프라인 오케스트레이션: PDF -> chunks -> embeddings -> Chroma.

흐름: load_pages -> parse -> tag -> embed_chunks -> ChromaStore.upsert.
설계 근거: docs/parsing-pipeline.md(파싱), ADR-003(임베딩), ADR-004(Chroma).
"""

from __future__ import annotations

from pathlib import Path

from parsing import load_pages, parse, tag

from .chroma_store import ChromaStore
from .embedder import embed_chunks


def run_indexing(
    pdf_path: str | Path | None = None,
    persist_dir: str | Path = "chroma_db",
) -> dict:
    """PDF를 파싱·임베딩·적재하는 전체 인덱싱 흐름을 실행한다.

    Args:
        pdf_path: 매뉴얼 PDF 경로. None이면 .env의 MANUAL_PDF_PATH.
        persist_dir: Chroma 영속 디렉터리.

    Returns:
        {"chunks": int, "embedded": int, "stored": int, "persist_dir": str}
    """
    print(f"[1/4] PDF 로드: {pdf_path or '(.env MANUAL_PDF_PATH)'}")
    pages = load_pages(Path(pdf_path) if pdf_path else None)
    print(f"      페이지 {len(pages)}개 로드")

    print("[2/4] 파싱 + 메타데이터 태깅")
    chunks = tag(parse(pages))
    print(f"      청크 {len(chunks)}개 생성")

    print(f"[3/4] 임베딩 (gemini-embedding-001, 768d) — 청크 {len(chunks)}개")
    embeddings = embed_chunks(chunks)
    print(f"      임베딩 {len(embeddings)}개 생성")

    print(f"[4/4] Chroma 적재 -> {persist_dir}")
    store = ChromaStore(persist_dir=persist_dir)
    stored = store.upsert(chunks, embeddings)
    print(f"      저장됨: 컬렉션 '{store.collection_name}' 총 {stored}청크")

    return {
        "chunks": len(chunks),
        "embedded": len(embeddings),
        "stored": stored,
        "persist_dir": str(persist_dir),
    }
