"""embedder 테스트 — 실제 API 호출 없이 google.genai.Client를 모킹."""

from __future__ import annotations

from index.embedder import embed_chunks
from parsing import Chunk


def _chunk(i: int) -> Chunk:
    return Chunk(id=f"c{i}", content=f"content {i}", metadata={})


class _FakeEmbedding:
    def __init__(self, values: list[float]) -> None:
        self.values = values


class _FakeResponse:
    def __init__(self, embeddings: list[_FakeEmbedding]) -> None:
        self.embeddings = embeddings


def test_empty_returns_empty():
    # 빈 입력은 API 호출 없이 빈 리스트
    assert embed_chunks([]) == []


def test_embeds_with_mocked_client(monkeypatch):
    calls: list[int] = []

    class FakeModels:
        def embed_content(self, model, contents, config):
            calls.append(len(contents))
            return _FakeResponse([_FakeEmbedding([0.1, 0.2, 0.3]) for _ in contents])

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.models = FakeModels()

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("index.embedder.genai.Client", FakeClient)

    vecs = embed_chunks([_chunk(1), _chunk(2)])
    assert len(vecs) == 2
    assert vecs[0] == [0.1, 0.2, 0.3]
    assert calls == [2]


def test_batches_in_chunks_of_batch_size(monkeypatch):
    calls: list[int] = []

    class FakeModels:
        def embed_content(self, model, contents, config):
            calls.append(len(contents))
            return _FakeResponse([_FakeEmbedding([1.0]) for _ in contents])

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.models = FakeModels()

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("index.embedder.genai.Client", FakeClient)

    chunks = [_chunk(i) for i in range(150)]
    vecs = embed_chunks(chunks, batch_size=100)
    assert len(vecs) == 150
    assert calls == [100, 50]  # 100/50 배치 분할 확인
