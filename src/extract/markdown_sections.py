"""Split markdown into format-generic contract sections for rule-based fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass

SECTION_SPECS: list[tuple[str, str, re.Pattern[str]]] = [
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
        "Included Services",
        re.compile(r".*\(Included Services\)\s*$", re.MULTILINE),
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
class MarkdownSection:
    """A named slice of contract markdown with optional page metadata."""

    section_type: str
    title: str
    raw_text: str
    page_number: int | None = None


def _find_section_starts(markdown: str) -> list[tuple[int, str, str]]:
    """Locate all known section headers and return (offset, type, title) tuples."""
    matches: list[tuple[int, str, str]] = []
    for section_type, title, pattern in SECTION_SPECS:
        match = pattern.search(markdown)
        if match:
            matches.append((match.start(), section_type, title))
    matches.sort(key=lambda item: item[0])
    return matches


def split_markdown_sections(markdown: str) -> list[MarkdownSection]:
    """Split contract markdown into ordered sections by known headings."""
    starts = _find_section_starts(markdown)
    if not starts:
        raise ValueError("No recognizable sections found in document markdown")

    sections: list[MarkdownSection] = []
    for index, (start_pos, section_type, title) in enumerate(starts):
        end_pos = starts[index + 1][0] if index + 1 < len(starts) else len(markdown)
        section_text = markdown[start_pos:end_pos].strip()
        sections.append(
            MarkdownSection(
                section_type=section_type,
                title=title,
                raw_text=section_text,
            )
        )

    rebate = _build_rebate_section(markdown)
    if rebate:
        sections.insert(1, rebate)

    return sections


def _build_rebate_section(markdown: str) -> MarkdownSection | None:
    """Build a rebate_guarantees section between its start and Applied Rebates."""
    marker = "Rebate Guarantees"
    start = markdown.find(marker)
    if start == -1:
        return None

    end_marker = "Traditional Pricing — Applied Rebates"
    end = markdown.find(end_marker, start)
    if end == -1:
        end = len(markdown)

    return MarkdownSection(
        section_type="rebate_guarantees",
        title="Rebate Guarantees",
        raw_text=markdown[start:end].strip(),
    )


def get_section(sections: list[MarkdownSection], section_type: str) -> MarkdownSection | None:
    """Return the first section matching section_type, or None."""
    return next((section for section in sections if section.section_type == section_type), None)
