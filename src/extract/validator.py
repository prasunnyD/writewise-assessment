"""Validation and anti-hallucination checks for extracted rows."""

from __future__ import annotations

import re

from models.enums import SourceSection, ValueType
from models.extraction import ContractTermRow, ExtractionResult, IncludedServiceRow


def _normalize_for_search(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def value_appears_in_source(value_text: str, source_text: str) -> bool:
    if not value_text:
        return False
    normalized_source = _normalize_for_search(source_text)
    normalized_value = _normalize_for_search(value_text)

    if normalized_value in normalized_source:
        return True

    numeric_matches = re.findall(r"[\d.]+", value_text)
    if numeric_matches:
        return all(num in source_text.replace(",", "") for num in numeric_matches if num)

    return False


def validate_contract_term(row: ContractTermRow, source_text: str) -> list[str]:
    warnings: list[str] = []
    if row.value_type.value == "numeric" and row.value_numeric is not None:
        num_str = f"{row.value_numeric:g}"
        if num_str not in source_text.replace(",", ""):
            alt = f"{row.value_numeric:.2f}"
            if alt not in source_text.replace(",", ""):
                warnings.append(
                    f"Numeric value {row.value_numeric} for '{row.source_row_label}' "
                    "not found in source text"
                )

    if row.value_text and not value_appears_in_source(row.value_text, source_text):
        if row.value_type.value != "included":
            warnings.append(
                f"Value text '{row.value_text[:60]}' for '{row.source_row_label}' "
                "not verified in source"
            )

    if row.term_category.value == "rebate" and not row.payment_schedule:
        warnings.append("Rebate row missing payment_schedule")

    return warnings


def validate_included_service(row: IncludedServiceRow, source_text: str) -> list[str]:
    warnings: list[str] = []

    if row.source_section == SourceSection.ALLOWANCES_FEES:
        if row.value_type == ValueType.NUMERIC and row.value_numeric is not None:
            num_str = f"{row.value_numeric:g}"
            if num_str not in source_text.replace(",", ""):
                alt = f"{row.value_numeric:.2f}"
                if alt not in source_text.replace(",", ""):
                    warnings.append(
                        f"Numeric value {row.value_numeric} for '{row.service_name}' "
                        "not found in source text"
                    )
        if row.value_text and not value_appears_in_source(row.value_text, source_text):
            if row.value_type != ValueType.INCLUDED:
                warnings.append(
                    f"Value text '{row.value_text[:60]}' for '{row.service_name}' "
                    "not verified in source"
                )
        if row.service_name.lower() not in source_text.lower():
            warnings.append(f"Fee service not found in source: {row.service_name}")
        return warnings

    if row.service_name.lower() not in source_text.lower():
        warnings.append(f"Included service not found in source: {row.service_name}")
    return warnings


def validate_extraction(result: ExtractionResult, source_corpus: str) -> ExtractionResult:
    all_warnings = list(result.warnings)
    validated_terms: list[ContractTermRow] = []

    for row in result.contract_terms:
        row_warnings = validate_contract_term(row, source_corpus)
        if row_warnings and row.value_type.value == "numeric" and row.value_numeric is not None:
            num_str = f"{row.value_numeric:g}"
            if num_str not in source_corpus.replace(",", ""):
                continue
        validated_terms.append(row)
        all_warnings.extend(row_warnings)

    validated_services: list[IncludedServiceRow] = []
    for service in result.included_services:
        row_warnings = validate_included_service(service, source_corpus)
        if (
            service.source_section == SourceSection.ALLOWANCES_FEES
            and service.value_type == ValueType.NUMERIC
            and service.value_numeric is not None
        ):
            num_str = f"{service.value_numeric:g}"
            if num_str not in source_corpus.replace(",", ""):
                continue
        if service.service_name.lower() in source_corpus.lower() or (
            service.source_section == SourceSection.ALLOWANCES_FEES
            and service.value_text
            and value_appears_in_source(service.value_text, source_corpus)
        ):
            validated_services.append(service)
        else:
            all_warnings.append(f"Service not found in source: {service.service_name}")
        all_warnings.extend(row_warnings)

    if not validated_terms:
        all_warnings.append("No contract terms survived validation")

    return ExtractionResult(
        metadata=result.metadata,
        contract_terms=validated_terms,
        included_services=validated_services or result.included_services,
        assumptions=result.assumptions,
        warnings=all_warnings,
        raw_markdown=result.raw_markdown,
        networks=result.networks,
        pricing_models=result.pricing_models,
    )
