"""에이전트 파이프라인 — 검색 + 답변 생성 오케스트레이션.

ask()는 src/graph의 조건부 라우팅 상태 머신(orchestrate→retrieve→answer/재시도/
not_found)을 호출하는 thin wrapper다. 출처(sources)와 답변은 그래프 최종 상태에서
읽는다. 설계: docs/langgraph-multiagent.md.
"""

from __future__ import annotations

from pathlib import Path

from graph import build_graph
from retrieval.retriever import Retriever


def ask(
    query: str,
    n_results: int = 3,
    error_code: str | None = None,
    *,
    persist_dir: str | Path = "chroma_db",
    retriever: Retriever | None = None,
    client=None,
) -> dict:
    """질문에 대해 검색 후 한국어 답변과 출처를 생성한다.

    내부적으로 조건부 라우팅 상태 머신을 실행한다: 에러코드 유무에 따른 필터/비필터
    검색, 검색 0건 시 조기 종료, 필터 검색 0건 시 1회 비필터 재검색.

    Args:
        query: 사용자 질문. **error_code가 None이어도 query 텍스트에서 SRVO 코드가
            추출되면 해당 코드로 필터링된 검색을 수행한다**(자동 필터).
        n_results: 검색할 최대 청크 수.
        error_code: 지정 시 해당 코드 메타데이터로 검색 필터링(query 추출보다 우선).
        persist_dir: Chroma 영속 디렉터리(retriever 미주입 시 사용).
        retriever: 주입용 Retriever(테스트). None이면 persist_dir로 생성.
        client: 주입용 google-genai 클라이언트(테스트). None이면 답변 노드가 .env로 생성.

    Returns:
        {"answer": str, "sources": list[dict], "query": str, "retrieval_mode": str}.
        sources 각 원소: {"error_code", "page_no", "parsed_by"}.
        retrieval_mode: "filtered" | "unfiltered" | "unfiltered_fallback" | "none".
        ("unfiltered_fallback"은 필터 검색 0건으로 필터를 풀고 얻은 결과 — 요청 코드
        일치가 보장되지 않으므로 호출자가 출처의 error_code로 교차확인할 것.)
    """
    graph = build_graph(retriever=retriever or Retriever(persist_dir=persist_dir), client=client)
    final = graph.invoke(
        {"query": query, "n_results": n_results, "effective_code": error_code}
    )
    return {
        "answer": final["answer"],
        "sources": final["sources"],
        "query": query,
        "retrieval_mode": final.get("retrieval_mode", "none"),
    }
