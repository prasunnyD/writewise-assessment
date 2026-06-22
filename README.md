# WriteWise Contract Extraction & Q&A Agent

Extract pharmacy benefit pricing from PBM proposal PDFs into Supabase, then answer questions via a grounded CLI agent.

## Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation) (dependency management)
- [Supabase](https://supabase.com) project (free tier)
- OpenAI API key

## Setup

### 1. Environment

```bash
cp .env.example .env
```

Create a [Supabase](https://supabase.com) project, then set:

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (Settings → API) |
| `SUPABASE_DB_URL` | Postgres connection URI (Settings → Database → Connection string) |
| `OPENAI_API_KEY` | OpenAI API key (**required** for default extraction and Q&A) |
| `OPENAI_MODEL` | Optional, defaults to `gpt-4o` |

For `SUPABASE_DB_URL`, use the **URI** connection string from the Supabase dashboard. The transaction pooler (`:6543`) or direct connection (`:5432`) both work.

### 2. Install

This project uses [Poetry](https://python-poetry.org/) for dependencies and virtualenv management:

```bash
poetry install
```

Run commands with `poetry run ...`, or activate the shell first:

```bash
poetry shell
```

### 3. Database

Apply the schema programmatically (no manual SQL editor paste required):

```bash
poetry run python -m db
```

This runs all `supabase/migrations/*.sql` files in order against your database via `SUPABASE_DB_URL`. Migrations are idempotent (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`), so re-running is safe.

## CLI commands

Poetry registers four console scripts. These are equivalent to the `python -m` forms below.

| Command | Purpose |
|---------|---------|
| `poetry run writewise-db` | Apply database migrations |
| `poetry run writewise-extract --pdf <path>` | Extract a PDF into Supabase |
| `poetry run writewise-agent` | Start the interactive Q&A agent |
| `poetry run writewise-eval --pdf <path> [--no-llm]` | Evaluate extraction quality (metrics + golden checks) |

## Task 1 — Extract PDF to Supabase

```bash
poetry run writewise-extract --pdf assets/Northwind_Pricing_Proposal_SAMPLE.pdf
```

Options:

- `--dry-run` — extract and validate without writing to Supabase
- `--no-llm` — offline rule-based fallback (less accurate for new vendors; default uses OpenAI + Markitdown)

The pipeline is reproducible: pass any same-format vendor PDF as `--pdf`. Vendor names and numbers are read from the document, not hardcoded.

Example output (LLM path):

```
Contract terms: ~120 rows
Included services: ~50 rows (included bullets + allowances/fees)
Assumptions: ~24 rows
```

**Schema overview**

- `contract_terms` — pricing-grid terms only (discounts, rebates, admin fees, dispensing fees)
- `included_services` — document-level services from two PDF sections:
  - `(Included Services)` bullets (`source_section='included_services'`)
  - `Allowances and Ancillary Charges` fee rows (`source_section='allowances_fees'`, with `fee_type`, `value_type`, `value_text`, etc.)
- `documents` — cover-page metadata plus `raw_markdown` (full PDF as markdown)
- `networks` / `pricing_models` — reference tables upserted from extracted data at load time

Re-running against the same filename replaces prior rows for that document.

The full PDF is converted to markdown via [Markitdown](https://github.com/microsoft/markitdown) and stored in `documents.raw_markdown`. The same markdown is fed to the LLM for structured extraction, then rule-supplemented for the fee schedule (see `DECISIONS.md`).

## Task 2 — Q&A Agent

```bash
poetry run writewise-agent
```

On startup the agent lists extracted contracts and prompts you to pick one (by number or filename substring). All document-scoped tools receive that `document_id` automatically for the session.

Interactive CLI. Example questions:

- What's the generic discount for Retail 90 in 2026?
- How much is a clinical prior authorization with physician review?
- What's the specialty rebate per brand drug in 2027, and when is it paid?
- What's included vs. extra-cost in eligibility maintenance?

The agent uses typed database tools only — it does not read the PDF. If multiple contracts are loaded, it queries only the selected document unless you switch via `list_documents`.

## Project structure

```
supabase/migrations/   SQL schema (001–004, applied via `db migrate`)
src/db/                Supabase client and migration CLI
src/extract/           PDF extraction pipeline (LLM + rule parsers + validator)
src/agent/             Q&A CLI agent (OpenAI tool-calling loop)
src/eval/              Extraction evaluation (metrics, golden checks, CLI)
src/models/            Pydantic schemas and enums
tests/
  unit/                Fast offline tests (parsers, validator, pipeline mocks)
  eval/                Golden-check and metrics unit tests
  integration/         Live PDF extraction via Markitdown (--no-llm)
  fixtures/            Golden expectations and markdown snippets
assets/                Sample PDF
DECISIONS.md           Design rationale (tradeoffs, cost, ROI, architecture)
WriteWise_Decisions.docx  Word summary for stakeholders
```

All classes and functions under `src/` and `tests/` are documented with module-level and inline docstrings.

## Sample document

`assets/Northwind_Pricing_Proposal_SAMPLE.pdf` — synthetic 10-page Northwind PBM pricing proposal (fictional figures).

See `DECISIONS.md` for schema design, tool choices, grounding approach, evaluation strategy, tradeoffs, cost, ROI, and a simple architecture diagram. A stakeholder-friendly Word summary is in `WriteWise_Decisions.docx`.

## Testing

```bash
poetry run pytest                        # all tests (unit + integration)
poetry run pytest -m "not integration"   # unit tests only (fast, no PDF conversion)
```

| Suite | What it covers |
|-------|----------------|
| `tests/unit/` | Normalizer, rule/text parsers, markdown sections, validator, pipeline (mocked) |
| `tests/eval/` | Golden spot checks, validation metrics |
| `tests/integration/` | Full `evaluate_extraction` on the sample PDF via `--no-llm` |

Integration tests run Markitdown on `assets/Northwind_Pricing_Proposal_SAMPLE.pdf` through the offline extraction path.

### Evaluation

Run a validation metrics report with golden spot checks:

```bash
poetry run writewise-eval --pdf assets/Northwind_Pricing_Proposal_SAMPLE.pdf --no-llm
poetry run writewise-eval --pdf assets/Northwind_Pricing_Proposal_SAMPLE.pdf --no-llm --json
```

Options:

- `--golden <path>` — custom golden JSON (default: `tests/fixtures/northwind_expected.json`)
- `--json` — machine-readable report with exit code 0/1
- `--skip-numeric-verify` — skip post-validation numeric-in-source checks

Golden expectations cover metadata, key discount/fee spot values, row-count thresholds, and (by default) verification that every numeric row appears in `raw_markdown`.
