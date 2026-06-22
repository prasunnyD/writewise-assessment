"""OpenAI structured extraction for text-heavy sections."""

from __future__ import annotations

import json
import os
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel, Field

from models.enums import BasisType, ValueType
from models.extraction import AssumptionRow, FeeScheduleRow, IncludedServiceRow

T = TypeVar("T", bound=BaseModel)


class LLMIncludedServices(BaseModel):
    services: list[IncludedServiceRow]


class LLMFeeSchedule(BaseModel):
    fees: list[FeeScheduleRow]


class LLMAssumptions(BaseModel):
    assumptions: list[AssumptionRow]


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

    def extract_included_services(self, section_text: str) -> list[IncludedServiceRow]:
        system = (
            "Extract included PBM services from the contract section. "
            "Preserve category headings. Mark is_included=true for standard included services. "
            "Put any extra-cost details in cost_summary. Do not invent services."
        )
        result = self._extract(system, section_text, LLMIncludedServices)
        return result.services

    def extract_fee_schedule(self, section_text: str) -> list[FeeScheduleRow]:
        system = (
            "Extract ancillary charges and fee schedule rows. "
            "Use value_type=included for Included rows, quoted_upon_request when stated, "
            "pass_through for pass-through costs. Parse numeric amounts when present. "
            "basis_type examples: pmpm, per_record, per_audit, per_hour, flat_annual, dollar_per_claim. "
            "Do not invent fees."
        )
        result = self._extract(system, section_text, LLMFeeSchedule)
        return result.fees

    def extract_assumptions(self, section_text: str) -> list[AssumptionRow]:
        system = (
            "Extract assumption and caveat bullet points grouped by category headings. "
            "Copy bullet text faithfully. Do not invent assumptions."
        )
        result = self._extract(system, section_text, LLMAssumptions)
        return result.assumptions


def fees_to_contract_terms(
    fees: list[FeeScheduleRow],
    page_number: int | None,
) -> list:
    from models.enums import TermCategory
    from models.extraction import ContractTermRow

    rows: list[ContractTermRow] = []
    for fee in fees:
        rows.append(
            ContractTermRow(
                term_category=TermCategory.ANCILLARY_FEE
                if fee.category != "allowance"
                else TermCategory.ALLOWANCE,
                value_type=fee.value_type,
                value_text=fee.cost_text,
                value_numeric=fee.value_numeric,
                basis_type=fee.basis_type,
                unit_label=fee.unit_label,
                section_title="Allowances and Ancillary Charges",
                page_number=page_number,
                source_row_label=fee.service_name,
            )
        )
    return rows


def dump_for_debug(obj: BaseModel) -> str:
    return json.dumps(obj.model_dump(), indent=2, default=str)
