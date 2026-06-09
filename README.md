# 스마트 제조 AI Agent — FANUC 설비 에러 진단

> **FANUC R-30iA Mate Controller 유지보수 매뉴얼 기반 RAG + LangGraph 상태 머신으로 설비 에러를 진단하고 한국어 수리 가이드를 생성하는 AI 에이전트**

작업자가 설비 알람 코드(예: `SRVO-062`)나 증상을 자연어로 물으면, 매뉴얼 근거를 검색해 **안전 주의사항을 우선한 한국어 조치 가이드**를 출처와 함께 생성합니다.

---

## 주요 특징 (검증된 것만)

- **구조화 청킹** — PDF에서 `(Explanation)`/`(Action)` 마커를 기준으로 **SRVO 1코드 = 1청크**로 분할합니다. 실측 매뉴얼 261페이지에서 마커 일관성 ~80%(`(Explanation)` 79.6%, `(Action)` 81.6%)를 확인한 뒤 채택했습니다([ADR-002](docs/decisions/ADR-002-cross-reference-rag-redefinition.md)). 결과는 261p → **93청크**입니다.
- **벡터 검색** — `gemini-embedding-001`(768d) 임베딩과 **Chroma** 로컬 벡터 DB를 사용합니다. 93청크 인덱싱을 마쳤고, 에러코드·페이지 등 메타데이터를 함께 저장해 필터 검색을 지원합니다.
- **LangGraph 조건부 라우팅** — 질의에서 에러코드를 **규칙 기반(정규식)으로 자동 감지**해, 코드가 있으면 메타데이터 필터 검색을, 없으면 일반 검색을 수행합니다. **필터 검색이 0건이면 필터를 풀고 1회 재시도(bounded retry)**하며, 그래도 0건이면 LLM 호출 없이 조기 종료합니다. ([설계](docs/langgraph-multiagent.md), [ADR-005](docs/decisions/ADR-005-langgraph-orchestration.md))
- **LLM 답변** — `gemini-2.5-flash`로 매뉴얼 발췌에 근거한 **한국어 안전 우선 수리 가이드**를 생성합니다. 답변과 함께 출처(error_code·page·검색 모드)를 반환합니다.
- **테스트** — 단위·통합 테스트 **61개를 통과**했습니다. 각 그래프 노드는 의존성 주입으로 독립적으로 테스트합니다.

---

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 언어 | Python 3.12 |
| 그래프 오케스트레이션 | LangGraph 1.2 (`StateGraph`, 조건부 라우팅) |
| LLM·임베딩 | google-genai (Gemini: `gemini-2.5-flash`, `gemini-embedding-001`) |
| PDF 파싱 | pdfplumber |
| 벡터 DB | ChromaDB (로컬 파일 기반) |
| 테스트 | pytest |

> LLM(`gemini-2.5-flash`)·임베딩 모델은 비용/속도 균형 기준의 **잠정 선택**이며, 정량 비교(A6)는 후속 검증 대상입니다.

---

## 프로젝트 구조

```
src/
├── parsing/    # PDF 로드·노이즈 제거 → 마커 기반 SRVO 청킹 → 메타데이터 태깅 (→ Chunk)
├── index/      # Chunk 임베딩(gemini-embedding-001) + Chroma 적재 파이프라인
├── retrieval/  # 쿼리 임베딩 + Chroma 유사도 검색(에러코드 메타데이터 필터)
├── agent/      # LLM 답변 생성(gemini-2.5-flash, 안전 우선 프롬프트) + ask() 진입점
└── graph/      # LangGraph 조건부 라우팅 상태 머신(검색→답변 오케스트레이션 + 재시도)
```

검증 기록은 `docs/validation/`, 아키텍처 의사결정은 `docs/decisions/`(ADR), PoC는 `experiments/`에 있습니다.

---

## 구현 노트

- **RAG 파이프라인** — 파싱(PDF → 청크) → 인덱싱(`gemini-embedding-001` 임베딩 + Chroma 적재) → 검색(쿼리 임베딩 + 에러코드 메타데이터 필터) → 답변 생성(`gemini-2.5-flash`)의 단계를 직접 구성했습니다. 이 흐름과 재시도·조기 종료는 LangGraph 상태 머신으로 묶었고, 외부 진입점은 `ask()`(`src/agent/pipeline.py`) 하나입니다.
- **의존성 주입 + 테스트** — `ask()`와 `build_graph()`가 검색기(`Retriever`)와 LLM 클라이언트를 인자로 받도록 설계했습니다(`make_retrieve`/`make_answer` 클로저 팩토리로 노드에 주입). 실제 실행에서는 기본 객체를 생성하고, 테스트에서는 가짜 검색기·클라이언트를 주입해 Chroma·Gemini를 호출하지 않고 각 노드를 독립적으로 검증합니다. 라우팅 분기 같은 순수 함수는 그대로 단위 테스트해, 단위·통합 합계 61개를 구성했습니다.

---

## 실행 방법

### 1. 환경 설정

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (bash: source .venv/Scripts/activate)
pip install -r requirements.txt
```

`.env` 파일을 만들고(`copy .env.example .env`) 아래 값을 채웁니다:

```
GOOGLE_API_KEY=<Google AI Studio 키>      # 임베딩·LLM 호출용
MANUAL_PDF_PATH=data/raw/R30iA-Mate-Controller-Maintenance-Manual.pdf
```

> 매뉴얼 PDF는 저작권 문제로 repo에 포함하지 않으므로 `data/raw/`에 직접 배치합니다.
> 인덱싱은 임베딩 API를 다량 호출하므로 무료 티어 일일 쿼터에 막힐 수 있습니다(유료 티어 권장).

### 2. 인덱싱 (PDF → 파싱 → 임베딩 → Chroma 적재)

```python
import sys; sys.path.insert(0, "src")
from index.pipeline import run_indexing

run_indexing(persist_dir="chroma_db")   # .env의 MANUAL_PDF_PATH 사용
```

### 3. 질의 (검색 → 한국어 수리 가이드 생성)

```python
import sys; sys.path.insert(0, "src")
from agent.pipeline import ask

result = ask("SRVO-062 배터리 알람이 떴어. 어떻게 해야 해?")
print(result["answer"])           # 한국어 안전 우선 수리 가이드
print(result["retrieval_mode"])   # filtered | unfiltered | unfiltered_fallback | none
print(result["sources"])          # [{error_code, page_no, parsed_by}, ...]
```

### 테스트

```bash
pytest tests/ -v
```

---

## 개발 배경

DACON 스마트 제조 AI 해커톤 **본선 진출 결과물의 개념을 계승**해, 프로덕션 수준으로 **새로 구현**한 프로젝트입니다(기존 코드는 가져오지 않았습니다).

해커톤 당시에는 빠른 프로토타입을 위해 Cross-Reference RAG가 가능한 일부 데이터만으로 개발해 매뉴얼 전체를 반영하지 못했고, 기술 검증 없이 LLM에 기댄 기획이었습니다. 완성도와 기술 이해를 함께 끌어올리기 위해 처음부터 다시 구현했고, 핵심 원칙은 **검증 우선**으로 두었습니다:

```
기획서 가정 → experiments/ PoC 검증 → 통과분만 src/ 정식 구현
                                   → 실패 시 docs/validation/ 에 사유·대안 기록 + 기획 수정
```

---

## 측정 결과

정량 수치는 실제 측정한 것만 적었습니다. 자세한 기록은 `docs/validation/`에 있습니다.

- **라우팅 정확도** — 25질의 클린 테스트셋에서 **25/25(100%)**가 설계 의도대로 분기했습니다([검증 기록](docs/validation/A6-routing-quality-eval.md)). 라우팅은 규칙 기반·결정적이고 입력이 정상 형식이므로, 이 수치는 "정상 입력에서 분기가 설계대로 동작"함을 뜻하며 변형 입력 견고성과는 별개입니다.
- **변형 입력 견고성** — 9케이스 측정 중 소문자 입력 버그를 발견·수정(`CODE_RE`에 `IGNORECASE`+하이픈 선택 + 정규화)해 **9/9**가 되었습니다([검증 기록 §7](docs/validation/A6-routing-quality-eval.md)).

---

## 한계

- **단일 턴·무상태**의 규칙 기반 조건부 라우팅 구조입니다. LLM이 라우팅을 판단하지 않으며(정규식 + 0건 판정), 자율 에이전트나 멀티에이전트는 아닙니다.
- 답변 품질 정량 평가, 검색 정확도(올바른 청크 회수), LLM·임베딩 모델 비교(A6 나머지)는 아직 측정하지 않았습니다. 정량 수치는 측정한 뒤에만 적을 계획입니다.
- 오타 교정·별칭(`BZAL`→코드) 매핑은 미구현입니다(의도된 안전 폴백). 비필터 재시도(`unfiltered_fallback`)로 얻은 답변은 요청 코드와 다른 출처일 수 있어, `sources`의 `error_code`로 교차확인해야 합니다.

---

## 배운 점

- **기술 검증을 먼저 하고 개발한다** — 해커톤 때는 시간이 부족해 매뉴얼 일부 데이터만 보고 Cross-Reference RAG가 실제로 동작하는지 확인하지 않은 채 진행했습니다. 이번에 다시 개발하면서, 기술 가정을 먼저 검증하고 들어가야 개발 도중 터지는 문제가 줄어든다는 걸 체감했습니다(그 결과가 [ADR-002](docs/decisions/ADR-002-cross-reference-rag-redefinition.md)의 가정 기각·재정의입니다).
- **LLM에 맡길 일과 규칙으로 둘 일을 나눈다** — 앞서 AI-SkinView 챗봇을 개발하면서 LLM이 정해둔 규칙대로만 움직이지 않고 임의로 동작할 수 있다는 걸 겪었습니다. 그래서 라우팅은 LLM이 아니라 규칙 기반(정규식 + 0건 판정)으로 두었고, 검색 결과가 0건이면 어차피 쓸 근거가 없으니 LLM을 호출하지 않아 불필요한 비용도 줄였습니다.
- **처음 써본 기술을 실제로 적용해봤다** — RAG 파이프라인을 직접 구성하고, 의존성 주입으로 각 노드를 독립 테스트하는 방식을 이 프로젝트에서 처음 적용했습니다(적용 방식은 위 [구현 노트](#구현-노트) 참고).
