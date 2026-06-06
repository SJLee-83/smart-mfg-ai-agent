"""그래프 조립 — build_graph 클로저 팩토리.

설계 근거: docs/langgraph-multiagent.md §2.2, §2.7.

조건부 라우팅 상태 머신: orchestrate -> retrieve -(라우터)-> {answer | clear_filter | not_found}.
clear_filter는 retrieve로 1회 재진입(retried 가드로 무한 루프 불가). 단일 턴이라
체크포인터/메모리 없음. LLM은 answer 노드에서 google-genai 직호출(LangChain 래퍼 미사용).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from retrieval.retriever import Retriever

from .nodes import (
    clear_filter,
    make_answer,
    make_retrieve,
    not_found,
    orchestrate,
    route_after_retrieve,
)
from .state import GraphState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


def build_graph(*, retriever: Retriever | None = None, client=None) -> "CompiledStateGraph":
    """검색→답변 상태 머신을 컴파일해 반환한다.

    Args:
        retriever: 주입용 Retriever(테스트). None이면 기본 chroma_db로 생성.
        client: 주입용 google-genai 클라이언트(테스트). None이면 answer 노드가
            generate_answer 내부에서 .env로 생성.

    Returns:
        컴파일된 LangGraph 런너블. `.invoke({"query": ..., "n_results": ...,
        "effective_code": ...})` 호출 시 최종 상태 dict를 반환.
    """
    _retriever = retriever or Retriever()

    builder = StateGraph(GraphState)
    builder.add_node("orchestrate", orchestrate)
    builder.add_node("retrieve", make_retrieve(_retriever))
    builder.add_node("clear_filter", clear_filter)
    builder.add_node("answer", make_answer(client))
    builder.add_node("not_found", not_found)

    builder.add_edge(START, "orchestrate")
    builder.add_edge("orchestrate", "retrieve")
    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"answer": "answer", "clear_filter": "clear_filter", "not_found": "not_found"},
    )
    builder.add_edge("clear_filter", "retrieve")  # 비필터로 1회 재진입
    builder.add_edge("answer", END)
    builder.add_edge("not_found", END)

    return builder.compile()
