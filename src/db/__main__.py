"""CLI for database setup and migrations."""

from __future__ import annotations

from pathlib import Path

import typer
import psycopg

from db.migrate import MIGRATIONS_DIR, run_migrations

app = typer.Typer(help="Database setup for WriteWise contract extraction")


@app.command()
def migrate(
    migration_dir: Path | None = typer.Option(
        None,
        "--dir",
        help="Directory containing .sql migration files",
    ),
) -> None:
    """Apply SQL migrations to the Supabase Postgres database."""
    directory = migration_dir or MIGRATIONS_DIR
    typer.echo(f"Applying migrations from {directory}...")

    try:
        applied = run_migrations(directory)
    except RuntimeError as exc:
        raise typer.Exit(typer.style(str(exc), fg=typer.colors.RED)) from exc
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except psycopg.Error as exc:
        raise typer.Exit(typer.style(f"Migration failed: {exc}", fg=typer.colors.RED)) from exc

    for filename, statement_count in applied:
        typer.echo(f"  {filename}: {statement_count} statements")
    typer.echo(typer.style("Migrations applied successfully.", fg=typer.colors.GREEN))


if __name__ == "__main__":
    app()
