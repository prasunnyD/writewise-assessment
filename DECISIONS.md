# DECISIONS.md

## Schema design

**Single `contract_terms` fact table** instead of separate tables per fee type (discounts, rebates, admin fees, ancillary charges).

Why:

- The PDF mixes units ($/claim, PMPM, AWP-%, flat annual) in one fee schedule. A unified row shape with `basis_type`, `value_type`, and `value_text` preserves meaning without schema churn.
- A second vendor PDF becomes a new `documents` row with the same tables — no code changes.
- Dimensions disambiguate messy overlaps: `pricing_model_id` (Traditional vs Applied Rebates), `network_id`, `drug_type`, `channel`, `calendar_year`, `payment_schedule`.

Non-numeric values use `value_type` (`included`, `quoted_upon_request`, `pass_through`) plus verbatim `value_text`, not NULL sentinels.

Rebate payment timing is a first-class field (`payment_schedule`, `payment_timing_text`) because two otherwise identical rebate grids differ only by quarterly vs monthly payment.

## Extraction pipeline

**Hybrid: rule-based for structured tables, LLM optional for text-heavy sections.**

| Section | Approach |
|---------|----------|
| Traditional / Applied Rebates pricing | Rule parser + deterministic year splitter |
| Rebate guarantees | Rule parser on dollar grids |
| Included services, fees, assumptions | LLM structured outputs when `OPENAI_API_KEY` set; rule fallback |

Trustworthiness:

1. **Deterministic normalizer** splits stacked cells (`2025: AWP-21.50% / 2026: ...`) into one row per year — not left to the LLM alone.
2. **Source-text validation** drops numeric rows whose values don't appear in the extracted PDF text.
3. **Idempotent loads** — re-run deletes prior rows for the same `source_filename`.
4. **Provenance columns** — `section_title`, `page_number`, `source_row_label` for audit.

pdfplumber layout differs from visual PDF order (metric names inline with years). The rule parser uses regex to extract `(year, value)` pairs and maps alternating columns to `broad_national` / `retail_90`, mirroring `retail_30` to broad national when only two distinct columns appear.

## Tool design

**Typed tools, not a generic SQL tool.**

| Tool | Role |
|------|------|
| `list_pricing_models` / `list_networks` | Disambiguation |
| `get_network_discount` | Discounts and dispensing fees |
| `get_rebate_guarantee` | Rebate $ + payment timing |
| `search_fees` | Fee schedule keyword search |
| `get_included_services` | Included services + related fees |
| `get_assumptions` | Caveats text |

Typed tools constrain query shapes, prevent bad joins across pricing models, and return structured `needs_clarification` responses when parameters are missing.

## Grounding

1. System prompt forbids inventing numbers; answers must cite tool results.
2. Tools return verbatim `value_text` from the database.
3. Ambiguous questions (e.g. "brand discount" without network/year/model) trigger clarification via `needs_clarification` tool responses — the agent must not silently pick Traditional over Applied Rebates.
4. `not_found` responses are passed through; the agent says data is missing rather than guessing.

## What broke / limitations

- **pdfplumber column order** — Network guarantee columns are merged on one line; we infer column mapping from pair order. A third distinct Retail 30 column could be mis-assigned if a vendor PDF has three unique value columns.
- **Fee schedule line breaks** — Multi-line cells (e.g. Claims portal "4 users: Included") sometimes split into separate rows. Search still finds related fees.
- **Section page boundaries** — Segmentation uses header regex on full text; page numbers are approximate.
- **Validator** — Lenient on `value_text` substring checks for AWP strings; strict on numeric presence in source.

## With more time

- Stretch eval Q&A pairs + automated runner
- Rebate dollar estimation tool (claims × rebate rate × AWP assumptions)
- Table-aware PDF extraction (camelot/tabula) for column alignment
- Human-in-the-loop review UI for extraction warnings
- pgvector search for assumptions/caveats free-text questions
