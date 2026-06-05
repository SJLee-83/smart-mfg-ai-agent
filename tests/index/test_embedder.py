"""embedder 테스트 — 실제 API 호출 없이 google.genai.Client를 모킹.

배치 분할, 429 backoff 재시도, 비-429 즉시 전파를 검증한다(time.sleep은 모킹).
"""

from __future__ import annotations

import pytest

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


def _patch_client(monkeypatch, models) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.models = models

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("index.embedder.genai.Client", FakeClient)
    monkeypatch.setattr("index.embedder.time.sleep", lambda *_: None)


def test_empty_returns_empty():
    # 빈 입력은 API 호출 없이 빈 리스트
    assert embed_chunks([]) == []


def test_embeds_with_mocked_client(monkeypatch):
    calls: list[int] = []

    class FakeModels:
        def embed_content(self, model, contents, config):
            calls.append(len(contents))
            return _FakeResponse([_FakeEmbedding([0.1, 0.2, 0.3]) for _ in contents])

    _patch_client(monkeypatch, FakeModels())
    vecs = embed_chunks([_chunk(1), _chunk(2)], batch_size=10)
    assert len(vecs) == 2
    assert vecs[0] == [0.1, 0.2, 0.3]
    assert calls == [2]


def test_batches_in_chunks_of_batch_size(monkeypatch):
    calls: list[int] = []

    class FakeModels:
        def embed_content(self, model, contents, config):
            calls.append(len(contents))
            return _FakeResponse([_FakeEmbedding([1.0]) for _ in contents])

    _patch_client(monkeypatch, FakeModels())
    vecs = embed_chunks([_chunk(i) for i in range(150)], batch_size=100)
    assert len(vecs) == 150
    assert calls == [100, 50]  # 100/50 배치 분할 확인


def test_retries_on_429_then_succeeds(monkeypatch):
    state = {"calls": 0}

    class FakeModels:
        def embed_content(self, model, contents, config):
            state["calls"] += 1
            if state["calls"] == 1:
                raise Exception("429 RESOURCE_EXHAUSTED quota exceeded")
            return _FakeResponse([_FakeEmbedding([0.5]) for _ in contents])

    _patch_client(monkeypatch, FakeModels())
    vecs = embed_chunks([_chunk(1)])
    assert vecs == [[0.5]]
    assert state["calls"] == 2  # 1차 429 -> backoff 후 재시도 성공


def test_non_rate_limit_error_propagates_immediately(monkeypatch):
    class FakeModels:
        def embed_content(self, model, contents, config):
            raise ValueError("bad request (not a rate limit)")

    _patch_client(monkeypatch, FakeModels())
    with pytest.raises(ValueError):
        embed_chunks([_chunk(1)])
