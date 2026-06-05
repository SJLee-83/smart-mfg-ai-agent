# ADR-001: 데이터 폴더 구조 — `data/raw/` 골격 유지 + 원본 데이터 git 제외

- **상태(Status)**: 채택(Accepted)
- **날짜**: 2026-06-05
- **관련**: `.gitignore`, `.env.example`(`MANUAL_PDF_PATH`), `data/raw/.gitkeep`

---

## 맥락(Context)

매뉴얼 PDF(`R30iA-Mate-Controller-Maintenance-Manual.pdf`, 약 7.4MB)를 RAG 입력으로 사용해야 한다.
원본 데이터를 어디에 두고, git에 어떻게 다룰지 결정이 필요하다.

제약·전제:
- 매뉴얼 1종, 단독 작업, 포트폴리오 목적 프로젝트
- GitHub 공개 가능성 있음 → 원본 데이터는 repo에 커밋하지 않는 편이 안전
- 코드가 매뉴얼 경로를 일관되게 참조할 수 있어야 함

## 결정(Decision)

`data/raw/` 폴더를 repo 구조 안에 두되, **원본 데이터 파일은 git 추적에서 제외**한다.

- 폴더 골격은 `data/raw/.gitkeep`으로 repo에 유지한다.
- 원본 데이터 파일(`*.pdf`, `*.csv`)은 `.gitignore`로 추적 제외한다.
- 매뉴얼 PDF 경로는 하드코딩하지 않고 **`.env`의 `MANUAL_PDF_PATH`** 로 관리한다.
  (`.env.example`에 키와 기본 경로를 템플릿으로 남김)

### `.gitignore` 패턴

```gitignore
data/raw/*.pdf
data/raw/*.csv
!data/raw/.gitkeep
```

## 검증 기록 — `.gitkeep` 함정 (중요)

처음 안은 "`.gitignore`에서 `data/raw/` 전체를 무시 + `data/raw/.gitkeep`으로 골격 유지"였다.
**이 조합은 작동하지 않는다.**

`git check-ignore -v data/raw/.gitkeep` 실측 결과, `.gitkeep` 자체가 `data/raw/` 규칙에
의해 무시되었다(exit 0). git은 제외된 디렉터리 내부로 진입하지 않으므로, 부모 디렉터리가
통째로 무시되면 그 안의 파일은 `!` 부정 패턴으로도 다시 추적할 수 없다.

→ 그래서 디렉터리 전체 무시(`data/raw/`)가 아니라 **파일 단위 무시(`data/raw/*.pdf`,
`data/raw/*.csv`)** 로 바꿔, 디렉터리는 추적 대상으로 남기고 그 안의 원본 데이터 파일만
제외하는 방식을 채택했다. 이렇게 하면 `.gitkeep`은 어떤 무시 패턴에도 걸리지 않아 정상
추적된다(`!data/raw/.gitkeep`는 의도를 명시하는 방어적 선언).

## 결과(Consequences)

**좋은 점**
- `data/raw/` 폴더 구조가 repo(및 GitHub)에 그대로 드러난다 → 신규 클론 시 경로 일관성.
- 매뉴얼 PDF는 git에 올라가지 않는다 → 공개 repo에서도 원본 데이터 비노출, 저장소 경량.
- 경로가 `.env`로 추상화되어 매뉴얼 파일명이 바뀌어도 코드 수정 불필요.

**트레이드오프 / 주의**
- 무시 범위를 `*.pdf`·`*.csv`로 **한정**했으므로, `data/raw/`에 다른 확장자
  (`.json`, `.xlsx`, `.txt` 등) 원본 데이터를 넣으면 **자동으로 무시되지 않는다**.
  → 그런 데이터를 추가할 때는 커밋 전 수동 점검하거나 `.gitignore` 패턴을 확장할 것.
- 새 클론 환경에서는 매뉴얼 PDF가 없으므로, 사용자가 직접 `data/raw/`에 배치하고
  `.env`의 `MANUAL_PDF_PATH`를 맞춰야 한다(README에 안내 필요).

## 고려한 대안(Alternatives considered)

1. **`data/raw/` 전체 무시 + `.gitkeep`** — 위 "검증 기록"대로 작동하지 않아 기각.
2. **`data/raw/*` 전체 무시 + `!data/raw/.gitkeep`** — 폴더 내 모든 파일을 무시하는
   가장 강한 안전망. 채택안보다 안전하지만, 현재는 사용자가 확장자 한정 방식을 명시 선택.
   향후 다양한 원본 데이터가 들어오면 이 패턴으로 전환 검토.
3. **원본 PDF를 repo에 커밋** — 공개 repo 데이터 노출 위험 + 저장소 비대화로 기각.
