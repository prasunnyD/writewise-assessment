"""Integration test: live PDF extraction via rule-based path."""

from pathlib import Path

import pytest

from eval.runner import evaluate_extraction

SAMPLE_PDF = (
    Path(__file__).resolve().parents[2] / "assets" / "Northwind_Pricing_Proposal_SAMPLE.pdf"
)
GOLDEN_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "northwind_expected.json"


@pytest.mark.integration
def test_extract_sample_pdf_no_llm():
    """Extract the sample PDF without LLM and verify evaluation passes."""
    assert SAMPLE_PDF.exists(), f"Sample PDF not found at {SAMPLE_PDF}"

    report = evaluate_extraction(str(SAMPLE_PDF), use_llm=False, golden_path=GOLDEN_PATH)

    assert report.passed
    assert report.golden.all_passed
    assert report.validated.metadata.vendor_name is not None
    assert report.validated.raw_markdown
    assert "Traditional Pricing" in report.validated.raw_markdown
    assert report.metrics.terms_out >= 80
    assert report.metrics.services_out >= 30
    assert len(report.validated.assumptions) >= 15
    assert "No contract terms survived validation" not in report.validated.warnings
