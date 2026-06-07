"""graph 노드/라우터 유닛 테스트 — 주입 fake로 격리(실 Chroma/API 없음).

설계 §5. 라우터는 순수 함수라 무목, retrieve/answer만 fake 의존성 사용.
"""

from __future__ import annotations

from agent.answer_generator import NO_CONTEXT_MESSAGE
from graph.nodes import (
    _to_source,
    clear_filter,
    make_answer,
    make_retrieve,
    not_found,
    orchestrate,
    route_after_retrieve,
)
from parsing import Chunk


def _chunk(code: str, page: int = 1) -> Chunk:
    return Chunk(
        id=f"{code}_{page:03d}",
        content=f"{code} content",
        metadata={"error_code": code, "page_no": page, "parsed_by": "marker"},
    )


class _FakeRetriever:
    """search 호출 인자 기록 + 호출별로 미리 정한 결과 반환."""

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
        self.calls: list = []

    def generate_content(self, model, contents, config=None):
        self.calls.append(contents)
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text: str = "답변") -> None:
        self.models = _FakeModels(text)


# --- orchestrate ---


def test_orchestrate_extracts_code_from_query():
    out = orchestrate({"query": "SRVO-062 배터리 알람"})
    assert out["effective_code"] == "SRVO-062"
    assert out["retried"] is False


def test_orchestrate_no_code():
    out = orchestrate({"query": "로봇이 안 움직여요"})
    assert out["effective_code"] is None


def test_orchestrate_respects_caller_override():
    # caller가 effective_code를 이미 줬으면 query 추출보다 우선
    out = orchestrate({"query": "SRVO-062 알람", "effective_code": "SRVO-999"})
    assert out["effective_code"] == "SRVO-999"


def test_orchestrate_normalizes_lowercase_code():
    # 소문자 입력도 정규형(대문자·하이픈)으로 변환해야 메타데이터 필터가 적중한다.
    out = orchestrate({"query": "srvo-062 배터리 알람"})
    assert out["effective_code"] == "SRVO-062"


def test_orchestrate_normalizes_code_without_hyphen():
    # 하이픈 누락 입력도 정규형으로 복원.
    out = orchestrate({"query": "srvo062 배터리"})
    assert out["effective_code"] == "SRVO-062"


# --- retrieve ---


def test_retrieve_filtered_passes_code_and_sets_mode():
    r = _FakeRetriever([[_chunk("SRVO-062")]])
    node = make_retrieve(r)
    out = node({"query": "q", "n_results": 2, "effective_code": "SRVO-062"})
    assert out["retrieval_mode"] == "filtered"
    assert out["chunks"] and out["chunks"][0].id == "SRVO-062_001"
    assert r.calls[0] == {"query": "q", "n_results": 2, "error_code": "SRVO-062"}


def test_retrieve_unfiltered_when_no_code():
    r = _FakeRetriever([[_chunk("SRVO-001")]])
    out = make_retrieve(r)({"query": "q", "effective_code": None})
    assert out["retrieval_mode"] == "unfiltered"
    assert r.calls[0]["error_code"] is None
    assert r.calls[0]["n_results"] == 3  # 기본값


def test_retrieve_mode_is_fallback_when_retried_first():
    # retried가 우선: effective_code가 None이어도 retried면 unfiltered_fallback
    r = _FakeRetriever([[_chunk("SRVO-062")]])
    out = make_retrieve(r)({"query": "q", "effective_code": None, "retried": True})
    assert out["retrieval_mode"] == "unfiltered_fallback"  # NOT "unfiltered"


# --- clear_filter ---


def test_clear_filter_resets_and_guards():
    out = clear_filter({"effective_code": "SRVO-062", "retried": False})
    assert out == {"effective_code": None, "retried": True}


# --- answer ---


def test_answer_calls_generate_answer_and_maps_sources():
    client = _FakeClient(text="배터리를 교체하십시오.")
    chunks = [_chunk("SRVO-062", 77), _chunk("SRVO-065", 78)]
    out = make_answer(client)({"query": "q", "chunks": chunks})
    assert out["answer"] == "배터리를 교체하십시오."
    assert out["status"] == "answered"
    assert [s["error_code"] for s in out["sources"]] == ["SRVO-062", "SRVO-065"]
    assert out["sources"][0] == {"error_code": "SRVO-062", "page_no": 77, "parsed_by": "marker"}


# --- not_found ---


def test_not_found_sets_status_and_none_mode():
    out = not_found({"query": "q"})
    assert out["answer"] == NO_CONTEXT_MESSAGE
    assert out["sources"] == []
    assert out["status"] == "not_found"
    assert out["retrieval_mode"] == "none"


# --- router ---


def test_router_chunks_present_goes_answer():
    assert route_after_retrieve({"chunks": [_chunk("SRVO-001")]}) == "answer"


def test_router_empty_and_retried_goes_not_found():
    assert route_after_retrieve({"chunks": [], "retried": True, "effective_code": None}) == "not_found"


def test_router_filtered_miss_goes_clear_filter():
    assert route_after_retrieve({"chunks": [], "retried": False, "effective_code": "SRVO-062"}) == "clear_filter"


def test_router_unfiltered_miss_goes_not_found():
    assert route_after_retrieve({"chunks": [], "retried": False, "effective_code": None}) == "not_found"


# --- _to_source ---


def test_to_source_projects_metadata():
    assert _to_source(_chunk("SRVO-062", 77)) == {
        "error_code": "SRVO-062",
        "page_no": 77,
        "parsed_by": "marker",
    }
