"""src/parsing 공유 상수·패턴 — 정규식, severity 키워드, 노이즈 제거.

근거: docs/parsing-pipeline.md, docs/validation/A2-pdf-parsing-explore.md,
실제 페이지 구조(p.53/p.81/p.82). severity 키워드셋은 미검증(A5) — preliminary.
"""

from __future__ import annotations

import re

# --- content_type (결정 C: 이 파이프라인은 TROUBLESHOOTING만) ---
CONTENT_TYPE_TROUBLESHOOTING = "TROUBLESHOOTING"

# --- severity_hint (결정 D: 기본 UNKNOWN, 키워드 휴리스틱 / A5 미검증) ---
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_UNKNOWN = "UNKNOWN"
# preliminary 키워드셋 (A5 검증 전). FANUC 안전고지 위계: WARNING/DANGER > CAUTION/NOTE.
SEVERITY_HIGH_KEYWORDS: frozenset[str] = frozenset({"WARNING", "DANGER"})
SEVERITY_MEDIUM_KEYWORDS: frozenset[str] = frozenset({"CAUTION", "NOTE"})

# --- SRVO 코드 ---
CODE_RE = re.compile(r"SRVO-\d{3}")  # 모든 코드 언급(괄호 무관) / 형식 검증용
# 정의 헤더: 행 선두 "(N) " 항목번호 + 괄호 없는 코드 = 청크 경계 키.
# 괄호 안의 코드 "(SRVO-072)"(교차참조)나 "2 SRVO-002"(UI 리스트)는 매칭 안 됨.
DEF_HEADER_RE = re.compile(
    r"^[ \t]*\((?P<item>\d{1,4})\)[ \t]+(?P<code>SRVO-\d{3})\b(?P<rest>[^\n]*)",
    re.MULTILINE,
)
# 괄호 교차참조 (SRVO-NNN) — 경계 아님, related_codes 추출용.
XREF_RE = re.compile(r"\((SRVO-\d{3})\)")

# --- 구조 마커 ---
EXPLANATION_RE = re.compile(r"^[ \t]*\(Explanation\)[ \t]*", re.MULTILINE)
ACTION_RE = re.compile(r"^[ \t]*\(Action(?:[ \t]+(?P<num>\d+))?\)[ \t]*", re.MULTILINE)

# --- 페이지 노이즈(헤더/푸터/그림캡션) — 행 전체 제거 ---
# 러닝 헤더: 문서ID가 좌/우 정렬로 들어감(p.81 vs p.82 순서 반전) -> 문서ID로 매칭.
NOISE_RUNNING_HEADER_RE = re.compile(r"^.*B-\d{5}EN-\d/\d{2}.*$", re.MULTILINE)
NOISE_PAGE_FOOTER_RE = re.compile(r"^[ \t]*-[ \t]*\d+[ \t]*-[ \t]*$", re.MULTILINE)
NOISE_FIGURE_CAPTION_RE = re.compile(r"^[ \t]*Fig\.[ \t]*\d.*$", re.MULTILINE)

_NOISE_RES = (NOISE_RUNNING_HEADER_RE, NOISE_PAGE_FOOTER_RE, NOISE_FIGURE_CAPTION_RE)

# severity 키워드 워드바운더리 매칭(대문자 고지어) — 소문자 오탐 방지.
_SEVERITY_WORD_RES = {
    SEVERITY_HIGH: re.compile(r"\b(" + "|".join(sorted(SEVERITY_HIGH_KEYWORDS)) + r")\b"),
    SEVERITY_MEDIUM: re.compile(r"\b(" + "|".join(sorted(SEVERITY_MEDIUM_KEYWORDS)) + r")\b"),
}


def strip_noise(text: str) -> str:
    """러닝 헤더/페이지 푸터/그림 캡션 라인을 제거한다. 멱등·순수함수."""
    for rx in _NOISE_RES:
        text = rx.sub("", text)
    # 노이즈 제거로 생긴 연속 빈 줄 정리.
    return re.sub(r"\n[ \t]*\n+", "\n", text).strip("\n")


def detect_severity_hint(text: str) -> str:
    """안전고지 키워드 기반 severity_hint. 키워드 없으면 UNKNOWN(날조 금지).

    주의: 키워드 휴리스틱이며 매뉴얼 네이티브 알람 심각도(STOP/SERVO/WARN 등)가
    아니다. 정밀도 미검증(A5). WARNING/DANGER가 CAUTION/NOTE보다 우선.
    """
    if _SEVERITY_WORD_RES[SEVERITY_HIGH].search(text):
        return SEVERITY_HIGH
    if _SEVERITY_WORD_RES[SEVERITY_MEDIUM].search(text):
        return SEVERITY_MEDIUM
    return SEVERITY_UNKNOWN
