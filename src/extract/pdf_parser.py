"""PDF parsing and section segmentation."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pdfplumber

from models.extraction import SectionChunk

SECTION_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "traditional_pricing",
        "Traditional Pricing",
        re.compile(r"^Traditional Pricing\s*$", re.MULTILINE),
    ),
    (
        "applied_rebates_pricing",
        "Traditional Pricing — Applied Rebates",
        re.compile(r"^Traditional Pricing — Applied Rebates\s*$", re.MULTILINE),
    ),
    (
        "included_services",
        "Northwind PBM Services (Included Services)",
        re.compile(r"^Northwind PBM Services \(Included Services\)\s*$", re.MULTILINE),
    ),
    (
        "allowances_fees",
        "Allowances and Ancillary Charges",
        re.compile(r"^Allowances and Ancillary Charges\s*$", re.MULTILINE),
    ),
    (
        "assumptions",
        "Assumptions and Caveats",
        re.compile(r"^Assumptions and Caveats\s*$", re.MULTILINE),
    ),
]


@dataclass
class PageContent:
    page_number: int
    text: str
    tables: list[list[list[str | None]]]


def extract_pages(pdf_path: str) -> list[PageContent]:
    pages: list[PageContent] = []
    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            tables: list[list[list[str | None]]] = []
            for table in page.extract_tables() or []:
                cleaned = [
                    [cell.strip() if isinstance(cell, str) else cell for cell in row]
                    for row in table
                ]
                tables.append(cleaned)
            pages.append(PageContent(page_number=index, text=text, tables=tables))
    return pages


def _find_section_starts(full_text: str) -> list[tuple[int, str, str, re.Match[str]]]:
    matches: list[tuple[int, str, str, re.Match[str]]] = []
    for section_type, title, pattern in SECTION_PATTERNS:
        match = pattern.search(full_text)
        if match:
            matches.append((match.start(), section_type, title, match))
    matches.sort(key=lambda item: item[0])
    return matches


def segment_sections(pages: list[PageContent]) -> list[SectionChunk]:
    page_texts = {page.page_number: page.text for page in pages}
    full_text = "\n\n".join(page.text for page in pages)
    starts = _find_section_starts(full_text)

    if not starts:
        raise ValueError("No recognizable sections found in PDF")

    chunks: list[SectionChunk] = []
    for index, (start_pos, section_type, title, _match) in enumerate(starts):
        end_pos = starts[index + 1][0] if index + 1 < len(starts) else len(full_text)
        section_text = full_text[start_pos:end_pos].strip()

        page_start = 1
        page_end = len(pages)
        for page_number, text in page_texts.items():
            if title.split("\n")[0] in text or title in text:
                page_start = min(page_start, page_number) if page_start == 1 else page_start
                page_start = page_number if page_start == 1 else min(page_start, page_number)
        for page_number, text in page_texts.items():
            if any(
                title in text
                for title in [section_type, title]
            ) or section_text[:80] in text:
                page_start = min(page_start, page_number)
                page_end = max(page_end, page_number)

        section_tables: list[list[list[str | None]]] = []
        for page in pages:
            if page_start <= page.page_number <= page_end:
                section_tables.extend(page.tables)

        chunks.append(
            SectionChunk(
                section_type=section_type,
                title=title,
                page_start=page_start,
                page_end=page_end,
                raw_text=section_text,
                tables=section_tables,
            )
        )

    rebate_chunk = _build_rebate_chunk(pages, full_text)
    if rebate_chunk:
        chunks.insert(1, rebate_chunk)

    return chunks


def _build_rebate_chunk(pages: list[PageContent], full_text: str) -> SectionChunk | None:
    marker = "Rebate Guarantees"
    start = full_text.find(marker)
    if start == -1:
        return None

    end_marker = "Traditional Pricing — Applied Rebates"
    end = full_text.find(end_marker, start)
    if end == -1:
        end = len(full_text)

    section_text = full_text[start:end].strip()
    page_start = 1
    page_end = 2
    section_tables: list[list[list[str | None]]] = []
    for page in pages:
        if marker in page.text:
            page_start = page.page_number
            page_end = max(page_end, page.page_number)
            section_tables.extend(page.tables)

    return SectionChunk(
        section_type="rebate_guarantees",
        title="Rebate Guarantees",
        page_start=page_start,
        page_end=page_end,
        raw_text=section_text,
        tables=section_tables,
    )


def parse_pdf(pdf_path: str) -> tuple[list[PageContent], list[SectionChunk]]:
    pages = extract_pages(pdf_path)
    sections = segment_sections(pages)
    return pages, sections
