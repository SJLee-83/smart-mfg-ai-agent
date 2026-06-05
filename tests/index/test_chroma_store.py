"""chroma_store 테스트 — 실제 Chroma(tmp_path 임시 디렉터리), upsert/count."""

from __future__ import annotations

import pytest

from index.chroma_store import ChromaStore
from parsing import Chunk


def _chunk(i: int) -> Chunk:
    return Chunk(
        id=f"SRVO-{i:03d}_001",
        content=f"SRVO-{i:03d} dummy alarm content",
        metadata={"error_code": f"SRVO-{i:03d}", "page_no": 1, "content_type": "TROUBLESHOOTING"},
    )


def _emb(v: float) -> list[float]:
    return [v] * 768


def test_upsert_returns_count_and_persists(tmp_path):
    store = ChromaStore(persist_dir=tmp_path / "db")
    chunks = [_chunk(1), _chunk(2), _chunk(3)]
    embeddings = [_emb(0.1), _emb(0.2), _emb(0.3)]
    stored = store.upsert(chunks, embeddings)
    assert stored == 3
    assert store.count() == 3


def test_upsert_is_idempotent_on_same_id(tmp_path):
    store = ChromaStore(persist_dir=tmp_path / "db")
    store.upsert([_chunk(1)], [_emb(0.1)])
    store.upsert([_chunk(1)], [_emb(0.9)])  # 같은 id -> 갱신, 중복 아님
    assert store.count() == 1


def test_upsert_length_mismatch_raises(tmp_path):
    store = ChromaStore(persist_dir=tmp_path / "db")
    with pytest.raises(ValueError):
        store.upsert([_chunk(1)], [_emb(0.1), _emb(0.2)])
