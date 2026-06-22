"""Orchestrate PDF parsing, extraction, validation, and loading."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from models.enums import PricingModel, SourceSection
from models.extraction import (
    DocumentMetadata,
    ExtractionResult,
    IncludedServiceRow,
    NetworkRef,
    PricingModelRef,
)
from extract.document_converter import pdf_to_markdown
from extract.llm_extractor import LLMClient
from extract.markdown_sections import MarkdownSection, get_section, split_markdown_sections
from extract.rule_parser import (
    parse_document_metadata,
    parse_pricing_section,
    parse_rebate_guarantees,
)
from extract.text_parser import parse_assumptions, parse_fee_schedule, parse_included_services
from extract.validator import validate_extraction

load_dotenv()


def _supplement_services_from_rules(
    markdown: str,
    included_services: list[IncludedServiceRow],
) -> tuple[list[IncludedServiceRow], list[str]]:
    """Fill Allowances and Ancillary Charges via rule parser; LLM often omits this section."""
    warnings: list[str] = []
    try:
        sections = split_markdown_sections(markdown)
    except ValueError:
        return included_services, warnings

    llm_included = [
        service
        for service in included_services
        if service.source_section == SourceSection.INCLUDED_SERVICES
    ]
    merged: list[IncludedServiceRow] = list(llm_included)

    fees_section = get_section(sections, "allowances_fees")
    if fees_section:
        rule_fees = parse_fee_schedule(fees_section.raw_text)
        if rule_fees:
            merged.extend(rule_fees)
            warnings.append(
                f"Fee schedule: {len(rule_fees)} rows from rule parser "
                "(Allowances and Ancillary Charges)."
            )

    if not llm_included:
        included_section = get_section(sections, "included_services")
        if included_section:
            merged.extend(parse_included_services(included_section.raw_text))

    return merged, warnings


def _extract_with_rules(sections: list[MarkdownSection], markdown: str) -> ExtractionResult:
    meta_dict = parse_document_metadata(markdown)
    metadata = DocumentMetadata(**meta_dict)

    contract_terms = []
    included_services = []
    assumptions = []

    traditional = get_section(sections, "traditional_pricing")
    if traditional:
        contract_terms.extend(
            parse_pricing_section(
                traditional.raw_text,
                PricingModel.TRADITIONAL,
                traditional.page_number,
            )
        )

    rebate = get_section(sections, "rebate_guarantees")
    if rebate:
        contract_terms.extend(parse_rebate_guarantees(rebate.raw_text, rebate.page_number))

    applied = get_section(sections, "applied_rebates_pricing")
    if applied:
        contract_terms.extend(
            parse_pricing_section(
                applied.raw_text,
                PricingModel.APPLIED_REBATES,
                applied.page_number,
            )
        )

    fees_section = get_section(sections, "allowances_fees")
    if fees_section:
        included_services.extend(parse_fee_schedule(fees_section.raw_text))

    included_section = get_section(sections, "included_services")
    if included_section:
        included_services.extend(parse_included_services(included_section.raw_text))

    assumptions_section = get_section(sections, "assumptions")
    if assumptions_section:
        assumptions = parse_assumptions(assumptions_section.raw_text)

    return ExtractionResult(
        metadata=metadata,
        contract_terms=contract_terms,
        included_services=included_services,
        assumptions=assumptions,
        warnings=["Rule-based fallback extraction (--no-llm); less accurate for new vendors."],
    )


def extract_from_pdf(pdf_path: str, use_llm: bool = True, *, validate: bool = True) -> ExtractionResult:
    markdown = pdf_to_markdown(pdf_path)

    if use_llm and os.environ.get("OPENAI_API_KEY"):
        try:
            llm_result = LLMClient().extract_from_markdown(markdown)
            supplemented_services, supplement_warnings = _supplement_services_from_rules(
                markdown,
                llm_result.included_services,
            )
            result = ExtractionResult(
                metadata=llm_result.metadata,
                contract_terms=llm_result.contract_terms,
                included_services=supplemented_services,
                assumptions=llm_result.assumptions,
                networks=llm_result.networks,
                pricing_models=llm_result.pricing_models,
                warnings=supplement_warnings,
                raw_markdown=markdown,
            )
        except Exception as exc:
            sections = split_markdown_sections(markdown)
            result = _extract_with_rules(sections, markdown)
            result.warnings.append(f"LLM extraction failed, using rule fallback: {exc}")
            result.raw_markdown = markdown
    else:
        sections = split_markdown_sections(markdown)
        result = _extract_with_rules(sections, markdown)
        result.raw_markdown = markdown

    if validate:
        return validate_extraction(result, markdown)
    return result


def _upsert_reference_data(result: ExtractionResult) -> None:
    from db.client import get_supabase_client

    client = get_supabase_client()

    seen_models: dict[str, str] = {
        model.id: model.display_name for model in result.pricing_models
    }
    for term in result.contract_terms:
        if term.pricing_model_id:
            model_id = term.pricing_model_id.value
            seen_models.setdefault(model_id, term.section_title or model_id)
    if seen_models:
        client.table("pricing_models").upsert(
            [{"id": key, "display_name": value} for key, value in seen_models.items()],
            on_conflict="id",
        ).execute()

    seen_networks: dict[str, str] = {
        network.id: network.display_name for network in result.networks
    }
    for term in result.contract_terms:
        if term.network_id:
            seen_networks.setdefault(
                term.network_id,
                term.network_id.replace("_", " ").title(),
            )
    if seen_networks:
        client.table("networks").upsert(
            [{"id": key, "display_name": value} for key, value in seen_networks.items()],
            on_conflict="id",
        ).execute()


def load_to_supabase(result: ExtractionResult, source_filename: str) -> dict[str, int]:
    from db.client import get_supabase_client

    client = get_supabase_client()

    existing = (
        client.table("documents")
        .select("id")
        .eq("source_filename", source_filename)
        .execute()
    )
    if existing.data:
        doc_id = existing.data[0]["id"]
        for table in ["contract_terms", "included_services", "assumptions"]:
            client.table(table).delete().eq("document_id", doc_id).execute()
        client.table("documents").delete().eq("id", doc_id).execute()

    _upsert_reference_data(result)

    doc_payload = {
        "source_filename": source_filename,
        "vendor_name": result.metadata.vendor_name,
        "client_name": result.metadata.client_name,
        "proposal_date": result.metadata.proposal_date.isoformat()
        if result.metadata.proposal_date
        else None,
        "raw_markdown": result.raw_markdown,
    }
    doc_response = client.table("documents").insert(doc_payload).execute()
    document_id = doc_response.data[0]["id"]

    term_payloads = [row.to_db_dict(document_id) for row in result.contract_terms]
    if term_payloads:
        client.table("contract_terms").insert(term_payloads).execute()

    service_payloads = [service.to_db_dict(document_id) for service in result.included_services]
    if service_payloads:
        client.table("included_services").insert(service_payloads).execute()

    assumption_payloads = [
        {
            "document_id": document_id,
            "category": assumption.category,
            "bullet_text": assumption.bullet_text,
        }
        for assumption in result.assumptions
    ]
    if assumption_payloads:
        client.table("assumptions").insert(assumption_payloads).execute()

    return {
        "documents": 1,
        "contract_terms": len(term_payloads),
        "included_services": len(service_payloads),
        "assumptions": len(assumption_payloads),
    }
