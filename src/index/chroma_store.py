"""Chroma 적재 — 미리 계산된 임베딩과 함께 Chunk를 로컬 PersistentClient에 upsert.

설계 근거: ADR-004(Chroma 로컬 파일 기반), docs/parsing-pipeline.md.
이 스토어는 외부(gemini)에서 계산된 임베딩만 저장하므로 Chroma 내부 임베딩
함수는 호출되지 않는다(호출 시 오류). 메타데이터 값은 Chroma 스칼라(str/int)여야 한다.
"""

from __future__ import annotations

from pathlib import Path

import chromadb

from parsing import Chunk

COLLECTION_NAME = "fanuc_manual"


class _PrecomputedEmbeddingFunction:
    """미리 계산된 임베딩 전용 placeholder — Chroma가 자체 임베딩을 시도하지 않게 한다.

    upsert 시 항상 임베딩을 명시 제공하므로 __call__은 호출되지 않는다.
    (기본 EF의 onnx 모델 다운로드를 피하기 위한 장치 — A7 검증에서 확인된 패턴.)
    """

    @staticmethod
    def name() -> str:
        return "precomputed-external"

    def __call__(self, input):  # chroma EmbeddingFunction 시그니처
        raise NotImplementedError(
            "ChromaStore는 미리 계산된 임베딩만 사용한다 — EF가 호출되면 안 됨."
        )


class ChromaStore:
    """로컬 파일 기반 Chroma 컬렉션 래퍼."""

    collection_name = COLLECTION_NAME

    def __init__(self, persist_dir: str | Path = "chroma_db") -> None:
        """PersistentClient를 생성하고 컬렉션을 확보한다.

        Args:
            persist_dir: Chroma 영속 디렉터리(로컬 파일 기반).
        """
        self.persist_dir = str(persist_dir)
        self._client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=_PrecomputedEmbeddingFunction(),
        )

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> int:
        """청크와 그 임베딩을 적재(upsert)하고 컬렉션의 총 청크 수를 반환한다.

        Args:
            chunks: 적재할 청크.
            embeddings: chunks와 같은 순서·길이의 임베딩 벡터.

        Returns:
            적재 후 컬렉션의 총 청크 수.

        Raises:
            ValueError: chunks와 embeddings 길이 불일치.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks({len(chunks)})와 embeddings({len(embeddings)}) 길이 불일치"
            )
        if chunks:
            self._collection.upsert(
                ids=[c.id for c in chunks],
                embeddings=embeddings,
                documents=[c.content for c in chunks],
                metadatas=[c.metadata for c in chunks],
            )
        return self.count()

    def count(self) -> int:
        """현재 저장된 청크 수."""
        return self._collection.count()
