"""Unit tests for extract.rule_parser."""

from datetime import date

from models.enums import PaymentSchedule, PricingModel, TermCategory, ValueType
from extract.rule_parser import (
    parse_admin_fees,
    parse_document_metadata,
    parse_pricing_section,
    parse_rebate_guarantees,
)

from tests.fixtures.snippets import (
    COVER_PAGE,
    REBATE_GUARANTEES_SECTION,
    TRADITIONAL_PRICING_SECTION,
)


def test_parse_document_metadata():
    meta = parse_document_metadata(COVER_PAGE)
    assert meta["vendor_name"] == "Northwind PBM"
    assert meta["client_name"] == "Acme Corporation"
    assert meta["proposal_date"] == date(2026, 1, 15)


def test_parse_admin_fees():
    rows = parse_admin_fees(TRADITIONAL_PRICING_SECTION, PricingModel.TRADITIONAL, 1)
    assert len(rows) >= 2
    assert all(r.term_category == TermCategory.ADMIN_FEE for r in rows)
    years = {r.calendar_year for r in rows}
    assert 2026 in years
    assert 2027 in years


def test_parse_pricing_section_network_discount():
    rows = parse_pricing_section(TRADITIONAL_PRICING_SECTION, PricingModel.TRADITIONAL, 1)
    discount_rows = [r for r in rows if r.term_category == TermCategory.NETWORK_DISCOUNT]
    assert discount_rows
    awp_rows = [r for r in discount_rows if r.value_numeric == 18.5]
    assert awp_rows
    assert awp_rows[0].calendar_year == 2026


def test_parse_rebate_guarantees():
    rows = parse_rebate_guarantees(REBATE_GUARANTEES_SECTION, 2)
    assert rows
    assert all(r.term_category == TermCategory.REBATE for r in rows)
    assert all(r.payment_schedule is not None for r in rows)
    assert any(r.payment_schedule == PaymentSchedule.QUARTERLY_150D for r in rows)
    assert all(r.value_type == ValueType.NUMERIC for r in rows)
