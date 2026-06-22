# DECISIONS.md

## Schema design

**`contract_terms`** holds pricing-grid terms only: admin fees, network discounts, dispensing fees, and rebates. Dimensions disambiguate overlaps: `pricing_model_id` (Traditional vs Applied Rebates), `network_id`, `drug_type`, `channel`, `calendar_year`, `payment_schedule`.

**`included_services`** holds document-level services from two PDF sections:

- `(Included Services)` — bullets with `source_section='included_services'`, `is_included=true`
- `Allowances and Ancillary Charges` — priced fee schedule with `source_section='allowances_fees'`, `fee_type` (`allowance` / `ancillary_fee`), and value fields (`value_type`, `value_text`, `basis_type`, etc.)

Fee schedule data is pricing-model agnostic (no `pricing_model_id`, `network_id`, or year columns), so it does not belong in `contract_terms`. Sub-headings such as "Additional Administrative Services" are stored in `category` for filtering and audit.

Why a unified row shape for values:

- The PDF mixes units ($/claim, PMPM, AWP-%, flat annual). `basis_type`, `value_type`, and `value_text` preserve meaning without schema churn.
- A second vendor PDF becomes a new `documents` row with the same tables — no code changes.

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

**Markitdown + LLM-first structured extraction**, with a deterministic rule supplement for the fee schedule and a `--no-llm` fallback.

```text
PDF → Markitdown → markdown
  → (default) OpenAI structured output → ContractTermRow / IncludedServiceRow / AssumptionRow
  → rule parser supplements Allowances and Ancillary Charges → included_services
  → validator (source-text checks) → Supabase
  → (--no-llm) format-generic section split → rule parsers for all sections
```

### Reproducibility (Task 1)

The graded pipeline is a single CLI: `poetry run writewise-extract --pdf <path>`. Vendor names, client names, dollar amounts, and percentages are read from the document at runtime — nothing in `src/` hardcodes Northwind/Brightline figures. A second same-format proposal becomes a new `documents` row; reference tables (`networks`, `pricing_models`) are upserted from extracted data.

### Hybrid extraction: what each layer does

| Section | Extractor | Why |
|---------|-----------|-----|
| Traditional / Applied Rebates grids, rebates, admin fees | LLM structured output | Multi-column year/network grids; vendor network names vary |
| (Included Services) bullets | LLM structured output | Unstructured bullet lists under category headings |
| Allowances and Ancillary Charges | Rule parser (`parse_fee_schedule`) | See below |
| Assumptions and Caveats | LLM structured output | Free-text bullets |

### Why supplement fees with a rule parser

Testing showed the LLM-only path reliably extracted ~20 `(Included Services)` bullets but **zero** rows from Allowances and Ancillary Charges (including the Additional Administrative Services table), even with explicit prompt instructions. That section has ~30+ priced rows with mixed layouts (inline costs, multi-line cells, "Included", "Quoted upon request").

The hybrid fix (`_supplement_services_from_rules` in `pipeline.py`) keeps LLM output for grids and included bullets, then always rule-parses the `Allowances and Ancillary Charges` markdown section into `included_services` with `source_section='allowances_fees'`. This is a reliability fix for a measured failure mode, not a schema workaround.

The rule parser reads **values from the markdown** via `parse_single_value`; it does not embed contract dollar amounts. It does assume **same document format**: section title `Allowances and Ancillary Charges` and known sub-headings (e.g. `Additional Administrative Services`, `Implementation Allowances`). That matches the assignment's "second document in the same format" constraint.

Why Markitdown over pdfplumber or Docling:

- **Markitdown** — lightweight, one-step PDF→markdown, good enough for same-format proposals; easy Poetry install for graders
- **Not pdfplumber** — required vendor-specific section regex and brittle column mapping; markdown was generated but unused for extraction
- **Not Docling** — better table fidelity but heavy models/RAM; overkill for this assessment scope

Why LLM-first for pricing grids:

- Removes vendor-specific hardcoding (no `Northwind` / `Brightline` regex, no fixed `section_title` mappers)
- Reads network names, formulary names, and section headings from the document
- `networks` and `pricing_models` reference rows are upserted at load time from extracted data

Trustworthiness:

1. **Structured outputs** — Pydantic schema with enums constrains `term_category`, `basis_type`, `value_type`, etc.
2. **Source-text validation** — drops numeric rows whose values don't appear in the markdown corpus
3. **Idempotent loads** — re-run deletes prior rows for the same `source_filename`
4. **Provenance columns** — `section_title`, `page_number`, `source_row_label` (grids); `category`, `service_name`, `value_text` (fees)

**`--no-llm` fallback** — rule parsers on all markdown sections (format-generic headers, generic metadata heuristics). Best-effort offline path; less accurate for pricing grids on new vendors. Graders should use default LLM extraction for the second PDF.

## Tool design

**Typed tools, not a generic SQL tool.**

| Tool | Role |
|------|------|
| `list_pricing_models` / `list_networks` | Disambiguation |
| `get_network_discount` | Discounts and dispensing fees |
| `get_rebate_guarantee` | Rebate $ + payment timing |
| `search_fees` | Allowances & ancillary charges keyword search (`included_services` where `source_section='allowances_fees'`) |
| `get_included_services` | Included services + related fees from same table |
| `get_assumptions` | Caveats text |

Typed tools constrain query shapes, prevent bad joins across pricing models, and return structured `needs_clarification` responses when parameters are missing.

## Grounding

1. System prompt forbids inventing numbers; answers must cite tool results.
2. Tools return verbatim `value_text` from the database.
3. Ambiguous questions (e.g. "brand discount" without network/year/model) trigger clarification via `needs_clarification` tool responses — the agent must not silently pick Traditional over Applied Rebates.
4. `not_found` responses are passed through; the agent says data is missing rather than guessing.

## What broke / limitations

- **LLM fee schedule omission** — single-pass LLM extraction missed the entire Allowances and Ancillary Charges section; hybrid rule supplement addresses this
- **LLM grid accuracy** — pricing/rebate tables may mis-assign network or year columns; validator catches missing numerics but not all structural errors
- **Markitdown table layout** — dense multi-column grids may flatten; Docling would be the upgrade path
- **Fee schedule line breaks** — multi-line cells sometimes split into separate rows; search still finds related fees
- **Format coupling** — fee rule parser expects same section/sub-heading names as the sample proposal; renamed sections in a "same format" doc would need parser updates
- **Validator** — lenient on `value_text` substring checks for AWP strings; strict on numeric presence in source
- **`--no-llm` fallback** — uses format-specific metric headers and column heuristics throughout

## With more time

- Stretch eval Q&A pairs + automated runner
- Docling for improved table fidelity if Markitdown layout is insufficient
- Rebate dollar estimation tool (claims × rebate rate × AWP assumptions)
- Human-in-the-loop review UI for extraction warnings
- pgvector search for assumptions/caveats free-text questions
