# LangGraph 상태 머신 전환 설계 (검색→답변 파이프라인)

> 설계 논의: `design-langgraph-multiagent` 팀(3인 + 리드, 2라운드 + 수렴).
> 대상: 현재 선형 `agent.pipeline.ask()`(retrieve→answer)를 **조건부 라우팅 상태 머신 + 1회 재시도 엣지**로 전환.
> 작성일: 2026-06-06 / 상태: 설계 합의 완료, 구현 대기

---

## 0. 명칭에 대한 정직성 고지 (먼저 읽을 것)

이 작업은 사용자 요청에서 "멀티에이전트 구조"로 명명됐으나, **결론은 그 명칭을 외부 문서에 쓰지 않는 것**. 근거:

- LLM이 라우팅을 하지 않는다(라우팅은 정규식 + 0건 판정의 **규칙 기반**).
- 단일 턴·무상태이므로 목표 지속/반복 계획 같은 자율성 없음
- "Retrieval/Answer"는 기존 `Retriever.search`/`generate_answer`를 감싼 **노드**다. 그래프 내 LLM 호출은 답변 노드 1곳뿐.

[ADR-002](decisions/ADR-002-cross-reference-rag-redefinition.md)에서 과장된 "Cross-Reference RAG" 명칭을 실측으로 축소한 것과 같은 규약(`docs/conventions.md` §2)의 적용. **정직한 명칭 천장과 금지 주장 목록은 §6에 배치**하며 이 문서의 서술도 그 목록을 준수(노드/상태 머신/규칙 기반 라우팅으로 기술).

---

## 1. 확정 전제 (인터뷰에서 잠금 - 본 설계의 입력)

| # | 결정 | 값 |
|---|---|---|
| 1 | 전환 목적 | 실제 분기 동작(조건부 엣지) 구현 - 선형 wrapper 아님 |
| 2 | 대화 모델 | **단일 턴·무상태** (체크포인터/메모리 없음) |
| 3 | 라우팅 분기 | (a) 에러코드 유/무 → 필터/비필터 검색, (b) 0건 → 조기 종료, (c) 필터 0건 → 비필터 재검색. 오프토픽 거부 제외 |
| 4 | 의도/코드 파악 | **규칙 기반** (`CODE_RE` 정규식; 라우팅에 LLM 미사용) |
| 5 | 모듈 배치 | 새 `src/graph/`; `agent.pipeline.ask()`는 그래프 thin wrapper로 유지(하위호환), 기존 35 테스트 유지 |
| 6 | 재시도 트리거 | **0건일 때만** (거리 임계값 미사용 - 미검증값 회피) |
| 7 | 의존성 | `langgraph`(+전이 `langchain-core`) 추가. google-genai 직호출 유지, LangChain LLM 래퍼 미도입. 기존 모듈 재활용(로직 재작성 금지) |
| 8 | 스코프 제외 | Safety Agent (ADR-002/미검증) |

---

## 2. 합의된 아키텍처

### 2.1 노드 5개 + 단일 라우터

| 노드 | 읽기 | 쓰기(delta) | 호출/로직 |
|---|---|---|---|
| `orchestrate` | query, effective_code | effective_code, retried=False | `effective_code`가 비어 있을 때만 `CODE_RE.search(query)`로 채움(호출자 override 우선). LLM 없음 |
| `retrieve` | query, n_results, effective_code, retried | chunks, retrieval_mode | `Retriever.search(query, n_results, error_code=effective_code)`. retrieval_mode는 §2.4 규칙 |
| `clear_filter` | - | effective_code=None, retried=True | 순수 상태 쓰기(재시도 가드). 로직 0 |
| `answer` | query, chunks | answer, sources, status="answered" | `generate_answer(query, chunks, client=...)` + `_to_source` 매핑 |
| `not_found` | - | answer=NO_CONTEXT_MESSAGE, sources=[], status="not_found", retrieval_mode="none" | 순수 종단 노드. LLM 없음 |

라우터(순수 함수, 유일 분기점):

```python
def route_after_retrieve(state) -> str:
    if state["chunks"]:                 # 결과 있음 → 답변
        return "answer"
    if state.get("retried", False):     # 이미 재시도했고 또 0건 → 진짜 미스
        return "not_found"
    if state.get("effective_code"):     # 필터 검색 0건 → 필터 풀고 재시도
        return "clear_filter"
    return "not_found"                  # 비필터 검색 0건 → 진짜 미스
```

### 2.2 엣지 배선

```python
builder.add_edge(START, "orchestrate")
builder.add_edge("orchestrate", "retrieve")
builder.add_conditional_edges(
    "retrieve", route_after_retrieve,
    {"answer": "answer", "clear_filter": "clear_filter", "not_found": "not_found"},
)
builder.add_edge("clear_filter", "retrieve")   # 비필터로 재진입(최대 1회)
builder.add_edge("answer", END)
builder.add_edge("not_found", END)
graph = builder.compile()
```

**무한 루프 불가 증명**: `clear_filter`가 `retried=True`를 쓴다. 재시도 후 retrieve가 또 0건이면 라우터의 `state.get("retried")` 가지가 `not_found`로 보낸다 → 재시도 엣지는 최대 1회. 트리거는 오직 0건(임계값 없음, 전제 #6 충족).

### 2.3 그래프 다이어그램

```
                 START
                   │
                   ▼
             ┌────────────┐
             │ orchestrate │  effective_code = override OR CODE_RE.search(query) OR None
             └────────────┘
                   │
                   ▼
             ┌────────────┐ ◄──────────────┐
             │  retrieve   │                │ (비필터로 재진입)
             └────────────┘                │
                   │ route_after_retrieve  │
        ┌──────────┼───────────┐           │
   chunks 있음  필터 0건     진짜 0건       │
   "answer"   "clear_filter"  "not_found"  │
        │          │              │        │
        ▼          ▼              │        │
   ┌────────┐ ┌────────────┐      │        │
   │ answer │ │clear_filter ├──────┼────────┘  effective_code=None, retried=True
   └────────┘ └────────────┘      │
        │                    ┌──────────┐
        │                    │ not_found │  answer=NO_CONTEXT_MESSAGE, sources=[], mode="none"
        ▼                    └──────────┘
       END                        │
                                  ▼
                                 END
```

retrieve가 3개의 서로 다른 후속(answer/clear_filter/not_found)을 가지며 그중 하나가 1회 루프백 → 선형이 아닌 실제 상태 머신(전제 #1 충족).

### 2.4 출처 표기(provenance) - `retrieval_mode` 4값

분기 (c)의 위험: 필터를 풀고 재검색하면 **요청 코드와 다른(유사하지만 틀린) 코드의 청크**가 올라올 수 있고, `generate_answer`의 프롬프트는 각 블록에 실제 error_code를 붙이므로 LLM이 **엉뚱한 코드 근거로 단정 답변**할 가능성 존재(제조/안전 도메인 최악 실패). 이를 숨기지 않기 위해 출처 모드를 명시 표기.

상태/노드가 직접 쓰는 4값(래퍼 파생 아님):

| 값 | 의미 |
|---|---|
| `filtered` | 코드 필터로 검색해 결과를 얻음 |
| `unfiltered` | 코드가 애초에 없던 일반 검색 |
| `unfiltered_fallback` | **위험 신호** - 필터 검색 0건이라 필터를 풀고 얻은 결과. 요청 코드 일치 보장 없음 |
| `none` | 전혀 못 찾음 |

**계산 규칙(우선순위 고정 - `retried` 먼저, 무조건)**:

```python
mode = "unfiltered_fallback" if state.get("retried") \
       else ("filtered" if state.get("effective_code") else "unfiltered")
```

`retried`를 **반드시 먼저** 검사. `clear_filter`가 effective_code=None·retried=True를 동시에 쓰므로, effective_code를 먼저 보면 fallback 상태(effective_code=None, retried=True)가 `unfiltered`로 **오라벨**되어 위험 신호 소실. 따라서 `retried` 우선이 불변식이며 회귀 테스트로 고정(§5).

- `unfiltered`(무코드 질의)와 `unfiltered_fallback`(코드 있었으나 필터 미스로 완화)은 **절대 aliasing 금지**.
- v1의 오답 가시성 = `retrieval_mode="unfiltered_fallback"` + 기존 `sources`의 청크별 `error_code`(요청 코드와 다르면 호출자가 즉시 감지). 이미 충분히 노출되므로 청크별 추가 필드 미도입

### 2.5 State 스키마

```python
# src/graph/state.py
from typing import TypedDict, Optional, Literal
from parsing import Chunk

class GraphState(TypedDict, total=False):
    # 입력 (invoke 시 caller가 설정)
    query: str
    n_results: int
    effective_code: Optional[str]   # ask(error_code=)로 시드; orchestrate가 비었을 때만 채움; clear_filter가 None으로 리셋
    # 산출
    chunks: list[Chunk]             # retrieve가 씀(재시도 시 덮어씀 - last-write-wins가 정확)
    retrieval_mode: Literal["filtered", "unfiltered", "unfiltered_fallback", "none"]
    status: Literal["answered", "not_found"]   # 그래프 내부용(ask() 출력 미노출)
    answer: str
    sources: list[dict]             # [{error_code, page_no, parsed_by}]
    # 제어
    retried: bool                   # clear_filter가 True - 재시도 1회 가드
```

- `total=False`: caller는 query(+선택 n_results/effective_code)만 넘기면 됨. **라우터·노드는 제어/산출 키를 `state.get(...)`로 방어적으로 읽는다**(첫 패스 KeyError 방지).
- **reducer 미사용 결정**: 누적이 전혀 없다(`chunks`는 재시도 시 병합이 아니라 완전 교체). 단일 턴·무상태(전제 #2)라 `add_messages`/`operator.add`는 cargo-cult. LangGraph를 **상태 누적이 아니라 조건부 라우팅**에 쓴다는 점을 명시.
- **코드 필드 1개 결정**: `requested_code`/`filter_code` 2필드 분리는 v1에서 불필요. `retried` 플래그가 fallback 구분을 담당하므로 4값 provenance를 1필드로 달성. 2필드는 §6의 보류 항목(프롬프트 디스클레이머)이 생길 때만 의미. 지금 두면 "아무도 안 읽는 필드".

### 2.6 `ask()` thin wrapper (하위호환)

```python
def ask(query, n_results=3, error_code=None, *, persist_dir="chroma_db", retriever=None):
    graph = build_graph(retriever=retriever or Retriever(persist_dir=persist_dir))
    final = graph.invoke({"query": query, "n_results": n_results,
                          "effective_code": error_code})
    return {
        "answer": final["answer"],
        "sources": final["sources"],
        "query": query,
        "retrieval_mode": final.get("retrieval_mode", "none"),  # 추가 키
    }
```

- 기존 3키(`answer/sources/query`) 이름·타입·값 **불변**. `retrieval_mode` 1키만 **가산(additive)**.
- **하위호환 실측 확인**: `grep "ask(" tests/` → 매치 없음. `tests/agent/`에 `test_pipeline.py` 부재 → 기존 35 테스트 중 `ask()` 출력 dict를 읽는 테스트가 **하나도 없음**. 가산 키는 어떤 테스트도 깨지 않음.
- `status`는 출력에 미노출(내부 전용). 경계 미스 신호는 `retrieval_mode=="none"`로 충분.

### 2.7 의존성 주입(DI) - 클로저 팩토리

```python
# src/graph/graph.py
def build_graph(*, retriever=None, client=None) -> CompiledStateGraph:
    _retriever = retriever or Retriever(persist_dir=...)   # Chroma 1회 오픈
    builder = StateGraph(GraphState)
    builder.add_node("orchestrate", orchestrate)
    builder.add_node("retrieve", make_retrieve(_retriever))   # 클로저로 주입
    builder.add_node("clear_filter", clear_filter)
    builder.add_node("answer", make_answer(client))           # 클로저로 주입
    builder.add_node("not_found", not_found)
    # ... 엣지(§2.2) ...
    return builder.compile()
```

- 기존 DI 관례(`generate_answer(..., client=None)`, `ask(..., retriever=None)`)와 동일. LangGraph `RunnableConfig`에 도메인 의존성을 넣지 않는다(그건 LangChain LLM 래퍼 관용 - 전제 #7에서 배제).
- 노드는 상태 in → delta out 순수 함수. retrieve/answer만 주입 의존성 사용 → 테스트에서 fake retriever/client로 격리.
- 프로덕션은 `_DEFAULT_GRAPH`를 1회 컴파일 캐시(컴파일은 싸지만 `Retriever()`가 Chroma를 열기 때문).

### 2.8 파일 레이아웃

```
src/graph/
├── __init__.py   # export: build_graph, GraphState
├── state.py      # GraphState TypedDict
├── nodes.py      # orchestrate / retrieve / clear_filter / answer / not_found + route_after_retrieve
└── graph.py      # build_graph(retriever, client) - 노드 등록 + 엣지 + compile
```

- `nodes.py`: `CODE_RE`(parsing.constants), `Retriever`(retrieval.retriever), `generate_answer`/`NO_CONTEXT_MESSAGE`(agent.answer_generator) 임포트.
- `_to_source`는 `agent/pipeline.py`에 그대로 둔다(역방향 의존 회피). wrapper가 로컬 임포트.

---

## 3. 노드 본문 = 기존 로직 재활용(재작성 0)

| 노드 | 재활용 대상 | 재작성 여부 |
|---|---|---|
| orchestrate | `parsing.constants.CODE_RE` | 없음(정규식 직접 사용) |
| retrieve | `Retriever.search(query, n_results, error_code=...)` | 없음(이미 `error_code: str|None` 지원, retriever.py) |
| answer | `generate_answer(query, chunks, client=...)` + `_to_source` | 없음 |
| not_found | `agent.answer_generator.NO_CONTEXT_MESSAGE` | 없음 |

**중복 메모**: `generate_answer`는 빈 청크에 `NO_CONTEXT_MESSAGE`를 LLM 없이 반환한다(방어적). 그래프는 빈 청크를 not_found로 라우팅하므로 answer 노드는 빈 청크로 호출되지 않는다 → `generate_answer`의 가드는 **직접 호출자 보호용으로 유지**(기존 테스트 `test_empty_chunks_returns_default_message`가 고정). 제거 금지.

**키워드 라우팅**: CODE_RE 외 키워드(예: "battery") 기반 라우팅은 **현재 코드에 없음(net-new)**. 전제 #3의 분기는 CODE_RE만으로 충족되므로 **스코프 밖**으로 둔다.

---

## 4. 주요 결정사항과 근거

1. **5노드 채택(4노드 대신)**: 4노드는 `retrieve`가 "내가 재시도 패스인가?"를 라우터가 이미 계산한 술어로 자기탐지해야 함(술어 중복). `clear_filter`를 순수 상태쓰기로 분리하면 retrieve는 `search(...)` 한 줄, 분기 로직은 라우터 1곳 → 단일 책임 + 한 줄 유닛 테스트. 3인 합의.
2. **분기 (a)는 엣지가 아니라 데이터**: 에러코드 유/무는 `effective_code`로 표현하고 retrieve가 소비한다(retriever가 이미 코드 있을 때만 `where` 필터 구성). 별도 노드 2개로 쪼개면 동일 검색 코드를 복제해 가짜 분기를 만드는 것 → 노드 수 부풀리기는 정직성에 반함. 위상 분기는 (b)(c) 2개 + 재시도 루프 1개로 충분.
3. **`not_found`는 노드(엣지→END 아님)**: "LLM 호출 절약" 근거는 **철회됨**(answer 경로의 기존 가드가 이미 절약). 노드의 정당성은 **타입화된 status·provenance를 쓰는 것**: 문자열 매칭 대신 `status` 필드로 미스 판별, `retrieval_mode`로 필터미스 vs 전체미스 구분. 라우터는 문자열만 반환하고 노드만 상태를 쓴다는 불변식 유지.
4. **코드 필드 1개 + `retried` 플래그로 provenance**: 4값 모드를 2필드 없이 달성(§2.4/2.5). 안 읽는 필드 추가는 과설계.
5. **가산 `retrieval_mode` 키**: 하위호환 실측 확인 후 안전 결론(§2.6).
6. **`retried` 우선 검사 고정**: fallback 신호가 조용히 사라지지 않도록 우선순위를 불변식으로 박고 테스트로 고정(§2.4, §5).
7. **프롬프트 디스클레이머는 v1 제외**: "정확 일치 없음, 관련 정보" 같은 LLM 헤징은 측정 없이 "안전 기능"으로 출시하면 그 자체가 과장. §6 후속 검증으로 이관.
8. **의존성**: `langgraph` 추가(전이 `langchain-core`). LangChain LLM 래퍼 미도입. ADR-005 권고(§7).

---

## 5. 테스트 계획

신규 `tests/graph/`:
- `test_nodes.py`: orchestrate(코드 추출/무코드), retrieve(필터/재시도 인자), clear_filter(상태쓰기), answer(주입 fake client), not_found(고정 메시지+status+mode). 라우터: 표 기반(코드유무×결과유무) 무목.
- `test_graph.py`: 컴파일 그래프 + fake 의존성으로 4경로 - (1) 코드 필터 적중, (2) 무코드 적중, (3) 필터 0건→비필터 재시도 적중, (4) 양쪽 0건→not_found.

신규 `tests/agent/test_pipeline.py`(하위호환·provenance 고정):
- 출력 4키 `{answer, sources, query, retrieval_mode}` 고정(레거시 3키 보존 + 가산 키).
- **회귀(critic 요청)**: 필터미스→clear_filter→복구 ⇒ `retrieval_mode == "unfiltered_fallback"`(절대 "unfiltered" 아님).
- **회귀**: 무코드 질의 적중 ⇒ `retrieval_mode == "unfiltered"`. (위 둘이 `retried` 우선순위를 고정)
- 동작 변경 문서화: `error_code=None`이라도 query 텍스트에 SRVO 코드가 있으면 필터 검색(아래 §6 참고).

기존 35 테스트: `src/graph/` 임포트 부작용 없음, `ask()` 시그니처 불변 → 전부 통과 유지(실측 grep 근거).

---

## 6. 미해결 이슈 / 트레이드오프 / 후속 검증 (지금 주장 불가)

**동작 변경(의도된 개선이나 관찰 가능)**: `ask("SRVO-062 알람 발생")`처럼 `error_code=None`이지만 텍스트에 코드가 있으면 이제 **자동 필터** 검색(과거엔 비필터). 전제 #3a에 따른 개선. `ask()` docstring에 명시. 기존 테스트 충돌 없음(실측).

**보류 항목(item 8 - 프롬프트 디스클레이머)**: fallback일 때 answer 노드가 "요청 코드 정확 일치 없음" 한국어 고지를 후첨하는 방안. v1 제외. 구현 시: `generate_answer` 미수정 원칙(전제 #7) 유지 위해 노드 레벨 후첨. **포인터(architect)**: 코드 필드가 1개라 clear_filter가 effective_code를 비우므로, 디스클레이머 시점에 `CODE_RE.search(query)`로 요청 코드를 **재추출**하면 됨(필드 재도입 불필요).

**후속 검증(측정 전 주장 금지 - `docs/conventions.md` §2)**:
1. **라우팅 정확도**: 정규식/0건 라우터가 올바른 가지를 고르는가. 라벨드 질의셋(코드有/코드無/모호)로 오라우팅률 측정.
2. **재시도의 답변 품질 영향(핵심)**: 필터미스 질의에서 비필터 재시도가 정답을 돕는가 vs 오답(엉뚱 코드) 유발률. `unfiltered_fallback` 경로의 위험을 정량화하기 전엔 "fallback 경로"일 뿐 "품질 개선"이 아님.
3. **키워드 의도 추출 정밀도**: CODE_RE 외 키워드 라우팅을 추가할 경우(현재 미도입) 정밀/재현 미측정.
4. **프롬프트 헤징 효과**: item 8 도입 시, 헤징이 오답 피해를 줄이면서 정상 답변을 해치지 않는지 검증 후에만 "안전 기능" 주장.
5. **A6(멀티 vs 단일 RAG 품질)**: mvp-plan 미검증 항목. "최적화" 주장 금지.

---

## 7. 명칭 정직성 (외부 표기 - ADR-002 원칙)

**정직 명칭 천장**: "조건부 라우팅 상태 머신 + 1회 재시도 엣지"(conditional routing state machine with a retry edge). 이 위로 올리지 말 것.

**허용 표기(택1)**:
- "선형 RAG 호출을 LangGraph 상태 머신으로 리팩터링: orchestration 노드가 정규식으로 에러코드를 도출하고, retrieve 노드가 이를 메타데이터 필터로 적용하며, 조건부 엣지가 answer / not-found 종단 / 0건 시 1회 비필터 재시도로 분기."
- "규칙 기반 디스패치와 1회 bounded 재시도 엣지를 가진 LangGraph 상태 머신을 설계하고, 검증된 검색·생성 모듈을 순수·주입형 노드로 합성."

**유지할 정직 한정어**: "규칙 기반"(지능형 아님), "1회/bounded 재시도"(자가수정 루프 아님), "단일 턴".

**금지 주장(must-NOT-claim)**:
- "멀티에이전트 / 에이전트 협업": 자율 행위자 다수가 아니라 한 그래프의 노드들
- "LLM 기반 라우팅/오케스트레이션": 디스패치는 정규식 + 0건 판정, LLM 호출은 답변 노드 1곳뿐
- "자가수정 / 반복 추론 / agentic 루프": 0건 조건의 정확히 1회 fallback. "단일 fallback 재시도"로만 표기
- "동적 도구 선택": 도구는 retrieve 하나, `where` 필터만 데이터로 달라짐
- 정확도·"최적화" 등 수치 주장(미측정)

---

## 8. 권장 구현 순서

1. **의존성**: `requirements.txt`에 `langgraph>=0.2` 추가(전이 `langchain-core`). 가상환경 설치 확인. → **ADR-005** 작성: "왜 LangGraph인가 = 명시적 제어 흐름 + bounded 재시도 + 향후 확장성"(에이전트 필요가 아님).
2. **`src/graph/state.py`**: `GraphState` TypedDict(§2.5).
3. **`src/graph/nodes.py`**: 5개 노드 + `route_after_retrieve`. retrieval_mode 우선순위 규칙(§2.4) 정확히 구현.
4. **`src/graph/graph.py`**: `build_graph(retriever, client)` 클로저 팩토리 + 엣지(§2.2) + compile.
5. **`src/graph/__init__.py`**: export.
6. **`tests/graph/`**: 노드/그래프 테스트(§5). 먼저 통과시켜 라우팅·재시도·provenance 고정.
7. **`agent/pipeline.py`**: `ask()`를 wrapper로 교체(§2.6), docstring에 자동 필터 동작·`retrieval_mode` 명시. `_to_source` 유지.
8. **`tests/agent/test_pipeline.py`**: 4키 계약 + 2개 회귀 테스트(§5).
9. **전체 `pytest tests/`**: 기존 35 + 신규 통과 확인. 실데이터 스모크 1회(`ask` 필터/fallback/미스 경로).
10. **정직성 점검**: ADR-005·문서·커밋 메시지 서술이 §7 금지 목록을 위반하지 않는지 확인.

---

## 부록 - 합의 메타데이터

- 팀: `design-langgraph-multiagent` (langgraph-architect/opus, integration-reuse/sonnet, honesty-testability-critic/opus, 리드).
- 2라운드(초기 제안 → 교차리뷰 → 수렴). 전원 `[COMPLETE] No further input`.
- 주요 충돌 해소: (i) 4 vs 5노드 → 5노드, (ii) 코드 필드 2개 vs 1개 → 1개+`retried` 플래그, (iii) `not_found` 중복 → status carrier로 정당화, (iv) provenance 래퍼 파생 → 노드 명시 설정 + `retried` 우선순위 고정.
