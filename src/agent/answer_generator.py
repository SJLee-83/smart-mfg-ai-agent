"""답변 생성 — 검색된 청크를 컨텍스트로 Gemini가 한국어 수리 가이드를 생성한다.

흐름: (query, chunks) -> 프롬프트 구성 -> Gemini generate_content -> 한국어 답변.
LLM: gemini-2.5-flash — **A6 검증 전 잠정 선택**(속도/비용 균형). 검증 후 변경 가능.
(원안 gemini-2.0-flash는 generate_content에서 404 retired → 직속 stable 후속으로 대체.)
설계 근거: ADR-003. API 키는 .env의 GOOGLE_API_KEY.

시스템 지시는 GenerateContentConfig.system_instruction로 분리해 전달하고,
매뉴얼 발췌(컨텍스트)와 사용자 질문은 contents로 보낸다.
"""

from __future__ import annotations

import os

from dotenv import find_dotenv, load_dotenv
from google import genai
from google.genai import types

from parsing import Chunk

MODEL = "gemini-2.5-flash"  # A6 검증 전 잠정. 원안 gemini-2.0-flash는 retired(404) → stable 후속으로 대체
ENV_KEY = "GOOGLE_API_KEY"

SYSTEM_INSTRUCTION = (
    "당신은 FANUC 로봇 유지보수 전문가입니다. "
    "제공된 매뉴얼 발췌 내용에 근거해서만 답변하고, 매뉴얼에 없는 내용은 추측하지 마십시오. "
    "안전 주의사항을 가장 먼저 명확히 안내한 뒤 조치 절차를 설명하십시오. "
    "한국어로 답변하십시오."
)

NO_CONTEXT_MESSAGE = "관련 정보를 찾지 못했습니다."


def _make_client() -> genai.Client:
    """GOOGLE_API_KEY로 google-genai 클라이언트를 생성한다. 키가 없으면 예외."""
    load_dotenv(find_dotenv(usecwd=True))
    api_key = os.getenv(ENV_KEY)
    if not api_key:
        raise EnvironmentError(f"{ENV_KEY} not set in environment (.env)")
    return genai.Client(api_key=api_key)


def _build_prompt(query: str, chunks: list[Chunk]) -> str:
    """청크를 매뉴얼 발췌 컨텍스트로, 질문과 함께 하나의 프롬프트로 구성한다.

    각 청크 블록에 error_code를 명시해 LLM이 어떤 코드 근거인지 구분하게 한다.
    """
    blocks = []
    for c in chunks:
        code = c.metadata.get("error_code") or "(코드 미상)"
        page = c.metadata.get("page_no")
        header = f"[{code}] (매뉴얼 p.{page})" if page is not None else f"[{code}]"
        blocks.append(f"{header}\n{c.content}")
    context = "\n\n".join(blocks)
    return (
        "다음은 FANUC 매뉴얼에서 검색된 관련 항목입니다.\n\n"
        f"=== 매뉴얼 발췌 ===\n{context}\n\n"
        f"=== 사용자 질문 ===\n{query}\n\n"
        "위 매뉴얼 발췌에 근거해 한국어로 수리 가이드를 작성하십시오. "
        "발췌에 없는 내용은 추측하지 말고, 필요한 안전 주의사항을 먼저 안내하십시오."
    )


def generate_answer(
    query: str,
    chunks: list[Chunk],
    *,
    client: genai.Client | None = None,
) -> str:
    """검색된 청크를 컨텍스트로 한국어 수리 가이드를 생성한다.

    Args:
        query: 사용자 질문.
        chunks: 검색된 근거 청크. 빈 리스트면 LLM 호출 없이 기본 메시지를 반환한다.
        client: 주입용 google-genai 클라이언트(테스트). None이면 .env로 생성.

    Returns:
        한국어 답변 문자열. 청크가 없으면 NO_CONTEXT_MESSAGE.

    Raises:
        EnvironmentError: GOOGLE_API_KEY 미설정(client 미주입 시).
        google-genai API 오류는 그대로 전파(조용히 삼키지 않음).
    """
    if not chunks:
        return NO_CONTEXT_MESSAGE

    client = client or _make_client()
    prompt = _build_prompt(query, chunks)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION),
    )
    return response.text
