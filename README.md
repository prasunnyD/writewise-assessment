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
| `OPENAI_API_KEY` | OpenAI API key |
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
poetry run python -m db migrate
```

This runs all `supabase/migrations/*.sql` files in order against your database via `SUPABASE_DB_URL`. Migrations are idempotent (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`), so re-running is safe.

## CLI commands

Poetry registers three console scripts. These are equivalent to the `python -m` forms below.

| Command | Purpose |
|---------|---------|
| `poetry run writewise-db migrate` | Apply database migrations |
| `poetry run writewise-extract --pdf <path>` | Extract a PDF into Supabase |
| `poetry run writewise-agent` | Start the interactive Q&A agent |

## Task 1 — Extract PDF to Supabase

```bash
poetry run python -m extract --pdf assets/Northwind_Pricing_Proposal_SAMPLE.pdf
```

Options:

- `--dry-run` — extract and validate without writing to Supabase
- `--no-llm` — use rule-based parsers only (works offline for text sections)

The pipeline is reproducible: pass any same-format vendor PDF as `--pdf`. No vendor numbers are hardcoded.

Example output:

```
Contract terms: ~150 rows
Included services: ~20 rows
Assumptions: ~23 rows
```

Re-running against the same filename replaces prior rows for that document.

## Task 2 — Q&A Agent

```bash
poetry run python -m agent
```

Interactive CLI. Example questions:

- What's the generic discount for Retail 90 in 2026?
- How much is a clinical prior authorization with physician review?
- What's the specialty rebate per brand drug in 2027, and when is it paid?
- What's included vs. extra-cost in eligibility maintenance?

The agent uses typed database tools only — it does not read the PDF.

## Project structure

```
supabase/migrations/   SQL schema (applied via `db migrate`)
src/db/                Supabase client and migration CLI
src/extract/           PDF extraction pipeline
src/agent/             Q&A CLI agent
src/models/            Pydantic schemas
assets/                Sample PDF
DECISIONS.md           Design rationale
```

## Sample document

`assets/Northwind_Pricing_Proposal_SAMPLE.pdf` — synthetic 10-page Northwind PBM pricing proposal (fictional figures).

See `DECISIONS.md` for schema design, tool choices, grounding approach, and known limitations.
