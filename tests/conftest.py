"""Shared pytest fixtures for extraction pipeline tests."""

from __future__ import annotations

import pytest

from models.enums import (
    PricingModel,
    SourceSection,
    TermCategory,
    ValueType,
)
from models.extraction import ContractTermRow, IncludedServiceRow

from tests.fixtures.snippets import VALIDATOR_SOURCE


@pytest.fixture
def sample_source_corpus() -> str:
    return VALIDATOR_SOURCE


def make_contract_term(**overrides) -> ContractTermRow:
    defaults = {
        "pricing_model_id": PricingModel.TRADITIONAL,
        "network_id": "retail_90",
        "term_category": TermCategory.NETWORK_DISCOUNT,
        "calendar_year": 2026,
        "value_type": ValueType.NUMERIC,
        "value_text": "AWP - 18.5 %",
        "value_numeric": 18.5,
        "source_row_label": "Brand Effective Discount",
    }
    defaults.update(overrides)
    return ContractTermRow(**defaults)


def make_included_service(**overrides) -> IncludedServiceRow:
    defaults = {
        "category": "Clinical Services",
        "service_name": "Prior authorization review",
        "is_included": True,
        "source_section": SourceSection.INCLUDED_SERVICES,
    }
    defaults.update(overrides)
    return IncludedServiceRow(**defaults)
