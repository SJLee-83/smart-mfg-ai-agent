"""임베딩 — google-genai 신 SDK로 Chunk.content를 gemini-embedding-001(768d)로 벡터화.

설계 근거: ADR-003, docs/validation/A9-embedding-model-verification.md.
API 키는 .env의 GOOGLE_API_KEY.

배치 크기 주의: gemini-embedding-001 free tier는 큰 배치(예: 93개 한 요청)에 429
RESOURCE_EXHAUSTED를 반환한다(단일/소량 호출은 동작). 그래서 기본 배치를 1로 두고
429에 지수 backoff 재시도 + 배치 간 지연으로 RPM을 완화한다.
비-429(레이트리밋 아님) 오류는 즉시 전파한다(조용히 삼키지 않음).
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator, Sequence

from dotenv import find_dotenv, load_dotenv
from google import genai
from google.genai import types

from parsing import Chunk

MODEL = "gemini-embedding-001"
DEFAULT_DIMENSIONALITY = 768
DEFAULT_BATCH_SIZE = 1  # free tier: 큰 배치는 429 -> 보수적으로 1 (단일 호출은 검증됨)
ENV_KEY = "GOOGLE_API_KEY"

_MAX_RETRIES = 6  # 429 재시도 횟수
_BASE_DELAY = 2.0  # 초, 지수 backoff 시작값
_MAX_DELAY = 32.0  # 초, backoff 상한
_INTER_BATCH_SLEEP = 0.5  # 초, 배치 간 지연(RPM 완화)


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


def _is_rate_limit(exc: Exception) -> bool:
    """429 RESOURCE_EXHAUSTED(레이트리밋/쿼터) 여부."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    text = str(exc)
    return code == 429 or "RESOURCE_EXHAUSTED" in text or "429" in text


def _embed_batch(client: genai.Client, texts: list[str], config) -> list[list[float]]:
    """한 배치 임베딩. 429면 지수 backoff 재시도, 그 외 오류는 즉시 전파."""
    delay = _BASE_DELAY
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.embed_content(model=MODEL, contents=texts, config=config)
            return [list(e.values) for e in response.embeddings]
        except Exception as exc:  # noqa: BLE001 — 429만 재시도, 나머지는 즉시 재전파
            if _is_rate_limit(exc) and attempt < _MAX_RETRIES - 1:
                time.sleep(min(delay, _MAX_DELAY))
                delay *= 2
                continue
            raise
    raise RuntimeError("unreachable")  # 방어 — 루프는 return 또는 raise로 종료


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
        429 재시도 소진 또는 비-429 API 오류는 그대로 전파(조용히 삼키지 않음).
    """
    if not chunks:
        return []

    client = client or _make_client()
    config = types.EmbedContentConfig(output_dimensionality=dimensionality)

    vectors: list[list[float]] = []
    for n, batch in enumerate(_batches(chunks, batch_size)):
        if n > 0:
            time.sleep(_INTER_BATCH_SLEEP)
        texts = [c.content for c in batch]
        batch_vectors = _embed_batch(client, texts, config)
        if len(batch_vectors) != len(batch):
            raise RuntimeError(
                f"임베딩 개수 불일치: 요청 {len(batch)} != 응답 {len(batch_vectors)}"
            )
        vectors.extend(batch_vectors)
    return vectors
