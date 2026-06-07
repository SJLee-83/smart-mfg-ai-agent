"""Streamlit 데모 UI — R-Mate FANUC 설비 에러 진단 AI.

작업자가 설비 알람 코드(예: SRVO-062)나 증상을 자연어로 물으면 매뉴얼 근거를
검색해 안전 우선 한국어 수리 가이드를 출처와 함께 보여준다.

agent.pipeline.ask()를 그대로 호출하는 thin 프런트엔드다. 라우팅/검색/답변 로직은
src/에 있고, 이 파일은 입력 수집과 결과 표시만 담당한다.

실행: streamlit run app.py  (브라우저는 수동 오픈)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# src 레이아웃: editable 설치 없이 src/ 패키지를 import (pytest의 pythonpath=src와 동일 효과).
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

from agent.pipeline import ask  # noqa: E402  (sys.path 주입 후 import해야 함)

# Chroma 영속 디렉터리: .env의 VECTOR_DB_PATH(.env.example 참고) 또는 기본값.
PERSIST_DIR = os.getenv("VECTOR_DB_PATH", "chroma_db")

# 검색 모드별 사람이 읽는 설명. unfiltered_fallback은 위험 신호로 강조한다.
MODE_LABELS = {
    "filtered": "🎯 filtered — 에러코드 메타데이터로 필터링한 검색",
    "unfiltered": "🔍 unfiltered — 코드 없이 의미 기반 일반 검색",
    "unfiltered_fallback": (
        "⚠️ unfiltered_fallback — 필터 검색 0건으로 필터를 풀고 재검색한 결과. "
        "요청 코드와 다른 출처일 수 있으니 아래 출처의 error_code를 교차확인하세요."
    ),
    "none": "∅ none — 검색 결과 없음 (LLM 호출 없이 조기 종료)",
}

st.set_page_config(page_title="R-Mate", page_icon="🤖", layout="wide")

st.title("R-Mate — FANUC 설비 에러 진단 AI")
st.caption("FANUC R-30iA Mate Controller 유지보수 매뉴얼 기반 RAG + LangGraph 조건부 라우팅")

with st.sidebar:
    st.header("검색 설정")
    code_input = st.text_input(
        "에러코드 직접 입력 (선택)",
        placeholder="예: SRVO-062",
        help="입력 시 질문 텍스트보다 우선해 해당 코드로 필터 검색합니다.",
    )
    error_code = code_input.strip() or None
    n_results = st.slider("검색 결과 수", min_value=1, max_value=5, value=3)
    st.divider()
    st.caption(f"Vector DB: `{PERSIST_DIR}`")
    st.caption("규칙 기반 라우팅 · 단일 턴 · 멀티에이전트 아님")

query = st.text_area(
    "질문",
    placeholder="예: SRVO-062 배터리 알람이 떴어. 어떻게 해야 해?",
    height=120,
)
search = st.button("검색", type="primary")

if search:
    if not query.strip():
        st.warning("질문을 입력하세요.")
        st.stop()

    with st.spinner("매뉴얼 검색 + 답변 생성 중..."):
        try:
            result = ask(
                query.strip(),
                n_results=n_results,
                error_code=error_code,
                persist_dir=PERSIST_DIR,
            )
        except Exception as exc:  # noqa: BLE001 — UI에서 원인을 그대로 노출
            st.error(f"오류: {type(exc).__name__}: {exc}")
            st.stop()

    st.subheader("답변")
    st.markdown(result["answer"])

    mode = result.get("retrieval_mode", "none")
    st.info(MODE_LABELS.get(mode, f"검색 모드: {mode}"))

    sources = result.get("sources", [])
    st.subheader(f"출처 ({len(sources)})")
    if sources:
        for i, s in enumerate(sources, start=1):
            code = s.get("error_code") or "(코드 미상)"
            page = s.get("page_no")
            parsed_by = s.get("parsed_by") or "?"
            page_str = f"p.{page}" if page is not None else "p.?"
            st.markdown(f"**{i}. `{code}`** · 매뉴얼 {page_str} · parsed_by=`{parsed_by}`")
    else:
        st.write("출처 없음")
