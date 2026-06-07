# A6 검증 기록 — 라우팅 정확도 & 비필터 재시도 오답률 실측

- **검증 날짜**: 2026-06-07
- **검증 대상(A6 일부)**: `src/graph` 조건부 라우팅 상태 머신의 (1) 라우팅 정확도, (2) 비필터 재시도(`unfiltered_fallback`)의 출처 코드 불일치율
- **관련**: [EXPERIMENT_PLAN.md](../../experiments/a6_routing_quality/EXPERIMENT_PLAN.md)(설계), `experiments/a6_routing_quality/run_eval.py`(실행), [ADR-005](../decisions/ADR-005-langgraph-orchestration.md), `docs/langgraph-multiagent.md` §6
- **상태**: ✅ 측정 완료 — M1 100%, M2 100%(정의상). 단, 두 수치 모두 **해석에 강한 단서**가 붙음(아래 §4)

> 측정 도구: `experiments/a6_routing_quality/run_eval.py` (25질의 `dataset.jsonl`). 검색(쿼리 임베딩+Chroma)은 실제 호출, 답변 생성(LLM)은 스텁 — M1/M2는 `retrieval_mode`·`sources`만 보고 답변 텍스트와 무관하기 때문. 원시 출력: `experiments/a6_routing_quality/result_eval.txt`(gitignore, 재생성 가능).

---

## 1. 테스트셋 (25질의)

| 그룹 | 개수 | 구성 | 기대 라우팅 |
|---|---|---|---|
| A. 코드 명시 | 10 | 인덱스에 **실재하는** SRVO 코드 + 증상 | `filtered` |
| B. 코드 미명시 | 10 | A와 **같은 증상을 코드 없이** 표현(짝) | `unfiltered` |
| C. 필터 미스 | 5 | 형식은 유효하나(`SRVO-\d{3}`) **인덱스에 없는** 코드(007/500/911/998/999) | `unfiltered_fallback` 또는 `none` |

라벨(기대 가지·요청 코드)은 `dataset.jsonl`에 명시 저장. A 그룹 코드는 인덱싱된 93청크(각 코드 1청크)에 존재함을 사전 확인.

## 2. 결과 — M1 라우팅 정확도

| 구분 | 정확도 |
|---|---|
| **전체** | **25/25 = 100%** |
| A_code | 10/10 = 100% |
| B_nocode | 10/10 = 100% |
| C_miss | 5/5 = 100% |

관측 모드 분포: `filtered` 10 · `unfiltered` 10 · `unfiltered_fallback` 5 (`none` 0).

→ EXPERIMENT_PLAN §5 성공 기준(**M1 ≥ 90%**) 충족. 25/25 모두 설계 의도대로 분기.

## 3. 결과 — M2 재시도 오답률

| 항목 | 값 |
|---|---|
| `unfiltered_fallback` 경로 진입 | 5건 (그룹 C 전부) |
| 출처 코드 ≠ 요청 코드 | **5/5 = 100%** |

예: `SRVO-999` 질의 → fallback 출처 `[SRVO-065, SRVO-087, SRVO-062]`(요청 코드와 전부 불일치).

## 4. 해석 (정직 기록 — 수치를 액면 그대로 읽지 말 것)

**M1 = 100%는 "라우팅이 견고하다"가 아니다.** 다음을 함께 읽어야 한다:

- 라우팅은 **규칙 기반**(`CODE_RE` 정규식 + 0건 판정)이고 결정적이다. 이 테스트셋은 입력이 **깨끗**하다 — A/C는 항상 `SRVO-NNN`을 정확한 형식으로 포함, B는 코드 토큰이 전혀 없음. 따라서 100%는 "**정상 형식 입력에서 분기가 설계대로 동작**"을 확인한 것이지, 변형 입력 견고성을 입증한 게 아니다.
- **미검증 입력**: 공백/오타 코드(`SRVO 062`, `srvo-062` 소문자), 오타, 코드가 문장 중간에 비정형으로 박힌 경우 — `CODE_RE`(`SRVO-\d{3}`, 대문자·하이픈 고정)는 이들을 놓칠 수 있다. 이 실험은 그 경계를 건드리지 않았다.
- 25개는 **소표본**이고 라벨은 설계자가 부여 — 라벨 편향 가능(EXPERIMENT_PLAN §7).

**M2 = 100%는 "재시도가 위험하다"의 직접 증거가 아니다 — 정의상 결과다.**

- 이 시스템에서 `unfiltered_fallback`은 **필터 검색이 0건일 때만** 발생한다. 메타데이터는 **정확 일치**이고 각 코드는 정확히 1청크이므로, 필터 0건 = **요청 코드가 인덱스에 없음**과 동치다.
- 즉 fallback이 도는 모든 경우는 "요청 코드가 코퍼스에 부재"이므로, 비필터 재검색이 돌려주는 출처가 요청 코드와 일치하는 것은 **구조적으로 불가능**하다. **M2 = 100%는 측정이라기보다 정의의 귀결**이다.
- 따라서 이 100%는 "fallback 답변 5건이 모두 품질 불량"을 뜻하지 않는다. M2는 EXPERIMENT_PLAN §3·§7이 명시한 대로 **자동 프록시**일 뿐이며, 코드가 달라도 의미상 관련 알람일 수 있다(정성 검토 영역).

**부수 관측(별도 미측정 축)**:
- `none` 가지는 한 번도 도달하지 않았다. 비필터 검색은 컬렉션이 비어있지 않는 한 항상 최근접 이웃을 반환하므로, **현 데이터에서 `none`은 사실상 도달 불가**(컬렉션 공집합일 때만 발생).
- B 그룹에서 비필터 검색의 top-1이 짝 코드와 다른 경우가 일부 있었다(예: B01 짝=SRVO-001, 출처=`[SRVO-002, SRVO-001, SRVO-003]`). 이는 **라우팅이 아니라 검색 품질**의 문제로, 이 실험의 측정 대상이 아니다(일화적 관찰).

## 5. 설계 함의 (후속 검증 대상으로 승격)

- **존재하지 않는 코드 처리**: 현재는 무관한 최근접 코드로 답변하고 `unfiltered_fallback` 라벨로만 경고한다. "매뉴얼에 없는 코드"임을 **명시 고지**하거나 `none`으로 끊는 편이 더 안전할 수 있다 → 프롬프트 헤징 또는 라우팅 보강을 검증 대상으로(EXPERIMENT_PLAN §5, langgraph-multiagent §6 보류 항목).
- **라우팅 견고성**: ✅ 측정·수정 완료 — §7 참조(소문자 버그 발견 → `IGNORECASE`+정규화 수정 → 9/9).
- M1 충족으로 orchestrate 규칙 보강은 **현 시점 불요**(정상 입력 기준).

## 6. 비고 (보안·정직성)

- `GOOGLE_API_KEY`는 `.env`(git-ignored)에서만 로드, 출력·커밋 안 함. 임베딩 25회 호출(유료 티어 소액), LLM 0회.
- 이 측정은 **라우팅·출처**까지다. **답변 품질**(생성문 정확성·안전성)과 **검색 정확도**(올바른 청크 회수)는 별개 미검증 축이다. "라우팅이 의도대로 분기함"과 "답변/검색이 정확함"을 구분한다.

## 7. 후속 측정 — 변형 입력 라우팅 견고성 (2026-06-07)

§4·§5에서 "M1 100%는 정상 형식 입력 한정"이라 적은 한계를 직접 측정했다. 도구: `experiments/a6_routing_quality/run_robustness_eval.py`(9케이스, 검색 실호출·답변 스텁). 측정 중 **소문자 입력 버그를 발견·수정**했다.

### 수정 전: 7/9 PASS

FAIL 2건 모두 **소문자 입력**:

| 입력 | 기대 | 실제(수정 전) |
|---|---|---|
| `srvo-062 배터리 알람` | filtered | **unfiltered** |
| `srvo062 배터리` | filtered | **unfiltered** |

원인: `CODE_RE = SRVO-\d{3}`가 **대소문자 구분 + 하이픈 필수**라 소문자/하이픈 누락 코드를 미감지 → `effective_code=None` → unfiltered. **크래시는 없으나 필터 검색 이점을 조용히 상실.**

### 수정: `CODE_RE` 관대화 + 정규화

```python
# src/parsing/constants.py
CODE_RE = re.compile(r"SRVO-?\d{3}", re.IGNORECASE)   # 대소문자·하이픈 누락 허용
def canonical_code(text): ...                         # 감지 코드 → "SRVO-NNN" 정규형
# src/graph/nodes.py orchestrate: code = canonical_code(match.group(0))
```

**중요(정직 기록): `re.IGNORECASE` 추가만으로는 9/9가 불가능**했다(실측 확인). 소문자로 매칭해도 매칭 텍스트가 소문자 그대로면 메타데이터 필터(대문자 저장)가 빗나가 `unfiltered_fallback`이 된다. 따라서 (1) 정규식 IGNORECASE + 선택적 하이픈, (2) `canonical_code()`로 감지 코드를 `SRVO-NNN` 정규형으로 변환하는 두 단계를 모두 거쳐야 `filtered`가 된다.

### 수정 후: 9/9 PASS

| 케이스 | 수정 전 | 수정 후 |
|---|---|---|
| 소문자 2건 (`srvo-062`, `srvo062`) | FAIL (unfiltered) | **PASS (filtered)** |
| 오타 2건 (`SRVO-06 2` 공백, `SRV0-062` O→0) | PASS (unfiltered) | PASS |
| 별칭/증상 2건 (`BZAL`, `배터리 방전`) | PASS (unfiltered) | PASS |
| 코드만 2건 (`SRVO-062`, `SRVO-105`) | PASS (filtered) | PASS |
| 복수코드 1건 (첫 코드 감지) | PASS (filtered) | PASS |

기존 pytest **61 → 63개 통과**(orchestrate 정규화 회귀 테스트 2개 추가, 기존 테스트 무회귀).

### 한계 (정직 기록)

- **오타는 여전히 미복구**(의도된 설계): `SRVO-06 2`(공백 삽입)·`SRV0-062`(O→0)는 unfiltered로 빠진다. 오타 교정은 구현하지 않았다 — 다만 이들은 "엉뚱한 코드로 오인하지 않고 일반 검색으로 폴백"하므로 **안전한 실패**다.
- **별칭→코드 매핑 미구현**: `BZAL`(SRVO-062 알람 약어) 같은 별칭은 코드로 해석되지 않고 의미 검색(unfiltered)에 의존한다. 별칭 사전은 없음.
- 9케이스는 **소표본** — 모든 변형(다국어 혼용, 코드 다중 표기 등)을 망라하지 않는다.
- 원시 출력: `experiments/a6_routing_quality/result_robustness.txt`(gitignore: `result_*.txt`).
