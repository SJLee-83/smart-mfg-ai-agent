# 스마트 제조 AI Agent — FANUC 설비 에러 진단

> **FANUC R-30iA Mate Controller 유지보수 매뉴얼 기반 RAG + LangGraph 상태 머신으로 설비 에러를 진단하고 한국어 수리 가이드를 생성하는 AI 에이전트**

작업자가 설비 알람 코드(예: `SRVO-062`)나 증상을 자연어로 물으면, 매뉴얼 근거를 검색해 **안전 주의사항을 우선한 한국어 조치 가이드**를 출처와 함께 생성한다.

---

## 주요 특징 (검증된 것만)

- **구조화 청킹** — PDF에서 `(Explanation)`/`(Action)` 마커를 기준으로 **SRVO 1코드 = 1청크**로 분할. 실측 매뉴얼 261페이지에서 마커 일관성 ~80%(`(Explanation)` 79.6%, `(Action)` 81.6%) 확인 후 채택([ADR-002](docs/decisions/ADR-002-cross-reference-rag-redefinition.md)). 결과: 261p → **93청크**.
- **벡터 검색** — `gemini-embedding-001`(768d) 임베딩 + **Chroma** 로컬 벡터 DB. 93청크 인덱싱 완료. 에러코드·페이지 등 메타데이터 동반 저장으로 필터 검색 지원.
- **LangGraph 조건부 라우팅** — 질의에서 에러코드를 **규칙 기반(정규식)으로 자동 감지** → 코드가 있으면 메타데이터 필터 검색, 없으면 일반 검색. **필터 검색 0건 시 필터를 풀고 1회 재시도(bounded retry)**, 그래도 0건이면 LLM 호출 없이 조기 종료. ([설계](docs/langgraph-multiagent.md), [ADR-005](docs/decisions/ADR-005-langgraph-orchestration.md))
- **LLM 답변** — `gemini-2.5-flash`로 매뉴얼 발췌에 근거한 **한국어 안전 우선 수리 가이드** 생성. 답변과 함께 출처(error_code·page·검색 모드) 반환.
- **테스트** — 단위·통합 테스트 **61개 통과**. 각 그래프 노드는 의존성 주입으로 독립 테스트.

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

> LLM(`gemini-2.5-flash`)·임베딩 모델은 비용/속도 균형 기준의 **잠정 선택**이며 정량 비교(A6)는 후속 검증 대상이다.

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

검증 기록은 `docs/validation/`, 아키텍처 의사결정은 `docs/decisions/`(ADR), PoC는 `experiments/`.

---

## 실행 방법

### 1. 환경 설정

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (bash: source .venv/Scripts/activate)
pip install -r requirements.txt
```

`.env` 파일을 만들고(`copy .env.example .env`) 아래 값을 채운다:

```
GOOGLE_API_KEY=<Google AI Studio 키>      # 임베딩·LLM 호출용
MANUAL_PDF_PATH=data/raw/R30iA-Mate-Controller-Maintenance-Manual.pdf
```

> 매뉴얼 PDF는 저작권 문제로 repo에 포함하지 않는다 — `data/raw/`에 직접 배치한다.
> 인덱싱은 임베딩 API를 다량 호출하므로 무료 티어 일일 쿼터에 막힐 수 있다(유료 티어 권장).

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

DACON 스마트 제조 AI 해커톤 **본선 진출 결과물의 개념을 계승**해, 프로덕션 수준으로 **새로 구현**한 프로젝트다(기존 코드는 가져오지 않음). 핵심 원칙은 **검증 우선**:

```
기획서 가정 → experiments/ PoC 검증 → 통과분만 src/ 정식 구현
                                   → 실패 시 docs/validation/ 에 사유·대안 기록 + 기획 수정
```

기획서의 "Cross-Reference RAG"는 실측에서 근거 데이터가 희소함을 확인하고 **마커 기반 청킹 + 메타데이터 필터링**으로 재정의했다([ADR-002](docs/decisions/ADR-002-cross-reference-rag-redefinition.md)) — 검증으로 가정을 기각·수정한 사례.

---

## 정직성 고지

포트폴리오로서 **구현·검증한 것과 아직 측정하지 않은 것을 구분**한다.

- 이 시스템은 **규칙 기반 조건부 라우팅 상태 머신**이다. LLM이 라우팅하지 않으며(라우팅은 정규식+0건 판정), 단일 턴·무상태다. "멀티에이전트/자율 에이전트"가 아니다.
- **미검증(후속 과제)**: 라우팅 정확도, 비필터 재시도가 답변 품질에 주는 영향(엉뚱한 코드 답변 위험률), 답변 품질 정량 평가, LLM/임베딩 모델 비교(A6). 정량 수치는 측정 후에만 주장한다.
- 비필터 재시도로 얻은 답변은 `retrieval_mode="unfiltered_fallback"`로 표기되며, 요청 코드와 다른 출처일 수 있으니 `sources`의 `error_code`로 교차확인할 것.
