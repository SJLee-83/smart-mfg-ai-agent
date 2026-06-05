"""metadata_tagger 테스트 — ID 스킴/충돌가드, 메타데이터 스키마, severity_hint."""

from __future__ import annotations

from parsing import RawChunk, tag


def _raw(**kw) -> RawChunk:
    base = dict(
        error_code="SRVO-094",
        content="(57) SRVO-094 PMAL alarm\n(Explanation) cause.",
        page_no=81,
        title="SRVO-094 PMAL alarm",
        explanation="cause.",
        actions=[],
        related_codes=[],
        parsed_by="marker",
    )
    base.update(kw)
    return RawChunk(**base)


def test_id_scheme():
    assert tag([_raw()])[0].id == "SRVO-094_081"


def test_id_collision_guard():
    chunks = tag([_raw(), _raw()])  # 같은 코드+페이지 2회
    assert chunks[0].id == "SRVO-094_081"
    assert chunks[1].id == "SRVO-094_081_01"


def test_metadata_schema_and_scalar_values():
    md = tag([_raw(related_codes=["SRVO-072"])])[0].metadata
    assert md["error_code"] == "SRVO-094"
    assert md["page_no"] == 81
    assert md["title"] == "SRVO-094 PMAL alarm"
    assert md["content_type"] == "TROUBLESHOOTING"
    assert md["severity_hint"] == "UNKNOWN"  # 안전고지 키워드 없음 -> 날조 안 함
    assert md["parsed_by"] == "marker"
    assert md["related_codes"] == "SRVO-072"
    # 모든 값은 Chroma 스칼라(str/int)
    assert all(isinstance(v, (str, int)) for v in md.values())


def test_severity_hint_keyword_mapping():
    high = tag([_raw(content="(1) SRVO-094 x\nWARNING high voltage present")])[0].metadata
    assert high["severity_hint"] == "HIGH"
    med = tag([_raw(content="(1) SRVO-094 x\nCAUTION hot surface")])[0].metadata
    assert med["severity_hint"] == "MEDIUM"


def test_related_codes_empty_string():
    assert tag([_raw()])[0].metadata["related_codes"] == ""


def test_empty():
    assert tag([]) == []
