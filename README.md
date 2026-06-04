# 스마트 제조 AI Agent (재개발)

> DACON 스마트 제조 AI 해커톤 결과물의 개념을 계승하여 프로덕션 수준으로 재개발하는 프로젝트

---

## 개요

RAG 기반 멀티에이전트 스마트 제조 AI Agent. 기존 해커톤 코드는 가져오지 않고 **개념만 계승하여 새로 구현**한다.

현재 출발점은 MVP 기획서 1부이며, **기획서의 기술적 가정을 먼저 검증한 뒤 검증 통과분만 본 구현**하는 검증 우선 방식으로 진행한다.

---

## 폴더 구조

| 폴더 | 용도 |
|---|---|
| `docs/mvp-plan.md` | MVP 기획서 (검증 대상) |
| `docs/validation/` | 기획 가정 검증 기록 (성공·실패 모두) |
| `docs/decisions/` | 아키텍처 의사결정 기록 (ADR) |
| `experiments/` | 기획 가정 검증용 PoC 코드 (버려도 되는 코드) |
| `src/` | 검증 통과한 것만 정식 구현 |

---

## 작업 흐름

```
기획서 가정 → experiments/ PoC 검증 → 성공 시 src/ 정식 구현
                                    → 실패 시 docs/validation/ 기록 + 기획 수정
```

---

## 기술 스택

- Python 3.11+
- LangGraph (멀티에이전트 오케스트레이션)
- LangChain (LLM 연동)
- RAG (vector store — 구체 구현은 검증 후 결정)

---

## 개발 환경 설정

```bash
# 가상환경 생성·활성화 (Windows)
python -m venv .venv
.venv\Scripts\activate

# 의존성 설치 (requirements.txt 작성 후)
pip install -r requirements.txt

# 환경변수 설정
copy .env.example .env
# .env 파일에 API 키 입력
```

---

## 주의

- API 키·제조 데이터는 `.env`에 (git ignored). 커밋 전 시크릿 노출 점검
- 검증 안 된 기획 가정을 사실로 다루지 않음
