"""Orchestrate PDF parsing, extraction, validation, and loading."""

from __future__ import annotations

import os
from pathlib import Path

from models.extraction import DocumentMetadata, ExtractionResult, SectionChunk
from extract.pdf_parser import parse_pdf
from extract.rule_parser import (
    parse_document_metadata,
    parse_pricing_section,
    parse_rebate_guarantees,
)
from extract.text_parser import parse_assumptions, parse_fee_schedule, parse_included_services
from extract.validator import validate_extraction


def _get_section(sections: list[SectionChunk], section_type: str) -> SectionChunk | None:
    return next((s for s in sections if s.section_type == section_type), None)


def extract_from_pdf(pdf_path: str, use_llm: bool = True) -> ExtractionResult:
    pages, sections = parse_pdf(pdf_path)
    full_text = "\n\n".join(page.text for page in pages)
    meta_dict = parse_document_metadata(full_text)
    metadata = DocumentMetadata(**meta_dict)

    contract_terms = []
    included_services = []
    assumptions = []
    warnings: list[str] = []

    traditional = _get_section(sections, "traditional_pricing")
    if traditional:
        from models.enums import PricingModel

        contract_terms.extend(
            parse_pricing_section(
                traditional.raw_text,
                PricingModel.TRADITIONAL,
                traditional.page_start,
            )
        )

    rebate = _get_section(sections, "rebate_guarantees")
    if rebate:
        contract_terms.extend(parse_rebate_guarantees(rebate.raw_text, rebate.page_start))

    applied = _get_section(sections, "applied_rebates_pricing")
    if applied:
        from models.enums import PricingModel

        contract_terms.extend(
            parse_pricing_section(
                applied.raw_text,
                PricingModel.APPLIED_REBATES,
                applied.page_start,
            )
        )

    fees_section = _get_section(sections, "allowances_fees")
    if fees_section:
        if use_llm and os.environ.get("OPENAI_API_KEY"):
            try:
                from extract.llm_extractor import LLMClient, fees_to_contract_terms

                client = LLMClient()
                fee_rows = client.extract_fee_schedule(fees_section.raw_text)
                contract_terms.extend(
                    fees_to_contract_terms(fee_rows, fees_section.page_start)
                )
            except Exception as exc:
                warnings.append(f"LLM fee extraction failed, using rule parser: {exc}")
                fee_terms, _ = parse_fee_schedule(fees_section.raw_text)
                contract_terms.extend(fee_terms)
        else:
            fee_terms, _ = parse_fee_schedule(fees_section.raw_text)
            contract_terms.extend(fee_terms)

    included_section = _get_section(sections, "included_services")
    if included_section:
        if use_llm and os.environ.get("OPENAI_API_KEY"):
            try:
                from extract.llm_extractor import LLMClient

                client = LLMClient()
                included_services = client.extract_included_services(included_section.raw_text)
            except Exception as exc:
                warnings.append(f"LLM included services failed, using rule parser: {exc}")
                included_services = parse_included_services(included_section.raw_text)
        else:
            included_services = parse_included_services(included_section.raw_text)

    assumptions_section = _get_section(sections, "assumptions")
    if assumptions_section:
        if use_llm and os.environ.get("OPENAI_API_KEY"):
            try:
                from extract.llm_extractor import LLMClient

                client = LLMClient()
                assumptions = client.extract_assumptions(assumptions_section.raw_text)
            except Exception as exc:
                warnings.append(f"LLM assumptions failed, using rule parser: {exc}")
                assumptions = parse_assumptions(assumptions_section.raw_text)
        else:
            assumptions = parse_assumptions(assumptions_section.raw_text)

    result = ExtractionResult(
        metadata=metadata,
        contract_terms=contract_terms,
        included_services=included_services,
        assumptions=assumptions,
        warnings=warnings,
    )
    return validate_extraction(result, full_text)


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

    doc_payload = {
        "source_filename": source_filename,
        "vendor_name": result.metadata.vendor_name,
        "client_name": result.metadata.client_name,
        "proposal_date": result.metadata.proposal_date.isoformat()
        if result.metadata.proposal_date
        else None,
        "extraction_metadata": {"warnings": result.warnings},
    }
    doc_response = client.table("documents").insert(doc_payload).execute()
    document_id = doc_response.data[0]["id"]

    term_payloads = [row.to_db_dict(document_id) for row in result.contract_terms]
    if term_payloads:
        client.table("contract_terms").insert(term_payloads).execute()

    service_payloads = [
        {
            "document_id": document_id,
            "category": service.category,
            "service_name": service.service_name,
            "is_included": service.is_included,
            "cost_summary": service.cost_summary,
        }
        for service in result.included_services
    ]
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
