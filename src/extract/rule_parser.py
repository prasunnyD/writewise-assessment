"""Rule-based parsing for structured pricing and rebate sections."""

from __future__ import annotations

import re

from models.enums import (
    BasisType,
    PaymentSchedule,
    PricingModel,
    RebateChannel,
    TermCategory,
    ValueType,
)
from models.extraction import ContractTermRow
from extract.normalizer import (
    infer_drug_type,
    infer_term_category,
    parse_single_value,
    year_value_to_contract_term,
)

METRIC_HEADERS = [
    "Brand Discount",
    "Generic Discount",
    "Dispensing Fee",
    "Brand Effective Discount",
    "Generic Effective Rate",
    "LDD",
    "New to market",
]

YEAR_VALUE_GLOBAL = re.compile(
    r"(20\d{2})\s*:\s*"
    r"(\$[\d,]+(?:\.\d+)?(?:\s+per\s+[\w\s]+)?|AWP\s*-\s*[\d.]+\s*%|"
    r"\$[\d,]+(?:\.\d+)?|Included|Quoted upon request[^.]*|pass-through[^.]*)",
    re.IGNORECASE,
)


def parse_document_metadata(full_text: str) -> dict:
    vendor_match = re.search(r"(Northwind\w*\.?\w*)", full_text, re.IGNORECASE)
    client_match = re.search(r"Brightline Health", full_text)
    date_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
        full_text,
    )
    proposal_date = None
    if date_match:
        from datetime import datetime

        proposal_date = datetime.strptime(date_match.group(0), "%B %d, %Y").date()

    return {
        "vendor_name": vendor_match.group(1) if vendor_match else None,
        "client_name": client_match.group(0) if client_match else None,
        "proposal_date": proposal_date,
    }


def parse_admin_fees(
    section_text: str, pricing_model: PricingModel, page_number: int
) -> list[ContractTermRow]:
    rows: list[ContractTermRow] = []
    admin_block = _extract_block(section_text, "Administrative Fee", "Network Guarantees")
    if not admin_block:
        return rows

    for line in admin_block.splitlines():
        year_match = re.match(r"^(20\d{2})\s+(.+)$", line.strip())
        if not year_match:
            continue
        year = int(year_match.group(1))
        value_text = year_match.group(2).strip()
        parsed = parse_single_value(value_text, year)
        rows.append(
            ContractTermRow(
                pricing_model_id=pricing_model,
                term_category=TermCategory.ADMIN_FEE,
                calendar_year=year,
                value_type=parsed.value_type,
                value_text=parsed.value_text,
                value_numeric=parsed.value_numeric,
                basis_type=parsed.basis_type or BasisType.DOLLAR_PER_CLAIM,
                unit_label=parsed.unit_label or "per approved paid claim",
                section_title=pricing_model.value,
                page_number=page_number,
                source_row_label="Administrative Fee",
            )
        )
    return rows


def parse_pricing_section(
    section_text: str,
    pricing_model: PricingModel,
    page_number: int,
) -> list[ContractTermRow]:
    rows: list[ContractTermRow] = []
    rows.extend(parse_admin_fees(section_text, pricing_model, page_number))

    network_block = _extract_block(section_text, "Network Guarantees", "Mail Order")
    if network_block:
        rows.extend(
            _parse_multi_column_metrics(
                network_block,
                pricing_model,
                page_number,
                networks=["broad_national", "retail_90"],
                retail_30_mirror="broad_national",
            )
        )

    subsection_specs = [
        ("Mail Order", "mail", ["mail"]),
        ("Retail Specialty", "retail_specialty", ["retail_specialty"]),
        (
            "Exclusive Specialty",
            "northwind_direct_specialty",
            ["northwind_direct_specialty"],
        ),
    ]
    for header, network_id, networks in subsection_specs:
        block = _extract_network_subsection(section_text, header)
        if block:
            rows.extend(
                _parse_multi_column_metrics(
                    block,
                    pricing_model,
                    page_number,
                    networks=networks,
                )
            )

    return rows


def _extract_block(text: str, start: str, end: str | None) -> str:
    start_idx = text.find(start)
    if start_idx == -1:
        return ""
    content_start = start_idx + len(start)
    if end:
        end_idx = text.find(end, content_start)
        if end_idx == -1:
            return text[content_start:].strip()
        return text[content_start:end_idx].strip()
    return text[content_start:].strip()


def _extract_network_subsection(text: str, network_header: str) -> str:
    start = text.find(network_header)
    if start == -1:
        return ""
    rest = text[start + len(network_header) :]
    next_headers = [
        "Mail Order",
        "Retail Specialty",
        "Exclusive Specialty",
        "Rebate Guarantees",
        "Traditional Pricing",
        "CONFIDENTIAL",
    ]
    end_positions = [rest.find(h) for h in next_headers if rest.find(h) > 0]
    end = min(end_positions) if end_positions else len(rest)
    return rest[:end].strip()


def _split_by_metrics(text: str) -> list[tuple[str, str]]:
    pattern = "|".join(re.escape(metric) for metric in METRIC_HEADERS)
    parts = re.split(f"({pattern})", text)
    blocks: list[tuple[str, str]] = []
    current_metric: str | None = None
    buffer: list[str] = []

    for part in parts:
        if part in METRIC_HEADERS:
            if current_metric and buffer:
                blocks.append((current_metric, " ".join(buffer)))
            current_metric = part
            buffer = []
        else:
            buffer.append(part)
    if current_metric and buffer:
        blocks.append((current_metric, " ".join(buffer)))
    return blocks


def _parse_multi_column_metrics(
    text: str,
    pricing_model: PricingModel,
    page_number: int,
    networks: list[str],
    retail_30_mirror: str | None = None,
) -> list[ContractTermRow]:
    rows: list[ContractTermRow] = []
    for metric_name, metric_text in _split_by_metrics(text):
        pairs = YEAR_VALUE_GLOBAL.findall(metric_text)
        if not pairs:
            continue

        drug_type = infer_drug_type(metric_name)
        term_category = infer_term_category(metric_name)
        columns = len(networks)

        if columns == 1:
            for year_str, value_text in pairs:
                year_value = parse_single_value(value_text.strip(), int(year_str))
                rows.append(
                    year_value_to_contract_term(
                        year_value=year_value,
                        pricing_model_id=pricing_model,
                        network_id=networks[0],
                        term_category=term_category,
                        drug_type=drug_type,
                        section_title=pricing_model.value,
                        page_number=page_number,
                        source_row_label=metric_name,
                    )
                )
            continue

        for index, (year_str, value_text) in enumerate(pairs):
            network_id = networks[index % columns]
            year_value = parse_single_value(value_text.strip(), int(year_str))
            rows.append(
                year_value_to_contract_term(
                    year_value=year_value,
                    pricing_model_id=pricing_model,
                    network_id=network_id,
                    term_category=term_category,
                    drug_type=drug_type,
                    section_title=pricing_model.value,
                    page_number=page_number,
                    source_row_label=metric_name,
                )
            )
            if retail_30_mirror and network_id == retail_30_mirror:
                rows.append(
                    year_value_to_contract_term(
                        year_value=year_value,
                        pricing_model_id=pricing_model,
                        network_id="retail_30",
                        term_category=term_category,
                        drug_type=drug_type,
                        section_title=pricing_model.value,
                        page_number=page_number,
                        source_row_label=metric_name,
                    )
                )

    return rows


def parse_rebate_guarantees(section_text: str, page_number: int) -> list[ContractTermRow]:
    rows: list[ContractTermRow] = []
    blocks = re.split(
        r"Northwind Performance\s+Per Brand Drug — Rebates paid (\d+) days after the (quarter|month)",
        section_text,
        flags=re.IGNORECASE,
    )

    i = 1
    while i < len(blocks):
        days = blocks[i]
        period = blocks[i + 1]
        body = blocks[i + 2] if i + 2 < len(blocks) else ""
        if period.lower() == "quarter":
            schedule = PaymentSchedule.QUARTERLY_150D
            timing = f"{days} days after the quarter"
        else:
            schedule = PaymentSchedule.MONTHLY_60D
            timing = f"{days} days after the month"
        rows.extend(_parse_rebate_table(body, schedule, timing, page_number))
        i += 3

    if not rows:
        rows.extend(_parse_rebate_table_fallback(section_text, page_number))
    return rows


def _parse_rebate_table(
    body: str,
    schedule: PaymentSchedule,
    timing: str,
    page_number: int,
) -> list[ContractTermRow]:
    rows: list[ContractTermRow] = []
    for line in body.splitlines():
        line = line.strip()
        year_match = re.match(
            r"^(20\d{2})\s+\$?([\d,]+(?:\.\d+)?)\s+\$?([\d,]+(?:\.\d+)?)\s+\$?([\d,]+(?:\.\d+)?)\s+\$?([\d,]+(?:\.\d+)?)",
            line,
        )
        if not year_match:
            continue
        year = int(year_match.group(1))
        amounts = [float(v.replace(",", "")) for v in year_match.groups()[1:]]
        channels = [
            RebateChannel.RETAIL_30,
            RebateChannel.RETAIL_90,
            RebateChannel.MAIL,
            RebateChannel.SPECIALTY,
        ]
        for channel, amount in zip(channels, amounts):
            rows.append(
                ContractTermRow(
                    term_category=TermCategory.REBATE,
                    channel=channel,
                    calendar_year=year,
                    payment_schedule=schedule,
                    payment_timing_text=timing,
                    formulary_name="Northwind Performance exclusionary formulary",
                    value_type=ValueType.NUMERIC,
                    value_text=f"${amount:,.2f}",
                    value_numeric=amount,
                    basis_type=BasisType.PER_BRAND_DRUG,
                    unit_label="per brand drug",
                    section_title="Rebate Guarantees",
                    page_number=page_number,
                    source_row_label=f"Rebate guarantee ({schedule.value})",
                )
            )
    return rows


def _parse_rebate_table_fallback(section_text: str, page_number: int) -> list[ContractTermRow]:
    rows: list[ContractTermRow] = []
    current_schedule = PaymentSchedule.QUARTERLY_150D
    current_timing = "150 days after the quarter"
    for line in section_text.splitlines():
        if "60 days after the month" in line:
            current_schedule = PaymentSchedule.MONTHLY_60D
            current_timing = "60 days after the month"
        year_match = re.match(
            r"^(20\d{2})\s+\$?([\d,]+(?:\.\d+)?)\s+\$?([\d,]+(?:\.\d+)?)\s+\$?([\d,]+(?:\.\d+)?)\s+\$?([\d,]+(?:\.\d+)?)",
            line.strip(),
        )
        if year_match:
            year = int(year_match.group(1))
            amounts = [float(v.replace(",", "")) for v in year_match.groups()[1:]]
            channels = [
                RebateChannel.RETAIL_30,
                RebateChannel.RETAIL_90,
                RebateChannel.MAIL,
                RebateChannel.SPECIALTY,
            ]
            for channel, amount in zip(channels, amounts):
                rows.append(
                    ContractTermRow(
                        term_category=TermCategory.REBATE,
                        channel=channel,
                        calendar_year=year,
                        payment_schedule=current_schedule,
                        payment_timing_text=current_timing,
                        formulary_name="Northwind Performance exclusionary formulary",
                        value_type=ValueType.NUMERIC,
                        value_text=f"${amount:,.2f}",
                        value_numeric=amount,
                        basis_type=BasisType.PER_BRAND_DRUG,
                        unit_label="per brand drug",
                        section_title="Rebate Guarantees",
                        page_number=page_number,
                        source_row_label=f"Rebate guarantee ({current_schedule.value})",
                    )
                )
    return rows
