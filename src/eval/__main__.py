"""CLI for extraction evaluation reports."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from eval.runner import evaluate_extraction, format_report

app = typer.Typer(help="Evaluate extraction quality with validation metrics and golden checks")


@app.command()
def run(
    pdf: Path = typer.Option(..., "--pdf", help="Path to pricing proposal PDF"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Use rule-based extraction only"),
    golden: Path | None = typer.Option(
        None,
        "--golden",
        help="Path to golden spot-check JSON (defaults to tests/fixtures/northwind_expected.json)",
    ),
    as_json: bool = typer.Option(False, "--json", help="Output report as JSON"),
    skip_numeric_verify: bool = typer.Option(
        False,
        "--skip-numeric-verify",
        help="Skip post-validation numeric-in-source checks",
    ),
) -> None:
    report = evaluate_extraction(
        str(pdf),
        use_llm=not no_llm,
        golden_path=golden,
        verify_numerics=not skip_numeric_verify,
    )

    if as_json:
        payload = {
            "passed": report.passed,
            "metrics": {
                "terms_in": report.metrics.terms_in,
                "terms_out": report.metrics.terms_out,
                "terms_dropped": report.metrics.terms_dropped,
                "terms_drop_rate": report.metrics.terms_drop_rate,
                "services_in": report.metrics.services_in,
                "services_out": report.metrics.services_out,
                "services_dropped": report.metrics.services_dropped,
                "services_drop_rate": report.metrics.services_drop_rate,
                "assumptions_in": report.metrics.assumptions_in,
                "critical_warnings": report.metrics.critical_warnings,
                "warnings_added": report.metrics.warnings_added,
            },
            "golden": {
                "passed": report.golden.total_passed,
                "total": report.golden.total_checks,
                "failures": [
                    {"spec": failure.spec, "reason": failure.reason}
                    for failure in report.golden.failures
                ],
            },
            "metadata": report.validated.metadata.model_dump(mode="json"),
            "row_counts": {
                "contract_terms": len(report.validated.contract_terms),
                "included_services": len(report.validated.included_services),
                "assumptions": len(report.validated.assumptions),
            },
        }
        typer.echo(json.dumps(payload, indent=2, default=str))
        raise typer.Exit(code=0 if report.passed else 1)

    typer.echo(format_report(report))
    raise typer.Exit(code=0 if report.passed else 1)


if __name__ == "__main__":
    app()
