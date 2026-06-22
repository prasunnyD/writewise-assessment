"""Run extraction evaluation with validation metrics and golden checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from models.extraction import ExtractionResult
from extract.pipeline import extract_from_pdf
from extract.validator import validate_extraction
from eval.golden import GoldenCheckResult, default_golden_path, load_golden, run_golden_checks
from eval.metrics import ValidationMetrics, build_validation_metrics


@dataclass
class EvaluationReport:
    raw: ExtractionResult
    validated: ExtractionResult
    metrics: ValidationMetrics
    golden: GoldenCheckResult

    @property
    def passed(self) -> bool:
        return self.golden.all_passed and not self.metrics.critical_warnings


def evaluate_extraction(
    pdf_path: str,
    use_llm: bool = True,
    *,
    golden_path: str | Path | None = None,
    verify_numerics: bool = True,
) -> EvaluationReport:
    raw = extract_from_pdf(pdf_path, use_llm=use_llm, validate=False)
    validated = validate_extraction(raw, raw.raw_markdown)
    metrics = build_validation_metrics(raw, validated)

    path = Path(golden_path) if golden_path else default_golden_path()
    golden_spec = load_golden(path) if path.exists() else {}
    golden = run_golden_checks(
        validated,
        golden_spec,
        metrics,
        verify_numerics=verify_numerics,
    )

    return EvaluationReport(raw=raw, validated=validated, metrics=metrics, golden=golden)


def format_report(report: EvaluationReport) -> str:
    metrics = report.metrics
    golden = report.golden
    lines = [
        (
            f"Validation metrics: {metrics.terms_in} terms in → {metrics.terms_out} out "
            f"({metrics.terms_drop_rate:.1%} dropped), "
            f"{metrics.services_in} services in → {metrics.services_out} out "
            f"({metrics.services_drop_rate:.1%} dropped)"
        ),
        f"Assumptions: {len(report.validated.assumptions)}",
        f"Golden checks: {golden.total_passed}/{golden.total_checks} passed",
    ]

    if metrics.critical_warnings:
        lines.append(f"Critical warnings: {len(metrics.critical_warnings)}")
        lines.extend(f"  - {warning}" for warning in metrics.critical_warnings)

    if metrics.warnings_added:
        lines.append(f"Validator warnings added: {len(metrics.warnings_added)}")

    if golden.failures:
        lines.append("Failures:")
        for failure in golden.failures:
            lines.append(f"  - [{failure.spec}] {failure.reason}")

    status = "PASS" if report.passed else "FAIL"
    lines.append(f"Overall: {status}")
    return "\n".join(lines)
