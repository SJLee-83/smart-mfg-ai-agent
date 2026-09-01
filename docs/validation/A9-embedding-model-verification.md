# A9 검증 기록 - 임베딩 모델(gemini-embedding-001) 호출·차원 확인

- **검증 날짜**: 2026-06-05
- **검증 대상(A9)**: `gemini-embedding-001` 호출 가능 여부 및 출력 차원 확인
- **관련**: [ADR-003](../decisions/ADR-003-llm-embedding-gemini.md) (Gemini 임베딩, 768d 잠정)
- **상태**: 완료. 모델 호출 가능, 차원 확정(**768d**)

---

## 결과

| 항목 | 값 |
|---|---|
| 호출 결과 | **성공** |
| 출력 차원 | **768** (`output_dimensionality=768`, MRL truncation 동작) |
| 입력 | `"SRVO-062 BZAL alarm battery zero"` (비민감 테스트 문자열) |
| first3 (참고) | `[0.04967, -0.00515, 0.00827]` |

→ ADR-003의 "gemini-embedding-001, 출력 768d 잠정"이 **실제로 호출 가능**함을 실측 확인.
MRL 768 truncation이 정상 동작하므로 Vector(768) 스키마 전제가 유효.

## 사용 SDK

| 용도 | SDK | 버전 | 비고 |
|---|---|---|---|
| 검증(1차) | `google-generativeai` | 0.8.6 | **폐기됨(deprecated)** - import 시 지원종료 경고. 검증용으로만 사용 |
| 검증(2차) + 실제 구현 | **`google-genai`** (신 SDK) | 2.8.0 | `from google import genai` / `client.models.embed_content(...)`. 본 구현에 사용 |

- **두 SDK 결과 일치**: 신·구 SDK 모두 first3 = `[0.04967, -0.00515, 0.00827]`로 동일 → 같은 모델, 결정적 출력 확인.
- **실제 `src/index/` 임베딩 모듈은 `google-genai`(신 SDK)로 구현**. 폐기된 `google-generativeai`는 `requirements.txt`에 미포함(폐기 모델/SDK를 본 구현에 올리지 않는다는 ADR-003 원칙과 동일)

## 비고 (보안·정직성)

- `GOOGLE_API_KEY` 유효 확인. 키는 `.env`(git-ignored)에만 보관, 출력·커밋 안 함. 검증 임시 스크립트·출력은 실행 후 삭제.
- 이 검증 범위는 **"호출 가능 + 차원"**까지. 임베딩 **품질**(검색 정확도)은 별도 측정 대상(A4 메타데이터 필터링·검색 평가와 함께)으로 아직 미검증이며, "임베딩 동작 확인"과 "검색 정확도 검증"은 구분
