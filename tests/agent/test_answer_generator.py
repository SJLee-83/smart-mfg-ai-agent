"""answer_generator 테스트 — LLM(google-genai) 호출을 모킹(클라이언트 주입).

빈 청크 시 기본 메시지, 청크 있을 때 LLM 호출, 프롬프트의 error_code 포함을 검증한다.
"""

from __future__ import annotations

from agent.answer_generator import NO_CONTEXT_MESSAGE, generate_answer
from parsing import Chunk


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    """client.models 대역 — generate_content 호출 인자를 기록한다."""

    def __init__(self, text: str = "한국어 답변") -> None:
        self._text = text
        self.calls: list[dict] = []

    def generate_content(self, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, models: _FakeModels) -> None:
        self.models = models


def _chunk(code: str, page: int = 1) -> Chunk:
    return Chunk(
        id=f"{code}_{page:03d}",
        content=f"{code} alarm explanation and recovery steps",
        metadata={"error_code": code, "page_no": page, "parsed_by": "marker"},
    )


def test_empty_chunks_returns_default_message():
    # 청크 없으면 LLM 호출 없이 기본 메시지 (client 불필요 — 조기 반환)
    assert generate_answer("아무 질문", []) == NO_CONTEXT_MESSAGE


def test_calls_llm_when_chunks_present():
    models = _FakeModels(text="배터리를 교체하십시오.")
    client = _FakeClient(models)

    out = generate_answer("배터리 알람", [_chunk("SRVO-062")], client=client)

    assert out == "배터리를 교체하십시오."
    assert len(models.calls) == 1  # LLM 정확히 1회 호출


def test_prompt_includes_error_code():
    models = _FakeModels()
    client = _FakeClient(models)

    generate_answer(
        "질문", [_chunk("SRVO-062"), _chunk("SRVO-065", 2)], client=client
    )

    contents = models.calls[0]["contents"]
    assert "SRVO-062" in contents
    assert "SRVO-065" in contents
