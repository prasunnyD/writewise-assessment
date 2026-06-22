"""Apply SQL migrations to the Supabase Postgres database."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


def get_database_url() -> str:
    """Return the Postgres connection URI from environment variables."""
    url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "SUPABASE_DB_URL (or DATABASE_URL) must be set. "
            "Find it in Supabase: Project Settings → Database → Connection string (URI)."
        )
    return url


def _split_sql_statements(sql: str) -> list[str]:
    """Split a SQL file into executable statements, ignoring comment lines."""
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    cleaned = "\n".join(lines)
    return [statement.strip() for statement in cleaned.split(";") if statement.strip()]


def apply_migration_file(conn: psycopg.Connection, path: Path) -> int:
    """Execute all statements in a migration file and return the statement count."""
    statements = _split_sql_statements(path.read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
    return len(statements)


def run_migrations(
    migration_dir: Path | None = None,
    *,
    database_url: str | None = None,
) -> list[tuple[str, int]]:
    """Apply all .sql migration files in sorted order and return applied filenames."""
    directory = migration_dir or MIGRATIONS_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"Migrations directory not found: {directory}")

    files = sorted(directory.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"No .sql migration files found in {directory}")

    url = database_url or get_database_url()
    applied: list[tuple[str, int]] = []

    with psycopg.connect(url, autocommit=True) as conn:
        for path in files:
            count = apply_migration_file(conn, path)
            applied.append((path.name, count))

    return applied
