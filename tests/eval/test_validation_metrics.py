"""Unit tests for eval.metrics."""

from models.extraction import AssumptionRow, DocumentMetadata, ExtractionResult
from eval.metrics import build_validation_metrics

from tests.conftest import make_contract_term, make_included_service


def test_build_validation_metrics_counts_drops():
    """Count dropped rows, added warnings, and critical warnings."""
    before = ExtractionResult(
        metadata=DocumentMetadata(),
        contract_terms=[make_contract_term(), make_contract_term(value_numeric=99.9)],
        included_services=[make_included_service(), make_included_service(service_name="Other")],
        assumptions=[AssumptionRow(category="G", bullet_text="a")],
        warnings=["pipeline warning"],
    )
    after = ExtractionResult(
        metadata=DocumentMetadata(),
        contract_terms=[make_contract_term()],
        included_services=[make_included_service()],
        warnings=["pipeline warning", "validator warning", "No contract terms survived validation"],
    )

    metrics = build_validation_metrics(before, after)

    assert metrics.terms_in == 2
    assert metrics.terms_out == 1
    assert metrics.terms_dropped == 1
    assert metrics.services_in == 2
    assert metrics.services_out == 1
    assert metrics.services_dropped == 1
    assert metrics.warnings_before == 1
    assert metrics.warnings_after == 3
    assert metrics.warnings_added == ["validator warning", "No contract terms survived validation"]
    assert metrics.critical_warnings == ["No contract terms survived validation"]
    assert metrics.terms_drop_rate == 0.5


def test_build_validation_metrics_zero_drop_rate():
    """Report zero drop rates when validation does not remove rows."""
    row = make_contract_term()
    result = ExtractionResult(metadata=DocumentMetadata(), contract_terms=[row])
    metrics = build_validation_metrics(result, result)
    assert metrics.terms_drop_rate == 0.0
    assert metrics.services_drop_rate == 0.0
    assert metrics.warnings_added == []
