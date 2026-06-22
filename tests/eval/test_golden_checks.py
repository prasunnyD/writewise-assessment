"""Unit tests for eval.golden spot checks."""

from models.extraction import AssumptionRow, DocumentMetadata, ExtractionResult
from eval.golden import load_golden, run_golden_checks, run_threshold_checks
from eval.metrics import ValidationMetrics

from tests.conftest import make_contract_term, make_included_service
from tests.fixtures.snippets import VALIDATOR_SOURCE


def test_run_golden_checks_contract_term_pass():
    result = ExtractionResult(
        metadata=DocumentMetadata(vendor_name="Northwind PBM", client_name="Acme"),
        contract_terms=[
            make_contract_term(
                network_id="retail_90",
                calendar_year=2027,
                source_row_label="Generic Discount",
                value_numeric=87.3,
            )
        ],
        raw_markdown=VALIDATOR_SOURCE + " 87.3",
    )
    golden = {
        "metadata": {"vendor_name_contains": "Northwind", "client_name_not_null": True},
        "contract_terms": [
            {
                "network_id": "retail_90",
                "calendar_year": 2027,
                "source_row_label_contains": "Generic Discount",
                "value_numeric": 87.3,
            }
        ],
    }
    outcome = run_golden_checks(result, golden, verify_numerics=False)
    assert outcome.all_passed
    assert outcome.spot_checks_failed == 0


def test_run_golden_checks_contract_term_fail():
    result = ExtractionResult(
        metadata=DocumentMetadata(),
        contract_terms=[make_contract_term(value_numeric=18.5)],
    )
    golden = {
        "contract_terms": [
            {
                "network_id": "retail_90",
                "calendar_year": 2027,
                "source_row_label_contains": "Generic Discount",
                "value_numeric": 87.3,
            }
        ],
    }
    outcome = run_golden_checks(result, golden, verify_numerics=False)
    assert not outcome.all_passed
    assert outcome.failures


def test_run_threshold_checks():
    metrics = ValidationMetrics(
        terms_in=100,
        terms_out=95,
        terms_dropped=5,
        services_in=50,
        services_out=48,
        services_dropped=2,
        assumptions_in=20,
        warnings_before=1,
        warnings_after=2,
    )
    validated = ExtractionResult(
        metadata=DocumentMetadata(),
        assumptions=[AssumptionRow(category="G", bullet_text="x")] * 20,
    )
    golden = {
        "thresholds": {
            "min_terms_out": 80,
            "min_services_out": 30,
            "min_assumptions_out": 15,
            "max_terms_drop_rate": 0.1,
        }
    }
    outcome = run_threshold_checks(metrics, validated, golden)
    assert outcome.threshold_checks_failed == 0


def test_load_northwind_expected():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "fixtures" / "northwind_expected.json"
    golden = load_golden(path)
    assert "contract_terms" in golden
    assert golden["thresholds"]["min_terms_out"] >= 80
