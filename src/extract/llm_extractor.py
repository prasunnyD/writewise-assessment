"""OpenAI structured extraction from contract markdown."""

from __future__ import annotations

import json
import os
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel, Field

from models.extraction import (
    AssumptionRow,
    ContractTermRow,
    DocumentMetadata,
    IncludedServiceRow,
    NetworkRef,
    PricingModelRef,
)

T = TypeVar("T", bound=BaseModel)

EXTRACTION_SYSTEM_PROMPT = """You extract structured pharmacy benefit contract data from a PBM pricing proposal markdown document.

Rules:
- Read vendor_name, client_name, and proposal_date from the cover page. Do not invent names.
- Extract contract_terms as rows ready for the database schema. One row per year/network/metric/channel combination in pricing grids.
- Use pricing_model_id values: "traditional" or "applied_rebates" based on section headings in the document.
- Use network_id as a lowercase slug from network column/section headers (e.g. broad_national, retail_30, retail_90, mail, retail_specialty, exclusive_specialty). Include discovered networks in the networks list with matching id and display_name.
- Use term_category values: admin_fee, network_discount, dispensing_fee, rebate, allowance, ancillary_fee.
- Use drug_type when applicable: brand, generic, ldd, new_to_market.
- Use channel for rebate rows: retail_30, retail_90, mail, specialty. Do not put channel values in network_id.
- Use payment_schedule for rebates: quarterly_150d or monthly_60d based on payment timing text in the document.
- Copy value_text, payment_timing_text, unit_label, and formulary_name verbatim from the document when present.
- Parse value_numeric and basis_type when amounts are numeric (awp_minus_percent, dollar_per_claim, pmpm, per_brand_drug, etc.).
- Use value_type: numeric, included, quoted_upon_request, pass_through, or text as appropriate.
- Set section_title from the document section heading each row belongs to.
- Set source_row_label to the metric or service name from the document.
- Populate included_services and assumptions from their respective sections.
- List pricing_models found in the document (at minimum traditional and applied_rebates if both sections exist).
- Do not invent rows, numbers, or services not present in the markdown."""


class LLMExtractionResult(BaseModel):
    metadata: DocumentMetadata
    contract_terms: list[ContractTermRow] = Field(default_factory=list)
    included_services: list[IncludedServiceRow] = Field(default_factory=list)
    assumptions: list[AssumptionRow] = Field(default_factory=list)
    networks: list[NetworkRef] = Field(default_factory=list)
    pricing_models: list[PricingModelRef] = Field(default_factory=list)


class LLMClient:
    def __init__(self) -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for LLM extraction")
        self.client = OpenAI(api_key=api_key)
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    def _extract(self, system_prompt: str, user_content: str, schema: type[T]) -> T:
        response = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format=schema,
            temperature=0,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError(f"LLM returned no parsed output for {schema.__name__}")
        return parsed

    def extract_from_markdown(self, markdown: str) -> LLMExtractionResult:
        user_content = (
            "Extract all contract data from this pricing proposal markdown:\n\n"
            f"{markdown}"
        )
        return self._extract(EXTRACTION_SYSTEM_PROMPT, user_content, LLMExtractionResult)


def dump_for_debug(obj: BaseModel) -> str:
    return json.dumps(obj.model_dump(), indent=2, default=str)
