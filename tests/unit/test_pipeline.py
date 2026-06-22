"""Unit tests for extract.pipeline orchestration (mocked external deps)."""

from unittest.mock import MagicMock

from models.enums import SourceSection
from models.extraction import DocumentMetadata, IncludedServiceRow
from extract.llm_extractor import LLMExtractionResult
from extract.markdown_sections import split_markdown_sections
from extract.pipeline import (
    _extract_with_rules,
    _supplement_services_from_rules,
    extract_from_pdf,
)

from tests.fixtures.snippets import FULL_DOCUMENT_MARKDOWN


def test_supplement_services_from_rules_adds_fee_rows():
    llm_services = [
        IncludedServiceRow(
            category="Clinical",
            service_name="Prior authorization review",
            source_section=SourceSection.INCLUDED_SERVICES,
        )
    ]
    merged, warnings = _supplement_services_from_rules(FULL_DOCUMENT_MARKDOWN, llm_services)
    fee_rows = [s for s in merged if s.source_section == SourceSection.ALLOWANCES_FEES]
    included_rows = [s for s in merged if s.source_section == SourceSection.INCLUDED_SERVICES]
    assert fee_rows
    assert included_rows
    assert any("Fee schedule" in w for w in warnings)


def test_supplement_services_from_rules_empty_llm_included():
    merged, _warnings = _supplement_services_from_rules(FULL_DOCUMENT_MARKDOWN, [])
    included_rows = [s for s in merged if s.source_section == SourceSection.INCLUDED_SERVICES]
    assert included_rows


def test_extract_with_rules_produces_terms_and_services():
    sections = split_markdown_sections(FULL_DOCUMENT_MARKDOWN)
    result = _extract_with_rules(sections, FULL_DOCUMENT_MARKDOWN)
    assert result.contract_terms
    assert result.included_services
    assert result.assumptions
    assert result.metadata.vendor_name == "Northwind PBM"


def test_extract_from_pdf_llm_path(monkeypatch):
    llm_result = LLMExtractionResult(
        metadata=DocumentMetadata(vendor_name="Northwind PBM"),
        contract_terms=[],
        included_services=[
            IncludedServiceRow(
                category="Clinical",
                service_name="Prior authorization review",
                source_section=SourceSection.INCLUDED_SERVICES,
            )
        ],
    )

    monkeypatch.setattr("extract.pipeline.pdf_to_markdown", lambda _path: FULL_DOCUMENT_MARKDOWN)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_client.extract_from_markdown.return_value = llm_result
    monkeypatch.setattr("extract.pipeline.LLMClient", lambda: mock_client)

    result = extract_from_pdf("fake.pdf", use_llm=True)
    assert result.metadata.vendor_name == "Northwind PBM"
    fee_rows = [s for s in result.included_services if s.source_section == SourceSection.ALLOWANCES_FEES]
    assert fee_rows
    mock_client.extract_from_markdown.assert_called_once_with(FULL_DOCUMENT_MARKDOWN)


def test_extract_from_pdf_llm_fallback_on_failure(monkeypatch):
    monkeypatch.setattr("extract.pipeline.pdf_to_markdown", lambda _path: FULL_DOCUMENT_MARKDOWN)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_client.extract_from_markdown.side_effect = RuntimeError("API down")
    monkeypatch.setattr("extract.pipeline.LLMClient", lambda: mock_client)

    result = extract_from_pdf("fake.pdf", use_llm=True)
    assert result.contract_terms
    assert any("LLM extraction failed" in w for w in result.warnings)


def test_extract_from_pdf_no_llm_path(monkeypatch):
    monkeypatch.setattr("extract.pipeline.pdf_to_markdown", lambda _path: FULL_DOCUMENT_MARKDOWN)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = extract_from_pdf("fake.pdf", use_llm=False)
    assert result.contract_terms
    assert result.raw_markdown == FULL_DOCUMENT_MARKDOWN
    assert any("Rule-based fallback" in w for w in result.warnings)
