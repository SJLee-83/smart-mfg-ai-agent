"""chunk_parser 테스트 — 합성 골든 픽스처(구조만 모방, 매뉴얼 원문 미포함) + 합성 케이스.

fixtures/marker_page.txt : (N) SRVO-NNN 정의 + (Explanation)/(Action) + 교차참조 구조
fixtures/ui_page_no_defs.txt : 코드는 있으나 "(N) SRVO" 정의 헤더가 없는 UI 페이지(0청크)
"""

from __future__ import annotations

from pathlib import Path

from parsing import PageText, parse

FIXTURES = Path(__file__).parent / "fixtures"


def _page(page_no: int, fname: str) -> PageText:
    return PageText(page_no=page_no, text=(FIXTURES / fname).read_text(encoding="utf-8"))


def _by_code(page_no: int = 81, fname: str = "marker_page.txt"):
    return {c.error_code: c for c in parse([_page(page_no, fname)])}


def test_marker_page_yields_per_code_chunks():
    chunks = parse([_page(81, "marker_page.txt")])
    assert [c.error_code for c in chunks] == [
        "SRVO-901",
        "SRVO-902",
        "SRVO-903",
        "SRVO-904",
        "SRVO-905",
    ]


def test_marker_page_structure_and_anchor():
    first = parse([_page(81, "marker_page.txt")])[0]
    assert first.error_code == "SRVO-901"
    assert first.parsed_by == "marker"
    assert first.title.startswith("SRVO-901")
    assert first.explanation is not None
    # content는 헤더("(11) SRVO-901 ...")를 포함해 앵커링 보장
    assert first.content.startswith("(11) SRVO-901")


def test_explanation_only_vs_multi_action():
    by_code = _by_code()
    assert by_code["SRVO-901"].actions == []  # (Explanation)만
    assert by_code["SRVO-903"].actions == []  # (Explanation)만
    assert len(by_code["SRVO-902"].actions) == 2
    assert len(by_code["SRVO-905"].actions) == 5  # 서브불릿 사이에 끼어도 5개


def test_related_codes_captured_self_excluded():
    by_code = _by_code()
    assert by_code["SRVO-901"].related_codes == ["SRVO-801"]
    assert by_code["SRVO-902"].related_codes == ["SRVO-802"]
    assert by_code["SRVO-904"].related_codes == ["SRVO-803"]
    assert by_code["SRVO-903"].related_codes == []
    # SRVO-905는 본문에 자기코드 (SRVO-905)를 언급하지만 related에서 제외
    assert by_code["SRVO-905"].related_codes == []


def test_xref_is_not_a_boundary():
    codes = {c.error_code for c in parse([_page(81, "marker_page.txt")])}
    # (SRVO-801..803)은 괄호 교차참조일 뿐 — 독립 청크가 되면 안 됨
    for ref in ("SRVO-801", "SRVO-802", "SRVO-803"):
        assert ref not in codes


def test_ui_page_yields_zero_chunks():
    # 코드는 있으나 "(N) SRVO" 정의 헤더가 없음 -> 0청크(구조적 배제, 하드코딩 없음)
    assert parse([_page(53, "ui_page_no_defs.txt")]) == []


def test_page_spanning_code_stays_one_chunk():
    # 코드가 페이지 A에서 시작, 본문이 페이지 B로 이어짐(다음 정의 헤더 전까지)
    a = PageText(page_no=10, text="(1) SRVO-111 Test alarm\n(Explanation) cause line.")
    b = PageText(
        page_no=11,
        text="(Action 1) do the fix.\n(2) SRVO-222 Next alarm\n(Explanation) other.",
    )
    chunks = parse([a, b])
    assert [c.error_code for c in chunks] == ["SRVO-111", "SRVO-222"]
    s111 = chunks[0]
    assert s111.page_no == 10  # 시작 페이지
    assert s111.actions == ["do the fix."]  # 페이지 B의 액션이 한 청크로 붙음
    assert "do the fix" in s111.content


def test_fallback_when_no_markers():
    p = PageText(page_no=5, text="(1) SRVO-333 Some alarm\nPlain body without markers.")
    chunks = parse([p])
    assert len(chunks) == 1
    c = chunks[0]
    assert c.parsed_by == "fallback"
    assert c.explanation is None
    assert c.actions == []
    assert c.content.startswith("(1) SRVO-333")


def test_empty_and_no_code():
    assert parse([]) == []
    assert parse([PageText(page_no=1, text="no codes here")]) == []
