"""Convert PDF documents to markdown via Markitdown."""

from __future__ import annotations

from pathlib import Path


def pdf_to_markdown(pdf_path: str) -> str:
    from markitdown import MarkItDown

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    result = MarkItDown().convert(str(path))
    text = result.text_content
    if not text or not text.strip():
        raise ValueError(f"No text extracted from PDF: {pdf_path}")
    return text.strip()
