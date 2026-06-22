"""Fallback parsers for text-heavy sections when LLM is unavailable."""

from __future__ import annotations

import re

from models.enums import FeeType, SourceSection, ValueType
from models.extraction import AssumptionRow, IncludedServiceRow
from extract.normalizer import parse_single_value


def parse_included_services(section_text: str) -> list[IncludedServiceRow]:
    services: list[IncludedServiceRow] = []
    current_category = "General"
    for line in section_text.splitlines():
        line = line.strip()
        if not line or "(Included Services)" in line:
            continue
        if not _is_bullet_line(line):
            if line.endswith("Services") or line.endswith("Tools") or line.endswith("Management"):
                current_category = line
            continue
        bullet = _strip_bullet(line)
        if not bullet:
            continue
        services.append(
            IncludedServiceRow(
                category=current_category,
                service_name=bullet,
                is_included=True,
                source_section=SourceSection.INCLUDED_SERVICES,
            )
        )
    return services


FEE_SUBCATEGORIES = {
    "Eligibility Maintenance",
    "Reporting and IT Support",
    "ID Cards and Member Communication",
}

_ALLOWANCE_CATEGORIES = frozenset({
    "Implementation Allowances",
    "Pharmacy Management Fund",
})


def _split_service_and_cost(line: str) -> tuple[str, str] | None:
    lowered = line.lower()
    if lowered.endswith(" included"):
        return line[: lowered.rfind(" included")].strip(), "Included"
    if "quoted upon request" in lowered:
        idx = lowered.index("quoted upon request")
        return line[:idx].strip(), line[idx:].strip()
    dollar_match = re.search(r"\s+(\$\s*.+)$", line)
    if dollar_match:
        return line[: dollar_match.start()].strip(), dollar_match.group(1).strip()
    users_match = re.search(r"\s+(\d+\s+users:\s*Included)$", line, re.IGNORECASE)
    if users_match:
        return line[: users_match.start()].strip(), users_match.group(1).strip()
    return None


def parse_fee_schedule(section_text: str) -> list[IncludedServiceRow]:
    rows: list[IncludedServiceRow] = []
    current_category = "General"
    current_subcategory = ""

    lines = [line.strip() for line in section_text.splitlines() if line.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        if _is_category_header(line):
            current_category = line
            current_subcategory = ""
            i += 1
            continue
        if line in FEE_SUBCATEGORIES:
            current_subcategory = line
            i += 1
            continue
        if line in {"Service", "Service Cost", "Year Fee", "update"}:
            i += 1
            continue

        split = _split_service_and_cost(line)
        if split:
            service_name, cost_text = split
            label = f"{current_subcategory}: {service_name}" if current_subcategory else service_name
            _append_fee_row(rows, label, cost_text, current_category)
            i += 1
            continue

        service_name = line
        cost_parts: list[str] = []
        i += 1
        while i < len(lines):
            next_line = lines[i]
            if _is_category_header(next_line) or next_line in FEE_SUBCATEGORIES:
                break
            if next_line in {"update"}:
                i += 1
                continue
            nested = _split_service_and_cost(next_line)
            if nested and not cost_parts:
                service_name, cost_text = nested
                label = (
                    f"{current_subcategory}: {service_name}" if current_subcategory else service_name
                )
                _append_fee_row(rows, label, cost_text, current_category)
                i += 1
                break
            if _line_has_cost(next_line):
                cost_parts.append(next_line)
                i += 1
                break
            break

        if cost_parts:
            cost_text = " ".join(cost_parts).strip()
            label = f"{current_subcategory}: {service_name}" if current_subcategory else service_name
            _append_fee_row(rows, label, cost_text, current_category)

    return rows


def _line_has_cost(line: str) -> bool:
    lowered = line.lower()
    return (
        "$" in line
        or lowered.startswith("included")
        or "quoted upon request" in lowered
        or "pass-through" in lowered
        or bool(re.match(r"^\d+\s+users:", lowered))
    )


def _append_fee_row(
    rows: list[IncludedServiceRow],
    service_name: str,
    cost_text: str,
    current_category: str,
) -> None:
    parsed = parse_single_value(cost_text, None)
    value_type = parsed.value_type
    if "included" in cost_text.lower() and parsed.value_numeric is None:
        value_type = ValueType.INCLUDED
    if "quoted upon request" in cost_text.lower():
        value_type = ValueType.QUOTED_UPON_REQUEST
    if "pass-through" in cost_text.lower():
        value_type = ValueType.PASS_THROUGH

    fee_type = FeeType.ALLOWANCE if current_category in _ALLOWANCE_CATEGORIES else FeeType.ANCILLARY_FEE

    rows.append(
        IncludedServiceRow(
            category=current_category,
            service_name=service_name,
            is_included=value_type == ValueType.INCLUDED,
            cost_summary=cost_text,
            source_section=SourceSection.ALLOWANCES_FEES,
            fee_type=fee_type,
            value_type=value_type,
            value_text=cost_text,
            value_numeric=parsed.value_numeric,
            basis_type=parsed.basis_type,
            unit_label=parsed.unit_label,
        )
    )


def _is_category_header(line: str) -> bool:
    return line in {
        "Implementation Allowances",
        "Pharmacy Management Fund",
        "Additional Administrative Services",
        "Reporting and IT Support",
        "ID Cards and Member Communication",
        "Pharmacy Fraud, Waste, Abuse Programs",
        "Other Programs and Services",
        "Additional Claim Fees",
    }


def _is_bullet_line(line: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith("•")
        or stripped.startswith("-")
        or stripped.startswith("(cid:127)")
        or stripped.startswith("\u2022")
    )


def _strip_bullet(line: str) -> str:
    stripped = line.strip()
    for prefix in ("(cid:127)", "•", "-", "\u2022"):
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return stripped


def parse_assumptions(section_text: str) -> list[AssumptionRow]:
    assumptions: list[AssumptionRow] = []
    current_category = "General Assumptions"
    for line in section_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if not _is_bullet_line(line):
            if "Assumptions" in line or "Notes" in line:
                current_category = line
            continue
        bullet = _strip_bullet(line)
        if bullet:
            assumptions.append(AssumptionRow(category=current_category, bullet_text=bullet))
    return assumptions
