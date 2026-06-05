"""PDF 로더 — 파이프라인의 유일한 I/O 경계.

pdfplumber로 페이지 텍스트를 추출하고 노이즈(헤더/푸터/그림캡션)를 제거한다.
경로는 인자 우선, 없으면 .env의 MANUAL_PDF_PATH. 설계: docs/parsing-pipeline.md §2.9.
"""

from __future__ import annotations

import os
from pathlib import Path

import pdfplumber
from dotenv import find_dotenv, load_dotenv

from .constants import strip_noise
from .models import PageText

ENV_KEY = "MANUAL_PDF_PATH"


def resolve_pdf_path(pdf_path: Path | None = None) -> Path:
    """PDF 경로 해석: 인자 > .env의 MANUAL_PDF_PATH.

    Raises:
        EnvironmentError: 인자 미지정 + MANUAL_PDF_PATH 미설정.
    """
    if pdf_path is not None:
        return Path(pdf_path)
    load_dotenv(find_dotenv(usecwd=True))
    raw = os.getenv(ENV_KEY)
    if not raw:
        raise EnvironmentError(f"{ENV_KEY} not set in environment (.env)")
    return Path(raw)


def load_pages(pdf_path: Path | None = None) -> list[PageText]:
    """PDF를 열어 페이지별 (노이즈 제거된) 텍스트를 반환한다.

    Raises:
        EnvironmentError: 경로 미지정 + MANUAL_PDF_PATH 미설정.
        FileNotFoundError: 경로의 파일이 존재하지 않음.
    """
    path = resolve_pdf_path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    pages: list[PageText] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = strip_noise(page.extract_text() or "")
            pages.append(PageText(page_no=i, text=text))
    return pages
