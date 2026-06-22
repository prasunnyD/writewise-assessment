"""Integration test: full evaluate_extraction on sample PDF."""

from pathlib import Path

import pytest

from eval.golden import load_golden
from eval.runner import evaluate_extraction

SAMPLE_PDF = Path(__file__).resolve().parents[2] / "assets" / "Northwind_Pricing_Proposal_SAMPLE.pdf"
GOLDEN_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "northwind_expected.json"


@pytest.mark.integration
def test_evaluate_sample_pdf_no_llm():
    assert SAMPLE_PDF.exists(), f"Sample PDF not found at {SAMPLE_PDF}"

    report = evaluate_extraction(str(SAMPLE_PDF), use_llm=False, golden_path=GOLDEN_PATH)

    assert report.passed
    assert report.golden.all_passed
    assert not report.metrics.critical_warnings

    golden = load_golden(GOLDEN_PATH)
    thresholds = golden["thresholds"]
    assert report.metrics.terms_out >= thresholds["min_terms_out"]
    assert report.metrics.services_out >= thresholds["min_services_out"]
    assert len(report.validated.assumptions) >= thresholds["min_assumptions_out"]
    assert report.metrics.terms_drop_rate <= thresholds["max_terms_drop_rate"]
    assert report.metrics.services_drop_rate <= thresholds["max_services_drop_rate"]

    assert report.validated.metadata.vendor_name is not None
    assert "Traditional Pricing" in report.validated.raw_markdown
