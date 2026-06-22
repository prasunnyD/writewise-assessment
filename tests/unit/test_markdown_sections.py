"""Unit tests for extract.markdown_sections."""

import pytest

from extract.markdown_sections import get_section, split_markdown_sections

from tests.fixtures.snippets import FULL_DOCUMENT_MARKDOWN


def test_split_markdown_sections_returns_expected_types():
    """Split markdown into all expected section types."""
    sections = split_markdown_sections(FULL_DOCUMENT_MARKDOWN)
    types = [s.section_type for s in sections]
    assert "traditional_pricing" in types
    assert "rebate_guarantees" in types
    assert "applied_rebates_pricing" in types
    assert "included_services" in types
    assert "allowances_fees" in types
    assert "assumptions" in types


def test_split_markdown_sections_order():
    """Preserve document order for pricing and rebate sections."""
    sections = split_markdown_sections(FULL_DOCUMENT_MARKDOWN)
    types = [s.section_type for s in sections]
    trad_idx = types.index("traditional_pricing")
    rebate_idx = types.index("rebate_guarantees")
    applied_idx = types.index("applied_rebates_pricing")
    assert trad_idx < rebate_idx < applied_idx


def test_get_section_found():
    """Return a section when the requested type exists."""
    sections = split_markdown_sections(FULL_DOCUMENT_MARKDOWN)
    fees = get_section(sections, "allowances_fees")
    assert fees is not None
    assert "Allowances and Ancillary Charges" in fees.raw_text


def test_get_section_missing():
    """Return None when the requested section type is absent."""
    sections = split_markdown_sections(FULL_DOCUMENT_MARKDOWN)
    assert get_section(sections, "nonexistent") is None


def test_split_markdown_sections_raises_when_no_headers():
    """Raise ValueError when no recognizable section headers are found."""
    with pytest.raises(ValueError, match="No recognizable sections"):
        split_markdown_sections("This document has no known section headers.")
