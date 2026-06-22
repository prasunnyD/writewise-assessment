"""CLI entry point for contract extraction."""

from __future__ import annotations

from pathlib import Path

import typer

from extract.pipeline import extract_from_pdf, load_to_supabase

app = typer.Typer(help="Extract PBM pricing contract data from PDF into Supabase")


@app.command()
def main(
    pdf: Path = typer.Option(..., "--pdf", help="Path to pricing proposal PDF"),
    no_llm: bool = typer.Option(
        False,
        "--no-llm",
        help="Offline rule-based fallback (less accurate for new vendors)",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Extract and validate without loading DB"),
) -> None:
    if not pdf.exists():
        raise typer.BadParameter(f"PDF not found: {pdf}")

    typer.echo(f"Extracting from {pdf}...")
    if no_llm:
        typer.echo(
            typer.style(
                "Warning: --no-llm uses rule-based fallback; use default LLM extraction for new vendors.",
                fg=typer.colors.YELLOW,
            )
        )
    result = extract_from_pdf(str(pdf), use_llm=not no_llm)

    typer.echo(f"Vendor: {result.metadata.vendor_name}")
    typer.echo(f"Client: {result.metadata.client_name}")
    typer.echo(f"Contract terms: {len(result.contract_terms)}")
    typer.echo(f"Included services: {len(result.included_services)}")
    typer.echo(f"Assumptions: {len(result.assumptions)}")

    if result.warnings:
        typer.echo("\nWarnings:")
        for warning in result.warnings[:20]:
            typer.echo(f"  - {warning}")
        if len(result.warnings) > 20:
            typer.echo(f"  ... and {len(result.warnings) - 20} more")

    if dry_run:
        typer.echo("\nDry run complete — no database writes.")
        raise typer.Exit(0)

    counts = load_to_supabase(result, pdf.name)
    typer.echo("\nLoaded to Supabase:")
    for table, count in counts.items():
        typer.echo(f"  {table}: {count}")


if __name__ == "__main__":
    app()
