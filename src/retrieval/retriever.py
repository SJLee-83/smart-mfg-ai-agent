"""검색(retrieval) — 자연어 쿼리를 임베딩해 Chroma에서 유사 청크를 찾는다.

흐름: query 문자열 -> gemini-embedding-001 벡터화 -> Chroma 유사도 검색 -> list[Chunk].
설계 근거: ADR-003(임베딩), ADR-004(Chroma), docs/parsing-pipeline.md.

쿼리 임베딩은 적재 때와 '동일 경로'(index.embedder.embed_chunks)로 계산한다 —
모델/차원(768d)/task_type 설정이 저장된 문서 벡터와 일치해야 코사인 유사도가
의미를 갖기 때문이다. 별도 임베딩 함수를 두면 config가 어긋날 위험이 있다.
"""

from __future__ import annotations

from pathlib import Path

from index.chroma_store import ChromaStore
from index.embedder import embed_chunks
from parsing import Chunk


class Retriever:
    """Chroma 컬렉션에 대한 의미 기반 검색기."""

    def __init__(self, persist_dir: str | Path = "chroma_db") -> None:
        """영속 디렉터리의 Chroma 컬렉션에 연결한다.

        Args:
            persist_dir: 적재 시 사용한 Chroma 영속 디렉터리.
        """
        self._store = ChromaStore(persist_dir=persist_dir)

    def search(
        self,
        query: str,
        n_results: int = 3,
        error_code: str | None = None,
    ) -> list[Chunk]:
        """쿼리와 가장 유사한 청크를 반환한다.

        Args:
            query: 자연어 검색 질의.
            n_results: 반환할 최대 청크 수.
            error_code: 지정 시 해당 error_code 메타데이터로 필터링(정확 일치).

        Returns:
            유사도 순 Chunk 리스트(최대 n_results개). 일치 결과가 없으면 빈 리스트.
        """
        query_embedding = self._embed_query(query)
        where = {"error_code": error_code} if error_code else None
        result = self._store.query(
            embedding=query_embedding,
            n_results=n_results,
            where=where,
        )
        return self._to_chunks(result)

    @staticmethod
    def _embed_query(query: str) -> list[float]:
        """쿼리를 저장 문서와 동일 임베딩 경로로 벡터화한다(config 정합 보장).

        embed_chunks는 Chunk 리스트를 받으므로 쿼리를 임시 Chunk로 감싼다.
        id/metadata는 임베딩에 쓰이지 않으므로 placeholder로 둔다.
        """
        proxy = Chunk(id="__query__", content=query, metadata={})
        return embed_chunks([proxy])[0]

    @staticmethod
    def _to_chunks(result: dict) -> list[Chunk]:
        """Chroma query 결과(dict)를 Chunk 리스트로 변환한다. 결과 없으면 [].

        Chroma 응답은 쿼리 1건 기준 list-of-lists이므로 각 필드의 [0]을 취한다.
        """
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        return [
            Chunk(id=cid, content=doc, metadata=meta)
            for cid, doc, meta in zip(ids, documents, metadatas)
        ]
