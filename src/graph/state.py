"""그래프 상태 스키마 — 단일 턴·무상태 실행의 작업 상태.

설계 근거: docs/langgraph-multiagent.md §2.5.

reducer를 쓰지 않는다(단일 턴이라 누적이 없음 — chunks도 재시도 시 병합이 아니라
완전 교체, last-write-wins가 정확). total=False라 caller는 query만 필수로 넘기면 되고,
라우터/노드는 산출·제어 키를 state.get(...)으로 방어적으로 읽는다.
"""

from __future__ import annotations

from typing import Literal, Optional, TypedDict

from parsing import Chunk

RetrievalMode = Literal["filtered", "unfiltered", "unfiltered_fallback", "none"]
Status = Literal["answered", "not_found"]


class GraphState(TypedDict, total=False):
    """검색→답변 그래프의 작업 상태.

    필드 역할:
      - 입력(invoke 시 caller 설정): query, n_results, effective_code
      - 산출: chunks, retrieval_mode, status, answer, sources
      - 제어: retried (재시도 1회 가드)
    """

    # 입력
    query: str
    n_results: int
    effective_code: Optional[str]  # caller override로 시드; orchestrate가 비었을 때만 채움; clear_filter가 None으로 리셋

    # 산출
    chunks: list[Chunk]
    retrieval_mode: RetrievalMode
    status: Status
    answer: str
    sources: list[dict]  # [{error_code, page_no, parsed_by}]

    # 제어
    retried: bool  # clear_filter가 True로 설정 — 무한 루프 방지(재시도 최대 1회)
