# ADR-003: LLM·임베딩 스택 Gemini 전환

- **상태(Status)**: 채택(Accepted)
- **날짜**: 2026-06-05
- **관련**: `docs/mvp-plan.md`(§5.1, §5.3, 부록 A9), [ADR-002](ADR-002-cross-reference-rag-redefinition.md)

---

## 배경 (Context)

기획서 §5.3 기술 스택은 **LLM = OpenAI GPT-4o**, **임베딩 = OpenAI text-embedding-3-small(1536d)**로
기재. 또한 기획서 내부에 임베딩 모델이 **5.1(Solar) vs 5.3(OpenAI)** 로 엇갈리는 불일치가
있어(부록 A9) 미확정 가정으로 남아 있던 상태.

재개발 시 아래 이유로 **Gemini 단일 스택**으로 전환.

## 결정 (Decision)

- **LLM**: Gemini (구체 모델은 A6 검증 후 확정)
- **임베딩**: `gemini-embedding-001` (GA) - 출력 **768d 잠정**(MRL truncation). 최종 차원은 A9 검증 후 확정
- **API**: Google AI Studio 단일 키(`GOOGLE_API_KEY`)로 통일

> 임베딩 모델 ID는 **2026-06-05 기준 현행 GA 모델**로 확정했다(현행성 WebSearch 확인). 해당 모델은
> Matryoshka(MRL)를 지원해 768 / 1536 / 3072 차원 중 선택 가능하며, 우선 **768d**로 검증.
> 모델 현행성은 변동 가능하므로 **구현 착수 시 Google AI 공식 문서 재확인** 필요.

## 이유 (Rationale)

1. **단일 API 키** - LLM + 별도 임베딩 혼용 대비 관리 포인트 감소
2. **비용** - Google AI Studio 무료 티어로 검증 비용 최소화
3. **성능** - gemini-embedding-001이 다국어 임베딩에서 상위권으로 알려짐(점검 시점 기준; **A9에서 실측 확인**)
4. **기획서 임베딩 불일치(Solar vs OpenAI, 부록 A9) 해소** - 단일 스택으로 정리

## 영향 (Impact)

- `mvp-plan.md` §5.3 기술 스택 표 수정 (LLM 행·Embedding 행)
- `mvp-plan.md` §5.1 스키마 `embedding` 차원: 1536 → **768 잠정**
- `mvp-plan.md` §5.3 참고 노트(임베딩 모델·차원·Solar/OpenAI 불일치) 갱신
- `.env.example`: `GOOGLE_API_KEY` 추가, `OPENAI_API_KEY` 제거
- **벡터 차원 변경: 1536d → 768d 잠정** - Vector DB 스키마 영향(인덱스·저장 크기)
- 부록 **A9** 검증 범위 재정의: `gemini-embedding-001` 출력 차원(768/1536/3072) 비교

## 미확정 (Open)

- **Gemini LLM 구체 모델** (현행 Gemini Flash/Pro 계열 중) → **A6** 검증 후 결정
- **임베딩 출력 차원 최종값** (768 / 1536 / 3072) → **A9** 검증 후 결정
- **벡터 차원 최종값** → 임베딩 차원 확정에 종속

## 비고 - 검증 우선 원칙 적용

원안 스택(OpenAI)에서 전환하며 임베딩 후보 모델의 **현행성을 먼저 확인**한 결과, 일부 후보가 이미
지원 종료 상태임을 발견하고 현행 GA 모델로 교체해 본 ADR을 확정. "측정·확인된 것만 채택한다"는
프로젝트 원칙(CLAUDE.md)에 따른 절차다.
