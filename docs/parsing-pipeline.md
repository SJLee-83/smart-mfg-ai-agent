# 설계 문서: `src/parsing/` 파싱 파이프라인

> design-parsing-pipeline 팀(다관점 검토) 종합 결과 - 2026-06-05
> 검토 방식: lead(퍼실리테이터) + 전문가 3명(parser-core/api-design/domain-rag), 2라운드 제안→교차리뷰→수렴
> 근거 자료: `experiments/a2_pdf_parsing/` (result_explore.txt p.53/81/227, result_srvo_analysis.txt), `docs/validation/A2-pdf-parsing-explore.md`, ADR-002/003/004, `docs/mvp-plan.md` §5

---

## 0. 범위와 전제

- **스코프**: `pdf_loader → chunk_parser → metadata_tagger → list[Chunk]`까지. 임베딩(gemini-embedding-001)·Chroma 적재는 **별도 모듈**(예: `src/index/`).
- **이 프로젝트의 첫 `src/` 코드** - 기존 src 관례 없음, 패키징도 이번에 수립.
- experiments PoC를 참고하되 **프로덕션 품질로 재작성**(타입힌트·docstring·독립 테스트).

---

## 1. 합의된 아키텍처

### 1.1 모듈 레이아웃

```
src/parsing/
├── __init__.py        # 공개 export만
├── constants.py       # 정규식, severity 키워드, content_type 리터럴
├── models.py          # PageText, RawChunk, Chunk (3개 dataclass 한 곳)
├── pdf_loader.py      # load_pages() -> list[PageText]   (유일한 I/O + 헤더/푸터 제거)
├── chunk_parser.py    # parse() -> list[RawChunk]        (순수함수)
└── metadata_tagger.py # tag() -> list[Chunk]             (순수함수)

tests/parsing/
├── fixtures/
│   ├── page_81_markers.txt    # 골든: 마커 정상 페이지
│   └── page_53_fallback.txt   # 골든: 마커 없는 폴백 페이지
├── test_pdf_loader.py
├── test_chunk_parser.py
└── test_metadata_tagger.py
```

- 3개 dataclass를 단일 `models.py`에 둔다 → tagger가 RawChunk·Chunk를 모두 import할 때 순환참조 방지.
- `__init__.py`는 `PageText/RawChunk/Chunk`, `load_pages/parse/tag`만 export.

### 1.2 데이터 흐름

```
MANUAL_PDF_PATH(env)
   │  load_pages()  ── pdfplumber, 헤더/푸터 strip ──►  list[PageText]
   ▼
parse()  ── 전체 페이지 연결(경계 추적) → "(N) SRVO-NNN" 경계로 분할 → 마커/폴백 파싱 ──►  list[RawChunk]
   ▼
tag()  ── content_type/severity/related_codes 직렬화 + ID 부여 ──►  list[Chunk]
   ▼
(다음 모듈) 임베딩 → Chroma upsert
```

원칙: **I/O는 pdf_loader 전담.** `parse`·`tag`는 입력→출력 순수함수(파일·env·네트워크 접근 금지) → PDF 없이 인라인 문자열로 단위 테스트 가능.

### 1.3 데이터 모델 (`models.py`)

```python
@dataclass(frozen=True)
class PageText:
    page_no: int          # 1-based
    text: str             # 헤더/푸터 제거된 본문

@dataclass                 # 가변(파서가 점진 구성). __post_init__로 error_code 형식 검증
class RawChunk:
    error_code: str | None   # "SRVO-094" | None(폴백·코드 미검출)
    content: str             # 헤더(코드+title)줄 포함한 전체 블록 = 임베딩 대상 텍스트
    page_no: int             # 코드가 '시작'한 페이지
    title: str | None        # 헤더에서 "(N) " 제거한 코드+제목 (앵커 용어). 폴백 시 None 가능
    explanation: str | None  # (Explanation) 본문. 폴백 시 None
    actions: list[str]       # (Action 1..N) 단계들. 폴백 시 []
    related_codes: list[str] # 블록 내 (SRVO-NNN) 교차참조(자기코드 제외). 없으면 []
    parsed_by: str           # "marker" | "fallback"

@dataclass(frozen=True)
class Chunk:                 # Chroma 적재 단위
    id: str
    content: str
    metadata: dict           # 아래 1.4 스키마 (값은 str/int만)
```

### 1.4 `Chunk.metadata` 스키마 (최종 6키, Chroma 스칼라 한정)

| 키 | 타입 | 값 도메인 |
|---|---|---|
| `error_code` | str | `"SRVO-NNN"` 또는 `""` |
| `page_no` | int | 1–261 (출처/인용용) |
| `content_type` | str | `"TROUBLESHOOTING"` (상수 - 결정 C, 스코프 seam) |
| `severity_hint` | str | `"HIGH"` / `"MEDIUM"` / `"UNKNOWN"` (결정 D 변경, 기본 UNKNOWN) |
| `parsed_by` | str | `"marker"` / `"fallback"` (80/20 폴백 감사용) |
| `related_codes` | str | comma-join SRVO 코드, 없으면 `""` (휴면 데이터) |

- `title`도 `metadata`에 `str`로 노출(`None`이면 `""`). 단 **content에도 포함**(아래 2.6 앵커링).
- 모든 값은 str/int (float/bool/list/None 없음) → Chroma `where` 호환.
- `models.py`에 `TypedDict`로 문서화(런타임 강제 아님), 실제 필드 타입은 `dict` 유지.

### 1.5 인터페이스

```python
def load_pages(pdf_path: Path | None = None) -> list[PageText]: ...
def parse(pages: list[PageText]) -> list[RawChunk]: ...
def tag(chunks: list[RawChunk]) -> list[Chunk]: ...
```

---

## 2. 주요 결정사항과 근거

### 2.1 결정 A (content_type 충돌 해소: 필드 분리) - **승인**
파서는 구조를 `explanation`/`actions`/`title` 필드로, `content_type`(TROUBLESHOOTING/SAFETY)은 tagger의 메타데이터로. 서로 직교한 관심사라 한 필드명에 혼합 금지. (3인 합의)

### 2.2 결정 B (1 SRVO 코드 = 1 청크) - **승인**
- **중요 정정**: 마커는 페이지당이 아니라 **코드당** 1회. p.81 한 페이지에 5개 코드(094/095/096/097/105), 각자 (Explanation)/(Action). 49 SRVO 페이지에 105 고유코드 → 평균 2–3 코드/페이지. "1코드=1청크"는 **페이지를 코드 헤더로 분할**한다는 뜻.
- 근거: "SRVO-105 도어 열림 해결" 질의는 원인+조치가 **한 청크**에 있어야 완결. 액션 분할은 답을 파편화하고 ADR-002가 없앤 재조합 복잡도를 되살림. 블록 크기 실측 ~15–120단어(≈150토큰)로 임베딩 한계(2048) 13배 여유. 200–300청크 규모(ADR-004)에도 적합.

### 2.3 결정 C (SAFETY 파싱 스코프 제외) - **승인 + 정직성 명시**
- 이 파이프라인은 **TROUBLESHOOTING만**. `content_type`은 상수 `"TROUBLESHOOTING"`(현재 필터값 0, 향후 SAFETY 챕터 적재 시 판별 필드가 되는 forward-compat seam - 비용 ~0).
- **정직성**: SAFETY PRECAUTIONS 챕터 미적재. mvp-plan의 "Safety Agent"(§3.1, §6 SRVO-062 5단계, 기능3)는 **미구현 기능**이므로 구현된 것처럼 표현 금지 → 별도 문서 정리(3.4 후속).

### 2.4 결정 D (severity) - **변경: 기본값 UNKNOWN (사용자 사인오프 필요)**
- **원안**: WARNING→HIGH, CAUTION→MEDIUM, **기본 MEDIUM**.
- **변경안(팀 권장)**: 값 `{HIGH, MEDIUM, UNKNOWN}`, **기본 UNKNOWN**. 매핑 `WARNING/DANGER→HIGH`, `CAUTION/NOTE→MEDIUM`, 키워드 없음→`UNKNOWN`. 동시 등장 시 HIGH 우선.
- **근거**: "기본 MEDIUM"은 없는 심각도를 **날조** → `where severity=MEDIUM` 필터가 무키워드 청크와 진짜 MEDIUM을 섞음. UNKNOWN은 "표기된 심각도 미검출"을 정직하게 보존(비용 0). `docs/conventions.md` §2 "측정한 것만 주장" 부합.
- **정직성 기록(필수 동반)**: *"severity는 안전고지어(WARNING/CAUTION) 기반 키워드 휴리스틱이며, 매뉴얼의 네이티브 알람 심각도(STOP/SERVO/WARN/PAUSE…)가 아니다. 정밀도 미검증(A5 관련). 표기는 '키워드 기반 severity 태거, 정밀도 미측정'."*
- **확정(2026-06-05, 사용자 사인오프)**: 필드명 = **`severity_hint`**, 기본값 = **UNKNOWN**. 이름 자체가 휴리스틱임을 표시. 키워드셋은 미검증(A5)이라 `constants.py`에 "preliminary" 주석.

### 2.5 청킹 경계: 구조적 "(N) SRVO-NNN" 키 - **하드코딩 없는 p.227/p.53 배제**
- 경계 정규식 `^\s*\((?P<item>\d{1,4})\)\s+(?P<code>SRVO-\d{3})\b...` (행 선두 "(N) " 항목번호 + **괄호 없는** 코드).
- 이것이 **정의(definition)** 신호. 결과:
  - **괄호 교차참조 `(SRVO-072)`** → 코드가 괄호 안이라 경계 매칭 불가 → 블록 분할 없음
  - **p.53(알람이력 UI)**: 코드가 `2 SRVO-002`처럼 괄호 없는 리스트인덱스 → 0청크.
  - **p.227(5장 커넥터 표)**: 코드가 표 행 중간(`At cold start, SRVO-300`) → 0청크.
- **하드코딩 페이지범위(p.53–104) 기각**: 브리틀(재페이지네이션·다른 컨트롤러 PDF에서 깨짐)하고 적용 범위가 "이 PDF 페이지번호에서만 동작"으로 한정됨. 구조적 키는 매뉴얼의 **저작 관례**에 의존해 일반화됨. domain-rag가 페이지범위안을 **철회**하고 이 방식 채택. (이전 레포 "섹션번호 하드코딩" 한계를 실제로 개선)
- **검증 의무**: 실제 실행 시 p.53·p.227이 0청크임을 **로깅**해 "구조적 배제 검증됨, 하드코딩 범위 없음"을 정직 기록.

### 2.6 content 앵커링 - header/title를 content에 포함
- `content = block.strip()` = 헤더줄("(N) SRVO-NNN 제목") + 본문 전체. **항상** 코드+제목이 content 첫머리.
- 근거: explanation-only 블록 존재(p.81 SRVO-094/096은 (Action) 없이 (Explanation)만, 조치는 교차참조로 위임). 헤더 없으면 1줄 본문이 약하게 임베딩됨 → 헤더 포함으로 `SRVO-094`,`PMAL alarm` 등 검색어에 앵커.
- `title`은 **추가로** 메타데이터 필드로도 노출(필터/표시용). (api-design의 "content 본문만" 제안은 앵커링 위배라 기각; content는 헤더 포함이 합의)

### 2.7 Chunk ID 스킴 + 충돌 가드
- 기본: `id = f"{error_code}_{page_no:03d}"` (예: `SRVO-094_081`). 가독·결정적·Chroma upsert 친화.
- 같은 페이지의 **다른** 코드들은 error_code가 달라 자동 유일. 유일 잔여 위험 = **같은 코드가 같은 페이지에 2회 정의**(미관측·비현실적).
- 가드(tagger에서): 중복 id 감지 시 `_{ordinal:02d}` 접미 + WARNING 로깅(침묵 드랍 금지). "코드당 페이지당 1정의" 가정 문서화. 콘텐츠 해시 ID 금지(pdfplumber 버전차로 idempotency 깨짐).

### 2.8 related_codes - 휴면 데이터 (ADR-002 안전)
- 파서가 블록 내 `\(SRVO-\d{3}\)`를 추출(자기코드 제외, 첫등장 순서) → `RawChunk.related_codes: list[str]`. tagger가 comma-join `str`로 메타데이터화(`""` if none).
- 실측 정합: p.81 094→["SRVO-072"], 095→["SRVO-073"], 096→["SRVO-074"], 097→["SRVO-075"], 105→[]. (측정 15회/6페이지와 일치)
- **가드레일**: 순수 데이터 캡처(재검색·병합·답변구동 없음). 코드·문서에서 **"Cross-Reference RAG" 등으로 명명 금지**(ADR-002 폐기). 나중에 검색에 연결하면 그건 새 검증대상 기능.

### 2.9 parsed_by 메타데이터 / 테스트 / 에러처리 / 패키징
- **parsed_by**: 메타데이터 포함(`marker`/`fallback`) → 폴백 청크 품질 감사·필터.
- **테스트**: `parse`/`tag` 순수함수. 골든 픽스처 `page_81_markers.txt`(마커)·`page_53_fallback.txt`(폴백)를 커밋해 파서 사양으로 사용. `tag`는 손수 만든 RawChunk로 테스트. `pdf_loader`는 소형 fixture PDF(happy) + 경로주입/모킹(에러경로).
- **에러 계약(예외 전파, 침묵 금지)**: `load_pages` - env 미설정→`EnvironmentError`, 파일 없음→`FileNotFoundError`, 0페이지→`[]`, 페이지 텍스트 None→`""`. `parse([])`/`tag([])`→`[]`, 코드 없으면 `[]`(폴백이 열화 페이지 처리, 비예외). 최상위 `except Exception` 금지(설정오류 vs 데이터오류 구분 가능해야).
- **패키징**: 지금은 `requirements.txt`(pdfplumber, python-dotenv, pytest) + src 레이아웃. 테스트가 editable 설치 필요해지면 최소 `pyproject.toml` 추가(Phase 2). experiments와 src는 상호 import 없음.

---

## 3. 미해결 이슈 / 트레이드오프

1. **[확정] 결정 D 변경 승인됨(2026-06-05)** - 기본 UNKNOWN 채택, 필드명 `severity_hint`. (2.4)
2. **severity 정밀도 미검증(A5)** - 키워드셋은 preliminary. "severity-aware retrieval"은 현재 개념 단계. 과대표현 금지.
3. **related_codes 휴면** - 명명 가드레일 준수 시에만 유지. 부담되면 드랍 가능(12.2% 저빈도).
4. **[별도 후속] mvp-plan "Safety Agent" 정직성 정리** - §3.1·§6 SRVO-062 5단계·기능3이 미구현 SAFETY 능력을 구현처럼 기술. 이 설계 코드 밖, 문서 정리 태스크로 분리.
5. **relaxed fallback-2 recall 안전망(파서 내부)** - 마커가 있는데 "(N)" 접두어가 없는 정의 페이지가 49p 중 존재하면 1차 경계가 놓침. 1차 후 "코드 언급>0 & 정의청크 0 & 마커≥1"인 페이지에 한해 완화 헤더(`^\s*(SRVO-\d{3})\b`, 여전히 괄호 제외) 재시도 → recall 보호. p.53/p.227은 마커 없어 비발동.
6. **구조적 배제 검증 로깅** - 통합 실행 시 p.53·p.227 0청크 + 커버리지(정의청크 수 vs 105 고유코드 = 진짜 알람 vs UI/표 언급)를 로깅해 정직 데이터로 남김.

---

## 4. 권장 구현 순서

1. **models.py + constants.py** - dataclass 3종(+TypedDict 문서), 정규식·severity 키워드(preliminary 주석)·리터럴.
2. **pdf_loader.py** - pdfplumber 페이지순회, 헤더/푸터 strip(행앵커 정규식), env 경로해석. + 골든 픽스처(p.81/p.53) 추출 스크립트(experiments 임시).
3. **chunk_parser.py + test_chunk_parser.py** - 연결+경계추적, "(N) SRVO-NNN" 분할, 마커/폴백, title/related_codes. 테스트: p.81→marker·explanation·actions, p.53→0청크 또는 fallback, `[]`/무코드.
4. **metadata_tagger.py + test_metadata_tagger.py** - content_type 상수, severity(UNKNOWN 기본), related_codes 평탄화, ID+충돌가드. 손수 RawChunk로 테스트.
5. **__init__.py exports + requirements.txt**.
6. **통합 스모크** - 실제 PDF → list[Chunk]. p.53/p.227 0청크 로깅, 커버리지 로깅(정의 vs 105). (임베딩/Chroma는 다음 설계)

---

## 부록: 참여 및 합의 상태

- parser-core(opus): 경계 알고리즘·앵커링·구조적 배제·ID·related_codes - `[COMPLETE] No further input`
- api-design(sonnet): 모듈/모델/ID 가드/severity 타이핑/테스트/패키징 - `[COMPLETE] No further input`
- domain-rag(opus): RAG 적합·메타데이터·severity 정직성·SAFETY·related_codes - `[COMPLETE] No further input`
- 전 항목 수렴. 사용자 사인오프 완료(2026-06-05): **결정 D 변경 = 기본 UNKNOWN, 필드명 `severity_hint`**.
