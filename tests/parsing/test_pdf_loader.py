"""pdf_loader 테스트 — 노이즈 제거(순수함수) + 에러 경로."""

from __future__ import annotations

from pathlib import Path

import pytest

from parsing import load_pages
from parsing.constants import strip_noise
from parsing.pdf_loader import resolve_pdf_path


def test_strip_noise_removes_running_header_both_orders():
    # 러닝 헤더는 p.81/p.82에서 좌우 반전 — 둘 다 제거되어야 함
    t1 = "3.TROUBLESHOOTING MAINTENANCE B-82725EN-2/06\n(57) SRVO-094 x"
    t2 = "B-82725EN-2/06 MAINTENANCE 3.TROUBLESHOOTING\n(62) SRVO-136 y"
    assert "B-82725EN" not in strip_noise(t1)
    assert "B-82725EN" not in strip_noise(t2)
    assert "SRVO-094" in strip_noise(t1)  # 본문은 보존


def test_strip_noise_removes_footer_and_figure_caption():
    t = "body line\n- 44 -\nFig.3.5 (t) SRVO-105 Door open\nmore body"
    out = strip_noise(t)
    assert "- 44 -" not in out
    assert "Fig.3.5" not in out
    assert "body line" in out
    assert "more body" in out


def test_strip_noise_is_idempotent():
    t = "3.TROUBLESHOOTING MAINTENANCE B-82725EN-2/06\nkeep\n- 16 -"
    once = strip_noise(t)
    assert strip_noise(once) == once


def test_resolve_pdf_path_arg_takes_priority():
    p = Path("some/explicit/path.pdf")
    assert resolve_pdf_path(p) == p


def test_load_pages_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_pages(Path("does/not/exist.pdf"))
