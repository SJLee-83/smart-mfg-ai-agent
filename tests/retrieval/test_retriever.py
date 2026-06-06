"""retriever 테스트 — ChromaStore와 embedder(embed_chunks)를 모킹.

실제 API/Chroma 없이 search()의 동작을 검증한다:
쿼리 텍스트가 임베딩으로 전달되는지, error_code 필터가 where로 넘어가는지,
Chroma 결과가 Chunk로 매핑되는지, 빈 결과가 []로 처리되는지.
"""

from __future__ import annotations

import pytest

from parsing import Chunk
from retrieval.retriever import Retriever


class _FakeStore:
    """ChromaStore 대역 — query 호출 인자를 기록하고 미리 정한 결과를 반환한다."""

    def __init__(self, result: dict) -> None:
        self._result = result
        self.calls: list[dict] = []

    def query(self, embedding, n_results=3, where=None):
        self.calls.append({"embedding": embedding, "n_results": n_results, "where": where})
        return self._result


def _chroma_result(chunks: list[Chunk]) -> dict:
    """Chroma query 응답 형태(쿼리 1건 기준 list-of-lists)로 포장."""
    return {
        "ids": [[c.id for c in chunks]],
        "documents": [[c.content for c in chunks]],
        "metadatas": [[c.metadata for c in chunks]],
        "distances": [[0.1 * (i + 1) for i in range(len(chunks))]],
    }


def _build(monkeypatch, result: dict):
    """embed_chunks와 ChromaStore를 모킹하고 (Retriever, FakeStore, captured)를 반환.

    ChromaStore 패치는 Retriever() 생성 전에 적용돼야 주입된 FakeStore가 쓰인다.
    """
    captured: dict = {}

    def fake_embed_chunks(chunks, **kwargs):
        captured["text"] = chunks[0].content  # 쿼리 텍스트 기록
        return [[0.42] * 768]

    store = _FakeStore(result)
    monkeypatch.setattr("retrieval.retriever.embed_chunks", fake_embed_chunks)
    monkeypatch.setattr("retrieval.retriever.ChromaStore", lambda *a, **k: store)
    return Retriever(persist_dir="unused"), store, captured


def test_search_returns_chunks_in_order(monkeypatch):
    expected = [
        Chunk(
            id="SRVO-062_120",
            content="SRVO-062 BLAL alarm battery low",
            metadata={"error_code": "SRVO-062", "page_no": 120},
        ),
        Chunk(
            id="SRVO-001_058",
            content="SRVO-001 Operator panel E-stop",
            metadata={"error_code": "SRVO-001", "page_no": 58},
        ),
    ]
    retriever, store, captured = _build(monkeypatch, _chroma_result(expected))

    results = retriever.search("battery alarm", n_results=2)

    assert [c.id for c in results] == ["SRVO-062_120", "SRVO-001_058"]
    assert results[0].content.startswith("SRVO-062")
    assert results[0].metadata["error_code"] == "SRVO-062"
    # 쿼리 텍스트가 임베딩 경로로 전달됐는지
    assert captured["text"] == "battery alarm"
    # n_results 전달, error_code 미지정 시 필터 없음
    assert store.calls[0]["n_results"] == 2
    assert store.calls[0]["where"] is None
    # 임베딩 벡터가 store.query로 전달됐는지
    assert store.calls[0]["embedding"] == [0.42] * 768


def test_search_applies_error_code_filter(monkeypatch):
    retriever, store, _ = _build(monkeypatch, _chroma_result([]))

    retriever.search("battery", error_code="SRVO-062")

    assert store.calls[0]["where"] == {"error_code": "SRVO-062"}


def test_search_uses_default_n_results(monkeypatch):
    retriever, store, _ = _build(monkeypatch, _chroma_result([]))

    retriever.search("anything")

    assert store.calls[0]["n_results"] == 3  # 기본값


def test_search_handles_empty_results(monkeypatch):
    retriever, store, _ = _build(monkeypatch, _chroma_result([]))

    results = retriever.search("nonexistent code")

    assert results == []
