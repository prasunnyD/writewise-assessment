# DECISIONS.md

## Schema design

**Single `contract_terms` fact table** instead of separate tables per fee type (discounts, rebates, admin fees, ancillary charges).

Why:

- The PDF mixes units ($/claim, PMPM, AWP-%, flat annual) in one fee schedule. A unified row shape with `basis_type`, `value_type`, and `value_text` preserves meaning without schema churn.
- A second vendor PDF becomes a new `documents` row with the same tables — no code changes.
- Dimensions disambiguate messy overlaps: `pricing_model_id` (Traditional vs Applied Rebates), `network_id`, `drug_type`, `channel`, `calendar_year`, `payment_schedule`.

Non-numeric values use `value_type` (`included`, `quoted_upon_request`, `pass_through`) plus verbatim `value_text`, not NULL sentinels.

Rebate payment timing is a first-class field (`payment_schedule`, `payment_timing_text`) because two otherwise identical rebate grids differ only by quarterly vs monthly payment.

## Raw document storage

**`documents.raw_markdown`** stores the full PDF as markdown at extraction time via [Markitdown](https://github.com/microsoft/markitdown).

Why markdown:

- Human-readable audit copy alongside structured rows
- Single artifact used as LLM extraction input and DB storage
- No binary PDF blob in Postgres

Dropped `raw_metadata` and `extraction_metadata` — the former was never populated; the latter only held extraction warnings, which remain CLI-only on `ExtractionResult.warnings`.

Re-running extraction for the same `source_filename` replaces the document row and its `raw_markdown`.

## Extraction pipeline

**Markitdown + LLM-first structured extraction**, with a rule-based `--no-llm` fallback.

```text
PDF → Markitdown → markdown
  → (default) OpenAI structured output → ContractTermRow / IncludedServiceRow / AssumptionRow
  → (--no-llm) format-generic section split → rule parsers
  → validator (source-text checks) → Supabase
```

Why Markitdown over pdfplumber or Docling:

- **Markitdown** — lightweight, one-step PDF→markdown, good enough for same-format proposals; easy Poetry install for graders
- **Not pdfplumber** — required vendor-specific section regex and brittle column mapping; markdown was generated but unused for extraction
- **Not Docling** — better table fidelity but heavy models/RAM; overkill for this assessment scope

Why LLM-first:

- Removes vendor-specific hardcoding (no `Northwind` / `Brightline` regex, no fixed `section_title` mappers)
- Reads network names, formulary names, and section headings from the document
- Outputs `ContractTermRow` directly — no intermediate `FeeScheduleRow` → mapper glue
- `networks` and `pricing_models` reference rows are upserted at load time from extracted data

Trustworthiness:

1. **Structured outputs** — Pydantic schema with enums constrains `term_category`, `basis_type`, `value_type`, etc.
2. **Source-text validation** — drops numeric rows whose values don't appear in the markdown corpus
3. **Idempotent loads** — re-run deletes prior rows for the same `source_filename`
4. **Provenance columns** — `section_title`, `page_number`, `source_row_label` for audit

**`--no-llm` fallback** — rule parsers on markdown sections (format-generic headers, generic metadata heuristics). Best-effort offline path; less accurate for new vendors. Graders should use default LLM extraction for the second PDF.

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

- **LLM grid accuracy** — pricing/rebate tables may mis-assign network or year columns; validator catches missing numerics but not all structural errors
- **Markitdown table layout** — dense multi-column grids may flatten; Docling would be the upgrade path
- **Fee schedule line breaks** — Multi-line cells sometimes split into separate rows. Search still finds related fees.
- **Validator** — Lenient on `value_text` substring checks for AWP strings; strict on numeric presence in source
- **`--no-llm` fallback** — still uses format-specific metric headers and column heuristics

## With more time

- Stretch eval Q&A pairs + automated runner
- Docling for improved table fidelity if Markitdown layout is insufficient
- Rebate dollar estimation tool (claims × rebate rate × AWP assumptions)
- Human-in-the-loop review UI for extraction warnings
- pgvector search for assumptions/caveats free-text questions
