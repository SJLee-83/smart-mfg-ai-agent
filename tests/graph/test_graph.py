"""컴파일 그래프 라우팅 테스트 — fake 의존성으로 4경로 + retrieval_mode 회귀.

설계 §5. build_graph(retriever=fake, client=fake)로 실 Chroma/API 없이 end-to-end.
"""

from __future__ import annotations

from agent.answer_generator import NO_CONTEXT_MESSAGE
from graph.graph import build_graph
from parsing import Chunk


def _chunk(code: str, page: int = 1) -> Chunk:
    return Chunk(
        id=f"{code}_{page:03d}",
        content=f"{code} content",
        metadata={"error_code": code, "page_no": page, "parsed_by": "marker"},
    )


class _FakeRetriever:
    def __init__(self, results: list[list[Chunk]]) -> None:
        self._results = list(results)
        self.calls: list[dict] = []

    def search(self, query, n_results=3, error_code=None):
        self.calls.append({"query": query, "n_results": n_results, "error_code": error_code})
        return self._results.pop(0) if self._results else []


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, text: str) -> None:
        self._text = text

    def generate_content(self, model, contents, config=None):
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text: str = "답변입니다.") -> None:
        self.models = _FakeModels(text)


def _invoke(retriever_results, query, *, n_results=3, effective_code=None, answer_text="답변입니다."):
    graph = build_graph(retriever=_FakeRetriever(retriever_results), client=_FakeClient(answer_text))
    return graph.invoke(
        {"query": query, "n_results": n_results, "effective_code": effective_code}
    )


def test_graph_filtered_hit():
    final = _invoke([[_chunk("SRVO-062", 77)]], "SRVO-062 battery alarm")
    assert final["status"] == "answered"
    assert final["retrieval_mode"] == "filtered"
    assert final["answer"] == "답변입니다."
    assert [s["error_code"] for s in final["sources"]] == ["SRVO-062"]


def test_graph_no_code_hit_is_unfiltered():
    final = _invoke([[_chunk("SRVO-001")]], "robot won't move")
    assert final["status"] == "answered"
    assert final["retrieval_mode"] == "unfiltered"  # 무코드 질의


def test_graph_filtered_miss_then_fallback_hit():
    # 1차 필터 검색 0건 → clear_filter → 2차 비필터 적중
    final = _invoke([[], [_chunk("SRVO-065", 78)]], "SRVO-062 battery")
    assert final["status"] == "answered"
    # 회귀: fallback은 절대 "unfiltered"가 아니라 "unfiltered_fallback"
    assert final["retrieval_mode"] == "unfiltered_fallback"
    assert [s["error_code"] for s in final["sources"]] == ["SRVO-065"]


def test_graph_total_miss_with_code_is_none():
    # 필터 0건 → 재시도 비필터도 0건 → not_found
    final = _invoke([[], []], "SRVO-062 battery")
    assert final["status"] == "not_found"
    assert final["answer"] == NO_CONTEXT_MESSAGE
    assert final["sources"] == []
    assert final["retrieval_mode"] == "none"


def test_graph_total_miss_no_code_is_none():
    final = _invoke([[]], "nonexistent topic")
    assert final["status"] == "not_found"
    assert final["retrieval_mode"] == "none"


def test_graph_retry_runs_at_most_once():
    # 코드 있고 두 번 다 0건이면 search는 정확히 2회(필터 1 + 비필터 1) 후 종료
    retr = _FakeRetriever([[], []])
    graph = build_graph(retriever=retr, client=_FakeClient())
    graph.invoke({"query": "SRVO-062 x", "n_results": 3, "effective_code": None})
    assert len(retr.calls) == 2
    assert retr.calls[0]["error_code"] == "SRVO-062"  # 1차 필터
    assert retr.calls[1]["error_code"] is None  # 2차 비필터
