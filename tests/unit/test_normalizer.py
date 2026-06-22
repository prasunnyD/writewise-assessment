"""Unit tests for extract.normalizer."""

from models.enums import BasisType, DrugType, TermCategory, ValueType
from extract.normalizer import (
    infer_drug_type,
    infer_term_category,
    parse_single_value,
    parse_year_values,
)


def test_parse_single_value_included():
    """Parse Included as an included value type."""
    result = parse_single_value("Included", 2026)
    assert result.value_type == ValueType.INCLUDED
    assert result.calendar_year == 2026


def test_parse_single_value_awp_percent():
    """Parse AWP minus percent values."""
    result = parse_single_value("AWP - 18.5 %", 2026)
    assert result.value_type == ValueType.NUMERIC
    assert result.value_numeric == 18.5
    assert result.basis_type == BasisType.AWP_MINUS_PERCENT


def test_parse_single_value_per_claim():
    """Parse dollar-per-claim values."""
    result = parse_single_value("$2.50 per claim", 2026)
    assert result.value_numeric == 2.5
    assert result.basis_type == BasisType.DOLLAR_PER_CLAIM
    assert result.unit_label == "per claim"


def test_parse_single_value_quoted_upon_request():
    """Parse quoted-upon-request values."""
    result = parse_single_value("Quoted upon request", None)
    assert result.value_type == ValueType.QUOTED_UPON_REQUEST


def test_parse_single_value_pass_through():
    """Parse pass-through values."""
    result = parse_single_value("pass-through cost", None)
    assert result.value_type == ValueType.PASS_THROUGH


def test_parse_year_values_multi_year():
    """Parse multiple year:value pairs from one string."""
    raw = "2026: AWP - 20% / 2027: AWP - 22%"
    results = parse_year_values(raw)
    assert len(results) == 2
    assert results[0].calendar_year == 2026
    assert results[0].value_numeric == 20.0
    assert results[1].calendar_year == 2027
    assert results[1].value_numeric == 22.0


def test_parse_year_values_single_value_fallback():
    """Parse a single value when no year prefix is present."""
    results = parse_year_values("AWP - 15 %")
    assert len(results) == 1
    assert results[0].value_numeric == 15.0


def test_infer_drug_type_brand():
    """Infer brand drug type from metric names."""
    assert infer_drug_type("Brand Effective Discount") == DrugType.BRAND


def test_infer_drug_type_generic():
    """Infer generic drug type from metric names."""
    assert infer_drug_type("Generic Effective Rate") == DrugType.GENERIC


def test_infer_term_category_network_discount():
    """Infer network discount category from metric names."""
    assert infer_term_category("Brand Effective Discount") == TermCategory.NETWORK_DISCOUNT


def test_infer_term_category_admin_fee():
    """Infer admin fee category from metric names."""
    assert infer_term_category("Administrative Fee") == TermCategory.ADMIN_FEE


def test_infer_term_category_dispensing_fee():
    """Infer dispensing fee category from metric names."""
    assert infer_term_category("Dispensing Fee") == TermCategory.DISPENSING_FEE
