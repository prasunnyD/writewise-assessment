"""Unit tests for extract.text_parser."""

from models.enums import FeeType, SourceSection, ValueType
from extract.text_parser import (
    parse_assumptions,
    parse_fee_schedule,
    parse_included_services,
)

from tests.fixtures.snippets import (
    ALLOWANCES_FEES_SECTION,
    ASSUMPTIONS_SECTION,
    INCLUDED_SERVICES_SECTION,
)


def test_parse_included_services_bullets_and_categories():
    services = parse_included_services(INCLUDED_SERVICES_SECTION)
    names = [s.service_name for s in services]
    assert "Prior authorization review" in names
    assert "24/7 nurse hotline" in names
    assert all(s.source_section == SourceSection.INCLUDED_SERVICES for s in services)
    assert all(s.is_included for s in services)


def test_parse_fee_schedule_allowance_and_ancillary():
    rows = parse_fee_schedule(ALLOWANCES_FEES_SECTION)
    assert rows
    by_name = {r.service_name: r for r in rows}
    assert "Setup and conversion" in by_name
    setup = by_name["Setup and conversion"]
    assert setup.fee_type == FeeType.ALLOWANCE
    assert setup.value_numeric == 5000.0

    eligibility = by_name["Eligibility Maintenance: Monthly eligibility file"]
    assert eligibility.value_type == ValueType.INCLUDED
    assert eligibility.is_included

    clinical = by_name["Clinical prior authorization with physician review"]
    assert clinical.fee_type == FeeType.ANCILLARY_FEE
    assert clinical.value_numeric == 25.0


def test_parse_assumptions():
    assumptions = parse_assumptions(ASSUMPTIONS_SECTION)
    assert len(assumptions) >= 2
    texts = [a.bullet_text for a in assumptions]
    assert any("50,000 covered lives" in t for t in texts)
    assert all(a.category for a in assumptions)
