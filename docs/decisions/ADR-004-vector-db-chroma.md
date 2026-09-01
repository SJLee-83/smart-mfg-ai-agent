# ADR-004: Vector DB로 Chroma 채택 (pgvector 대신)

- **상태(Status)**: 채택(Accepted)
- **날짜**: 2026-06-05
- **관련**: `docs/mvp-plan.md`(§5.1, §5.3, 부록 A7), [ADR-003](ADR-003-llm-embedding-gemini.md)

---

## 배경 (Context)

기획서 §5.3은 Vector DB로 **PostgreSQL pgvector**를 기재. 이전 해커톤 구현도 pgvector 사용.
재개발 시 **규모·개발 속도·정직성** 기준으로 재검토.

## 결정 (Decision)

**Chroma 채택** (pgvector 대신). 로컬 파일 기반 모드 우선.

## 이유 (Rationale)

1. **규모 불일치** - 예상 청크 200~300개에 pgvector는 과하다. 성능 이점이 실측되지 않는 규모에서
   "관계형+벡터 하이브리드 검색 최적화"를 차별점으로 주장하는 것은 부풀리기다.
2. **로컬 개발 속도** - pgvector는 PostgreSQL 서버·Docker가 필요하다. Chroma는 `pip install` +
   파일 기반으로 즉시 시작 가능. 검증 우선 프로젝트에서 인프라 셋업 비용 최소화.
3. **선택 근거의 명시성** - 이전 레포가 pgvector를 썼으나 실제 장점(대규모·관계형 결합)을 살리지 못함.
   재개발에서는 규모에 맞는 기술 선택 근거를 문서로 남긴다.

## 영향 (Impact)

- `mvp-plan.md` §5.3 Vector DB 행 수정 (선택·선정 이유, 그리고 "대용량" 표현 정리)
- `mvp-plan.md` §5.1 스키마 설계는 **개념적으로 유지** - Chroma도 메타데이터 필터링(`where`)을 지원
- 부록 **A7** 재정의: "pgvector vs Chroma 비교" → Chroma 채택 전제로 **"Chroma 연동 동작 확인"으로 축소**

## 미확정 (Open)

- Chroma 버전, 로컬 vs 클라우드 모드 → **A7** 검증 후 확정
- 향후 규모 확장 시 pgvector 재검토 가능 (**확장성 포기 아님**)

## 검증 (A7 스모크 테스트)

`experiments/a7_vector_db/verify_chroma.py`로 로컬 파일 기반 Chroma 동작을 확인한다:
PersistentClient 생성 → 컬렉션 → 더미 5문서(`error_code`/`content_type` 메타데이터) →
메타데이터 필터(`error_code=SRVO-062`) → 유사도 검색(더미 벡터) → 테스트 DB 정리.
실제 임베딩 모델 없이 더미 벡터로 **메커니즘만** 검증한다(결과: `result_chroma_verify.txt`).
