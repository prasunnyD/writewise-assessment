from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from models.enums import (
    BasisType,
    DrugType,
    PaymentSchedule,
    PricingModel,
    RebateChannel,
    TermCategory,
    ValueType,
)


class SectionChunk(BaseModel):
    section_type: str
    title: str
    page_start: int
    page_end: int
    raw_text: str
    tables: list[list[list[str | None]]] = Field(default_factory=list)


class DocumentMetadata(BaseModel):
    vendor_name: str | None = None
    client_name: str | None = None
    proposal_date: date | None = None


class YearValue(BaseModel):
    calendar_year: int
    value_text: str
    value_numeric: float | None = None
    basis_type: BasisType | None = None
    value_type: ValueType = ValueType.NUMERIC
    unit_label: str | None = None


class MetricRow(BaseModel):
    metric_name: str
    drug_type: DrugType | None = None
    values: list[YearValue]


class NetworkPricingBlock(BaseModel):
    network_id: str
    metrics: list[MetricRow]


class AdminFeeRow(BaseModel):
    calendar_year: int
    value_text: str
    value_numeric: float | None = None
    basis_type: BasisType | None = None
    unit_label: str | None = None


class RebateTableBlock(BaseModel):
    payment_schedule: PaymentSchedule
    payment_timing_text: str
    formulary_name: str | None = None
    rows: list[RebateRow]


class RebateRow(BaseModel):
    calendar_year: int
    channel: RebateChannel
    value_text: str
    value_numeric: float


class IncludedServiceRow(BaseModel):
    category: str
    service_name: str
    is_included: bool = True
    cost_summary: str | None = None


class FeeScheduleRow(BaseModel):
    service_name: str
    cost_text: str
    value_type: ValueType = ValueType.NUMERIC
    value_numeric: float | None = None
    basis_type: BasisType | None = None
    unit_label: str | None = None
    category: str | None = None


class AssumptionRow(BaseModel):
    category: str
    bullet_text: str


class ContractTermRow(BaseModel):
    pricing_model_id: PricingModel | None = None
    network_id: str | None = None
    term_category: TermCategory
    drug_type: DrugType | None = None
    channel: RebateChannel | None = None
    calendar_year: int | None = None
    payment_schedule: PaymentSchedule | None = None
    payment_timing_text: str | None = None
    formulary_name: str | None = None
    value_type: ValueType
    value_text: str
    value_numeric: float | None = None
    basis_type: BasisType | None = None
    unit_label: str | None = None
    section_title: str | None = None
    page_number: int | None = None
    source_row_label: str | None = None

    def to_db_dict(self, document_id: str) -> dict[str, Any]:
        return {
            "document_id": document_id,
            "pricing_model_id": self.pricing_model_id.value if self.pricing_model_id else None,
            "network_id": self.network_id,
            "term_category": self.term_category.value,
            "drug_type": self.drug_type.value if self.drug_type else None,
            "channel": self.channel.value if self.channel else None,
            "calendar_year": self.calendar_year,
            "payment_schedule": self.payment_schedule.value if self.payment_schedule else None,
            "payment_timing_text": self.payment_timing_text,
            "formulary_name": self.formulary_name,
            "value_type": self.value_type.value,
            "value_text": self.value_text,
            "value_numeric": self.value_numeric,
            "basis_type": self.basis_type.value if self.basis_type else None,
            "unit_label": self.unit_label,
            "section_title": self.section_title,
            "page_number": self.page_number,
            "source_row_label": self.source_row_label,
        }


class ExtractionResult(BaseModel):
    metadata: DocumentMetadata
    contract_terms: list[ContractTermRow] = Field(default_factory=list)
    included_services: list[IncludedServiceRow] = Field(default_factory=list)
    assumptions: list[AssumptionRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
