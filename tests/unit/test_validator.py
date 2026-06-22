"""Unit tests for extract.validator."""

from models.enums import (
    BasisType,
    SourceSection,
    TermCategory,
    ValueType,
)
from models.extraction import AssumptionRow, DocumentMetadata, ExtractionResult
from extract.validator import (
    validate_contract_term,
    validate_extraction,
    validate_included_service,
    value_appears_in_source,
)

from tests.conftest import make_contract_term, make_included_service
from tests.fixtures.snippets import VALIDATOR_SOURCE


def test_value_appears_in_source_substring():
    assert value_appears_in_source("AWP - 18.5 %", VALIDATOR_SOURCE)


def test_value_appears_in_source_whitespace_normalization():
    assert value_appears_in_source("AWP  -  18.5  %", VALIDATOR_SOURCE)


def test_value_appears_in_source_numeric_fallback():
    assert value_appears_in_source("18.5", VALIDATOR_SOURCE)


def test_value_appears_in_source_missing():
    assert not value_appears_in_source("999.99", VALIDATOR_SOURCE)


def test_value_appears_in_source_empty():
    assert not value_appears_in_source("", VALIDATOR_SOURCE)


def test_validate_contract_term_warns_on_missing_numeric(sample_source_corpus):
    row = make_contract_term(value_numeric=999.99, value_text="$999.99")
    warnings = validate_contract_term(row, sample_source_corpus)
    assert any("not found in source" in w for w in warnings)


def test_validate_contract_term_warns_on_missing_payment_schedule(sample_source_corpus):
    row = make_contract_term(
        term_category=TermCategory.REBATE,
        payment_schedule=None,
        value_numeric=1.5,
        value_text="$1.50",
    )
    warnings = validate_contract_term(row, "2026 1.50 2.00 3.00 4.00")
    assert any("payment_schedule" in w for w in warnings)


def test_validate_included_service_fee_not_in_source():
    row = make_included_service(
        service_name="Fake service name",
        source_section=SourceSection.ALLOWANCES_FEES,
        value_type=ValueType.NUMERIC,
        value_numeric=25.0,
        value_text="$25.00 per claim",
        fee_type=None,
    )
    warnings = validate_included_service(row, VALIDATOR_SOURCE)
    assert any("not found in source" in w for w in warnings)


def test_validate_extraction_drops_hallucinated_numeric_terms():
    good = make_contract_term(value_numeric=18.5, value_text="AWP - 18.5 %")
    bad = make_contract_term(
        value_numeric=99.9,
        value_text="$99.99",
        source_row_label="Hallucinated metric",
    )
    result = ExtractionResult(
        metadata=DocumentMetadata(),
        contract_terms=[good, bad],
    )
    validated = validate_extraction(result, VALIDATOR_SOURCE)
    assert len(validated.contract_terms) == 1
    assert validated.contract_terms[0].value_numeric == 18.5


def test_validate_extraction_drops_hallucinated_fee_rows():
    good = make_included_service(
        service_name="Clinical prior authorization with physician review",
        source_section=SourceSection.ALLOWANCES_FEES,
        value_type=ValueType.NUMERIC,
        value_numeric=25.0,
        value_text="$25.00 per claim",
    )
    bad = make_included_service(
        service_name="Fake expensive service",
        source_section=SourceSection.ALLOWANCES_FEES,
        value_type=ValueType.NUMERIC,
        value_numeric=999.0,
        value_text="$999.00 per claim",
    )
    result = ExtractionResult(
        metadata=DocumentMetadata(),
        included_services=[good, bad],
    )
    validated = validate_extraction(result, VALIDATOR_SOURCE)
    names = [s.service_name for s in validated.included_services]
    assert "Clinical prior authorization with physician review" in names
    assert "Fake expensive service" not in names


def test_validate_extraction_passes_assumptions_unchanged():
    assumptions = [AssumptionRow(category="General", bullet_text="Test assumption")]
    result = ExtractionResult(
        metadata=DocumentMetadata(),
        assumptions=assumptions,
    )
    validated = validate_extraction(result, VALIDATOR_SOURCE)
    assert validated.assumptions == assumptions


def test_validate_extraction_no_terms_survived_warning():
    bad = make_contract_term(value_numeric=99.9, value_text="$99.99")
    result = ExtractionResult(
        metadata=DocumentMetadata(),
        contract_terms=[bad],
    )
    validated = validate_extraction(result, VALIDATOR_SOURCE)
    assert not validated.contract_terms
    assert "No contract terms survived validation" in validated.warnings


def test_validate_extraction_included_services_fallback_when_all_filtered():
    """When every included service fails name check, originals are preserved."""
    service = make_included_service(service_name="Completely fabricated service name")
    result = ExtractionResult(
        metadata=DocumentMetadata(),
        included_services=[service],
    )
    validated = validate_extraction(result, VALIDATOR_SOURCE)
    assert validated.included_services == [service]
    assert any("Completely fabricated service name" in w for w in validated.warnings)


def test_validate_contract_term_rebate_kept_with_payment_schedule_warning():
    row = make_contract_term(
        term_category=TermCategory.REBATE,
        payment_schedule=None,
        value_numeric=1.5,
        value_text="$1.50",
    )
    source = "2026 1.50 2.00 3.00 4.00"
    result = ExtractionResult(metadata=DocumentMetadata(), contract_terms=[row])
    validated = validate_extraction(result, source)
    assert len(validated.contract_terms) == 1
    assert any("payment_schedule" in w for w in validated.warnings)


def test_value_appears_in_source_comma_formatted():
    source = "Implementation allowance of $1,500.00 per year for setup"
    assert value_appears_in_source("$1,500.00", source)
    assert value_appears_in_source("1500.00", source)
