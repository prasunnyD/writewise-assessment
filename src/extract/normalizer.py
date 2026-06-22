"""Deterministic normalization of extracted contract values."""

from __future__ import annotations

import re

from models.enums import BasisType, DrugType, TermCategory, ValueType
from models.extraction import ContractTermRow, YearValue

YEAR_VALUE_PATTERN = re.compile(
    r"(?P<year>20\d{2})\s*:\s*(?P<value>.+?)(?=\s*20\d{2}\s*:|$)",
    re.DOTALL,
)
AWP_PATTERN = re.compile(r"AWP\s*-\s*(?P<pct>[\d.]+)\s*%", re.IGNORECASE)
MONEY_PATTERN = re.compile(r"\$\s*(?P<amount>[\d,]+(?:\.\d+)?)")
PER_CLAIM_PATTERN = re.compile(r"per\s+(?:approved\s+paid\s+)?claim", re.IGNORECASE)


def parse_year_values(raw: str) -> list[YearValue]:
    raw = raw.strip()
    if not raw:
        return []

    matches = list(YEAR_VALUE_PATTERN.finditer(raw))
    if not matches:
        return [parse_single_value(raw, calendar_year=None)]

    results: list[YearValue] = []
    for match in matches:
        year = int(match.group("year"))
        value_text = match.group("value").strip().strip("/")
        results.append(parse_single_value(value_text, calendar_year=year))
    return results


def parse_single_value(value_text: str, calendar_year: int | None) -> YearValue:
    value_text = value_text.strip()
    lowered = value_text.lower()

    if lowered in {"included", "included."}:
        return YearValue(
            calendar_year=calendar_year or 0,
            value_text=value_text,
            value_type=ValueType.INCLUDED,
        )
    if "quoted upon request" in lowered:
        return YearValue(
            calendar_year=calendar_year or 0,
            value_text=value_text,
            value_type=ValueType.QUOTED_UPON_REQUEST,
        )
    if "pass-through" in lowered or "pass through" in lowered:
        return YearValue(
            calendar_year=calendar_year or 0,
            value_text=value_text,
            value_type=ValueType.PASS_THROUGH,
        )

    awp_match = AWP_PATTERN.search(value_text)
    if awp_match:
        return YearValue(
            calendar_year=calendar_year or 0,
            value_text=value_text,
            value_numeric=float(awp_match.group("pct")),
            basis_type=BasisType.AWP_MINUS_PERCENT,
            value_type=ValueType.NUMERIC,
        )

    money_match = MONEY_PATTERN.search(value_text)
    value_numeric = None
    basis_type = None
    unit_label = None
    if money_match:
        value_numeric = float(money_match.group("amount").replace(",", ""))
        if PER_CLAIM_PATTERN.search(value_text):
            basis_type = BasisType.DOLLAR_PER_CLAIM
            unit_label = "per claim"
        elif "pmpm" in lowered:
            basis_type = BasisType.PMPM
            unit_label = "PMPM"
        elif "pmpy" in lowered:
            basis_type = BasisType.PMPY
            unit_label = "PMPY"
        elif "per record" in lowered:
            basis_type = BasisType.PER_RECORD
            unit_label = "per record"
        elif "per audit" in lowered:
            basis_type = BasisType.PER_AUDIT
            unit_label = "per audit"
        elif "per hour" in lowered or "programming hour" in lowered:
            basis_type = BasisType.PER_HOUR
            unit_label = "per hour"
        elif "per member per year" in lowered:
            basis_type = BasisType.PER_MEMBER_PER_YEAR
            unit_label = "per member per year"
        elif "per member" in lowered:
            basis_type = BasisType.PER_MEMBER
            unit_label = "per member"
        elif "per year" in lowered:
            basis_type = BasisType.FLAT_ANNUAL
            unit_label = "per year"
        elif "each" in lowered:
            basis_type = BasisType.OTHER
            unit_label = "each"

    return YearValue(
        calendar_year=calendar_year or 0,
        value_text=value_text,
        value_numeric=value_numeric,
        basis_type=basis_type,
        value_type=ValueType.NUMERIC if value_numeric is not None else ValueType.TEXT,
        unit_label=unit_label,
    )


def infer_drug_type(metric_name: str) -> DrugType | None:
    lowered = metric_name.lower()
    if "brand effective discount" in lowered or lowered.startswith("brand"):
        return DrugType.BRAND
    if "generic effective rate" in lowered or lowered.startswith("generic"):
        return DrugType.GENERIC
    if lowered == "ldd":
        return DrugType.LDD
    if "new to market" in lowered:
        return DrugType.NEW_TO_MARKET
    return None


def infer_term_category(metric_name: str) -> TermCategory:
    lowered = metric_name.lower()
    if "dispensing fee" in lowered:
        return TermCategory.DISPENSING_FEE
    if "administrative fee" in lowered or lowered == "fee":
        return TermCategory.ADMIN_FEE
    if "discount" in lowered or "effective rate" in lowered:
        return TermCategory.NETWORK_DISCOUNT
    return TermCategory.NETWORK_DISCOUNT


def year_value_to_contract_term(
    *,
    year_value: YearValue,
    pricing_model_id,
    network_id: str | None,
    term_category: TermCategory,
    drug_type: DrugType | None,
    section_title: str,
    page_number: int | None,
    source_row_label: str,
) -> ContractTermRow:
    calendar_year = year_value.calendar_year if year_value.calendar_year not in (None, 0) else None
    return ContractTermRow(
        pricing_model_id=pricing_model_id,
        network_id=network_id,
        term_category=term_category,
        drug_type=drug_type,
        calendar_year=calendar_year,
        value_type=year_value.value_type,
        value_text=year_value.value_text,
        value_numeric=year_value.value_numeric,
        basis_type=year_value.basis_type,
        unit_label=year_value.unit_label,
        section_title=section_title,
        page_number=page_number,
        source_row_label=source_row_label,
    )
