"""임베딩 — google-genai 신 SDK로 Chunk.content를 gemini-embedding-001(768d)로 벡터화.

설계 근거: ADR-003, docs/validation/A9-embedding-model-verification.md.
API 키는 .env의 GOOGLE_API_KEY. 실패는 조용히 삼키지 않고 예외로 전달한다.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence

from dotenv import find_dotenv, load_dotenv
from google import genai
from google.genai import types

from parsing import Chunk

MODEL = "gemini-embedding-001"
DEFAULT_DIMENSIONALITY = 768
DEFAULT_BATCH_SIZE = 100  # 한 번의 embed_content 호출당 최대 청크 수(API 제한 대비)
ENV_KEY = "GOOGLE_API_KEY"


def _make_client() -> genai.Client:
    """GOOGLE_API_KEY로 google-genai 클라이언트를 생성한다. 키가 없으면 예외."""
    load_dotenv(find_dotenv(usecwd=True))
    api_key = os.getenv(ENV_KEY)
    if not api_key:
        raise EnvironmentError(f"{ENV_KEY} not set in environment (.env)")
    return genai.Client(api_key=api_key)


def _batches(seq: Sequence[Chunk], size: int) -> Iterator[Sequence[Chunk]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def embed_chunks(
    chunks: list[Chunk],
    *,
    client: genai.Client | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dimensionality: int = DEFAULT_DIMENSIONALITY,
) -> list[list[float]]:
    """Chunk 리스트의 content를 임베딩해 벡터 리스트를 반환한다(입력 순서 보존).

    Args:
        chunks: 임베딩 대상. 빈 리스트면 API 호출 없이 빈 리스트 반환.
        client: 주입용 google-genai 클라이언트(테스트). None이면 .env로 생성.
        batch_size: 한 번의 embed_content 호출당 최대 청크 수.
        dimensionality: 출력 차원(gemini-embedding-001의 MRL truncation).

    Returns:
        len(chunks) 길이의 벡터 리스트(각 원소는 list[float]).

    Raises:
        EnvironmentError: GOOGLE_API_KEY 미설정(client 미주입 시).
        RuntimeError: 응답 임베딩 개수가 요청과 불일치.
        google-genai의 API 예외는 그대로 전파(조용히 삼키지 않음).
    """
    if not chunks:
        return []

    client = client or _make_client()
    config = types.EmbedContentConfig(output_dimensionality=dimensionality)

    vectors: list[list[float]] = []
    for batch in _batches(chunks, batch_size):
        texts = [c.content for c in batch]
        response = client.models.embed_content(model=MODEL, contents=texts, config=config)
        batch_vectors = [list(e.values) for e in response.embeddings]
        if len(batch_vectors) != len(batch):
            raise RuntimeError(
                f"임베딩 개수 불일치: 요청 {len(batch)} != 응답 {len(batch_vectors)}"
            )
        vectors.extend(batch_vectors)
    return vectors
