# ADR-005: 검색→답변 흐름의 LangGraph 상태 머신 채택

- **상태(Status)**: 채택(Accepted)
- **날짜**: 2026-06-06
- **관련**: `docs/langgraph-multiagent.md`(설계), `src/graph/`, `src/agent/pipeline.py`, [ADR-002](ADR-002-cross-reference-rag-redefinition.md), [ADR-003](ADR-003-llm-embedding-gemini.md)

---

## 배경 (Context)

`agent.pipeline.ask()`는 선형(retrieve→answer)이었다. 다음 동작을 명시적·테스트 가능한 제어 흐름으로 추가할 필요가 있었다:

1. 질의에 에러코드(SRVO-NNN)가 있으면 메타데이터 필터 검색, 없으면 일반 검색.
2. 검색 결과 0건이면 LLM 호출 없이 조기 종료.
3. 필터 검색이 0건이면 필터를 풀고 1회 재검색(fallback).

이를 선형 함수에 if/else로 누적하면 분기·재시도가 코드에 흩어지고 단위 테스트가 어렵다. 특히 (3)의 재시도(루프)와 (1)/(2)의 분기를 한 곳에서 검증 가능하게 만들 구조가 필요했다.

## 결정 (Decision)

**검색→답변 흐름을 `src/graph/`의 LangGraph `StateGraph`(조건부 라우팅 상태 머신)로 구현한다.**

- 노드 5개: `orchestrate`(규칙 기반 코드 추출) → `retrieve` →(라우터)→ `answer` / `clear_filter`(→retrieve 1회 재진입) / `not_found`.
- 라우팅은 **규칙 기반**(정규식 `CODE_RE` + 검색 0건 판정). 라우팅에 LLM을 쓰지 않는다. 그래프 내 LLM 호출은 `answer` 노드 1곳뿐.
- 단일 턴·무상태(체크포인터/메모리 없음).
- 기존 `Retriever.search`·`generate_answer`를 재작성 없이 노드로 감싼다(의존성 주입으로 노드 단위 테스트).
- `ask()`는 그래프를 호출하는 thin wrapper로 유지(레거시 출력 3키 보존 + 가산 키 `retrieval_mode`).
- 의존성: `langgraph`(+전이 `langchain-core`). LLM은 google-genai 직호출 유지([ADR-003]) — LangChain LLM 래퍼는 도입하지 않는다.

## 근거 (Rationale) — 왜 LangGraph인가 (정직한 기술)

- **명시적 제어 흐름**: 분기·재시도가 그래프 노드/엣지로 드러나 흐름을 읽고 검증하기 쉽다.
- **bounded 재시도 엣지**: `clear_filter`가 `retried` 가드를 세워 재시도가 정확히 1회만 일어난다. 루프를 선형 코드보다 안전하게 표현한다.
- **노드 단위 테스트성**: 각 노드가 상태의 순수 함수 + 주입 의존성이라 fake로 격리 테스트된다.
- **향후 확장성**: 노드/엣지 추가가 국소적(예: 추후 검증되면 노드 추가).

**과장 금지(ADR-002 원칙, CLAUDE.md §2)**: 이 구조의 채택 근거는 "에이전트가 필요해서"가 아니다. LLM이 자율적으로 라우팅·도구선택하지 않으며, 단일 턴·규칙 기반이다. 따라서 외부 표기는 **"멀티에이전트"가 아니라 "조건부 라우팅 상태 머신 + 1회 재시도 엣지"**로 한다. "LLM 기반 오케스트레이션", "자가수정 루프", "동적 도구 선택", 측정 안 한 정확도·"최적화" 주장은 하지 않는다.

## 고려한 대안 (Alternatives considered)

1. **선형 함수에 if/else 누적** — 분기·재시도가 흩어지고 루프 가드·테스트가 취약 → 기각.
2. **LangChain LCEL/Runnable 체인** — 조건부 재시도 루프 표현이 LangGraph보다 부자연스럽고, LLM 래퍼(ChatGoogleGenerativeAI) 도입이 [ADR-003]의 google-genai 직호출 결정을 뒤집음 → 기각.
3. **LangGraph StateGraph + google-genai 직호출** — 분기/루프를 명시 표현하면서 기존 검증 모듈을 재활용 → **채택**.

## 후속 (검증 전 주장 불가 — CLAUDE.md §2)

라우팅 정확도, 비필터 재시도의 답변 품질 영향(오답률), 키워드 의도 추출 정밀도, fallback 프롬프트 헤징 효과, A6(멀티 vs 단일 RAG). 모두 측정 후에만 수치/효과 주장. 상세는 `docs/langgraph-multiagent.md` §6.
