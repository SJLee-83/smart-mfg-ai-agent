"""ask() wrapper 테스트 — 그래프를 fake retriever/client로 구동(실 Chroma/API 없음).

하위호환 계약(레거시 3키 보존 + 가산 retrieval_mode)과 provenance 회귀를 고정한다.
설계 §2.6, §5.
"""

from __future__ import annotations

from agent.answer_generator import NO_CONTEXT_MESSAGE
from agent.pipeline import ask
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

    def search(self, query, n_results=3, error_code=None):
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


def _ask(results, query, *, error_code=None, answer="답변입니다."):
    return ask(
        query,
        error_code=error_code,
        retriever=_FakeRetriever(results),
        client=_FakeClient(answer),
    )


def test_ask_output_has_exactly_four_keys():
    result = _ask([[_chunk("SRVO-062")]], "SRVO-062 x")
    assert set(result.keys()) == {"answer", "sources", "query", "retrieval_mode"}


def test_ask_preserves_legacy_keys():
    result = _ask([[_chunk("SRVO-062", 77)]], "SRVO-062 battery", answer="조치하세요")
    assert result["query"] == "SRVO-062 battery"
    assert result["answer"] == "조치하세요"
    assert result["sources"] == [{"error_code": "SRVO-062", "page_no": 77, "parsed_by": "marker"}]


def test_ask_filtered_mode():
    result = _ask([[_chunk("SRVO-062")]], "SRVO-062 battery alarm")
    assert result["retrieval_mode"] == "filtered"


def test_ask_unfiltered_mode_for_no_code_query():
    result = _ask([[_chunk("SRVO-001")]], "robot won't move")
    assert result["retrieval_mode"] == "unfiltered"


def test_ask_unfiltered_fallback_not_unfiltered():
    # 회귀: 필터 미스 → 비필터 재시도 적중은 "unfiltered"가 아니라 "unfiltered_fallback"
    result = _ask([[], [_chunk("SRVO-065")]], "SRVO-062 battery")
    assert result["retrieval_mode"] == "unfiltered_fallback"


def test_ask_none_mode_on_total_miss():
    result = _ask([[], []], "SRVO-062 battery")
    assert result["retrieval_mode"] == "none"
    assert result["answer"] == NO_CONTEXT_MESSAGE
    assert result["sources"] == []
