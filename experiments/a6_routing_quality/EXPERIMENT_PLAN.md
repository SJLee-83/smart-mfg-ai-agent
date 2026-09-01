# A6 실험 설계 - 라우팅 정확도 & 비필터 재시도 오답률 측정

- **상태**: 구현·실행 완료 (2026-06-07). `run_eval.py`/`dataset.jsonl` 작성, 결과는 [docs/validation/A6-routing-quality-eval.md](../../docs/validation/A6-routing-quality-eval.md)
- **작성일**: 2026-06-06
- **관련**: `src/graph/`(상태 머신), `docs/langgraph-multiagent.md` §6, [ADR-005](../../docs/decisions/ADR-005-langgraph-orchestration.md), [ADR-002](../../docs/decisions/ADR-002-cross-reference-rag-redefinition.md)

> 이 문서는 **설계** 문서로 수치 주장 없음(`docs/conventions.md` §2). 실측 결과·해석은 [docs/validation/A6-routing-quality-eval.md](../../docs/validation/A6-routing-quality-eval.md)에 기록.

---

## 1. 실험 목적

`src/graph`의 조건부 라우팅 상태 머신이 도입한 두 동작의 실효성을 **정량 측정**한다:

1. **라우팅이 옳은 가지를 고르는가** - 에러코드 유무에 따른 필터/비필터 검색 분기가 의도대로 작동하는지.
2. **비필터 재시도가 안전한가** - 필터 검색 0건 시 필터를 푸는 fallback(`unfiltered_fallback`)이 "유사하지만 요청과 다른 코드"의 출처로 답변을 생성하는 위험(wrong-code answer)이 얼마나 되는지.

지금까지는 단위/통합 테스트로 **로직의 결정성**만 고정(`tests/graph/`)했고 **실데이터 품질**은 미측정. 이 실험이 그 공백을 대상으로 함.

## 2. 검증 대상 가정

- **A6 (멀티 vs 단일 RAG 품질)** - 기획서 미검증 항목. 조건부 라우팅 + 메타데이터 필터가 단순 단일 검색 대비 실제로 더 정확한 근거를 주는지의 일부를 라우팅 정확도·재시도 오답률로 근사 측정
- 직접적으로는 `docs/langgraph-multiagent.md` §6의 후속 검증 1번(라우팅 정확도)·2번(재시도의 답변 품질 영향)을 다룬다.

## 3. 측정 항목 (메트릭)

### M1. 라우팅 정확도 (routing accuracy)
- 정의: 질의가 **기대한 가지**로 라우팅된 비율.
- 기대 가지 판정: `ask()` 반환의 `retrieval_mode`(또는 그래프 최종 상태)로 관측.
  - 코드 명시 질의 → 기대 `filtered`(해당 코드 청크 존재 시) 
  - 코드 미명시 질의 → 기대 `unfiltered`
  - 존재하지 않는 코드 질의 → 기대 `unfiltered_fallback` 또는 `none`(필터 0건 후 재시도 경로 진입)
- 계산: `정확히 라우팅된 질의 수 / 전체 질의 수`.

### M2. 재시도 오답률 (unfiltered_fallback wrong-code rate)
- 정의: `retrieval_mode == "unfiltered_fallback"`로 답변된 질의 중, **답변 근거(sources)의 error_code가 사용자가 요청한 코드와 불일치**하는 비율.
- 관측: fallback 답변의 `sources[*].error_code` vs 질의의 요청 코드 비교. (요청 코드는 질의 텍스트의 `CODE_RE` 추출값.)
- 보조 관측: 사람 판정으로 "답변이 요청 코드와 무관/오도하는가"(정성)를 병기. M2는 **자동 측정 가능한 근사**이며 최종 위험 판단은 정성 검토로 보완

## 4. 테스트셋 설계 (총 25 질의)

| 구분 | 개수 | 예시 | 기대 라우팅 |
|---|---|---|---|
| A. 코드 명시 | 10 | "SRVO-062 배터리 알람", "SRVO-001 비상정지 어떻게 풀어?" | `filtered` |
| B. 코드 미명시 | 10 | "배터리 방전 알람 해결법", "비상정지가 안 풀려요" | `unfiltered` |
| C. 필터 미스 유발 | 5 | "SRVO-999 알람 조치"(존재하지 않는 코드) | `unfiltered_fallback` 또는 `none` |

설계 원칙:
- A 그룹의 코드는 **인덱싱된 93청크에 실제 존재하는 코드**에서 고른다(필터 적중 보장). 코드 목록은 `chroma_db` 메타데이터에서 추출.
- B 그룹은 A 그룹과 **동일 증상을 코드 없이** 표현해 짝을 이룬다(예: A "SRVO-062 배터리 알람" ↔ B "배터리 방전 알람 해결법"). 라우팅뿐 아니라 검색 품질 비교에도 재활용 가능.
- C 그룹은 형식은 유효하나(`SRVO-\d{3}`) 인덱스에 없는 코드로 fallback 경로를 강제한다 → M2 측정의 핵심 입력.
- 정답 라벨(기대 가지, 요청 코드)은 `dataset.jsonl` 등에 명시 저장.

## 5. 성공 기준

- **M1 라우팅 정확도 ≥ 90%** - 미달 시 orchestrate 규칙(정규식/추출) 보강 검토.
- **M2 재시도 오답률** - **기준치 없음. 측정·문서화가 목적**. 결과에 따라:
  - 높으면 → fallback을 기본 비활성화하거나, 프롬프트 헤징(요청 코드 미일치 고지) 도입을 검증 대상으로 승격(설계 §6 보류 항목).
  - 낮으면 → 현행 fallback 유지 근거로 기록.

## 6. 실행 방법

- `experiments/a6_routing_quality/run_eval.py`로 구현됨. 실행: `.venv/Scripts/python.exe experiments/a6_routing_quality/run_eval.py`.
- 개요: `dataset.jsonl` 로드 → 각 질의에 `agent.pipeline.ask()` 호출 → `retrieval_mode`·`sources` 수집 → M1/M2 집계 → 결과 표 출력(+ `results.json` 저장).
- 비용: 25질의 × (임베딩 1 + LLM 1) 호출. 유료 티어 기준 소액. 캐싱은 선택.
- 주의: 이 실험은 `experiments/`의 PoC. 결과가 의미 있으면 정식 평가 하니스로 승격하고 결과를 `docs/validation/`에 기록

## 7. 한계 (정직 기록)

- 테스트셋 25개는 **소표본**으로 정확도/오답률의 신뢰구간이 넓어 "경향" 수준으로만 해석
- M1의 "기대 가지"는 설계자가 라벨링하므로 라벨 편향 가능. 
- M2 자동 측정은 "출처 코드 불일치"를 프록시로 사용. 코드가 달라도 답변이 유효할 수 있고(관련 알람) 코드가 같아도 답변이 틀릴 수 있어 정성 검토 보완 필수
- A6 전체(멀티 vs 단일 RAG 품질)가 아니라 라우팅·재시도라는 **부분**만 측정
