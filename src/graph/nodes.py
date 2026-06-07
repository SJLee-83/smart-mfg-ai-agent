"""그래프 노드와 라우터 — 기존 검색/생성 로직을 재작성 없이 감싼다.

설계 근거: docs/langgraph-multiagent.md §2.1, §2.4, §3.

노드는 (state) -> 부분 상태 delta. retrieve/answer만 주입 의존성(retriever/client)을
쓰며, 이를 위해 클로저 팩토리(make_retrieve/make_answer)를 둔다. orchestrate/
clear_filter/not_found/route_after_retrieve는 순수 함수다.

규칙 기반 라우팅이다(정규식 + 0건 판정). LLM 호출은 answer 노드 1곳뿐.
"""

from __future__ import annotations

from collections.abc import Callable

from agent.answer_generator import NO_CONTEXT_MESSAGE, generate_answer
from parsing import Chunk
from parsing.constants import CODE_RE, canonical_code

from .state import GraphState

DEFAULT_N_RESULTS = 3


def _to_source(chunk: Chunk) -> dict:
    """청크를 출처 메타데이터(dict)로 변환한다 — error_code/page_no/parsed_by.

    agent.pipeline._to_source와 동일 로직을 의도적으로 복제한다. graph가 agent를
    import하면 역방향 의존이 되기 때문(설계 §2.8). ask() 통합 시 단일화 검토.
    """
    meta = chunk.metadata
    return {
        "error_code": meta.get("error_code", ""),
        "page_no": meta.get("page_no"),
        "parsed_by": meta.get("parsed_by", ""),
    }


def orchestrate(state: GraphState) -> dict:
    """질의에서 에러코드를 도출하고 재시도 가드를 초기화한다(규칙 기반, LLM 없음).

    effective_code가 이미 있으면(caller override) 그대로 두고, 없을 때만
    CODE_RE로 query에서 추출한다. 추출한 코드는 canonical_code로 정규형(대문자·
    하이픈)으로 변환해야 메타데이터 필터가 빗나가지 않는다('srvo-062'→'SRVO-062').
    """
    code = state.get("effective_code")
    if not code:
        match = CODE_RE.search(state["query"])
        code = canonical_code(match.group(0)) if match else None
    return {"effective_code": code, "retried": False}


def make_retrieve(retriever) -> Callable[[GraphState], dict]:
    """주입된 retriever를 클로저로 잡아 retrieve 노드를 생성한다."""

    def retrieve(state: GraphState) -> dict:
        code = state.get("effective_code")
        chunks = retriever.search(
            state["query"],
            state.get("n_results", DEFAULT_N_RESULTS),
            error_code=code,
        )
        # retrieval_mode: retried를 '먼저' 본다(설계 §2.4). clear_filter가
        # effective_code=None·retried=True를 동시에 쓰므로, effective_code를 먼저
        # 보면 fallback이 plain unfiltered로 오라벨되어 위험 신호가 사라진다.
        if state.get("retried"):
            mode = "unfiltered_fallback"
        elif code:
            mode = "filtered"
        else:
            mode = "unfiltered"
        return {"chunks": chunks, "retrieval_mode": mode}

    return retrieve


def clear_filter(state: GraphState) -> dict:
    """필터를 풀고 재시도 가드를 세운다(순수 상태쓰기). 재시도 최대 1회 보장."""
    return {"effective_code": None, "retried": True}


def make_answer(client) -> Callable[[GraphState], dict]:
    """주입된 client를 클로저로 잡아 answer 노드를 생성한다."""

    def answer(state: GraphState) -> dict:
        text = generate_answer(state["query"], state["chunks"], client=client)
        sources = [_to_source(c) for c in state["chunks"]]
        return {"answer": text, "sources": sources, "status": "answered"}

    return answer


def not_found(state: GraphState) -> dict:
    """검색 결과가 없을 때의 종단 노드(LLM 미호출). 타입화된 미스 상태를 쓴다."""
    return {
        "answer": NO_CONTEXT_MESSAGE,
        "sources": [],
        "status": "not_found",
        "retrieval_mode": "none",
    }


def route_after_retrieve(state: GraphState) -> str:
    """retrieve 후 유일 분기점(순수 함수). 다음 노드 이름을 반환한다.

    - 결과 있음 → answer
    - 이미 재시도했고 또 0건 → not_found (진짜 미스)
    - 필터 검색 0건(코드 있음) → clear_filter (비필터 재시도)
    - 비필터 검색 0건 → not_found (진짜 미스)
    """
    if state.get("chunks"):
        return "answer"
    if state.get("retried", False):
        return "not_found"
    if state.get("effective_code"):
        return "clear_filter"
    return "not_found"
