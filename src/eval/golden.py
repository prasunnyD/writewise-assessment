"""Golden-file spot checks for extraction evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from models.extraction import ExtractionResult
from eval.metrics import ValidationMetrics


@dataclass
class GoldenCheckFailure:
    """A single failed golden spot check or threshold."""

    spec: str
    reason: str


@dataclass
class GoldenCheckResult:
    """Aggregated pass/fail counts from golden evaluation checks."""

    spot_checks_passed: int = 0
    spot_checks_failed: int = 0
    threshold_checks_passed: int = 0
    threshold_checks_failed: int = 0
    failures: list[GoldenCheckFailure] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """Return True when no golden check failures were recorded."""
        return not self.failures

    @property
    def total_passed(self) -> int:
        """Return the total number of passed spot and threshold checks."""
        return self.spot_checks_passed + self.threshold_checks_passed

    @property
    def total_checks(self) -> int:
        """Return the total number of golden checks run."""
        return (
            self.spot_checks_passed
            + self.spot_checks_failed
            + self.threshold_checks_passed
            + self.threshold_checks_failed
        )


def load_golden(path: str | Path) -> dict[str, Any]:
    """Load a golden spot-check specification from a JSON file."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _matches_term_spec(term, spec: dict[str, Any]) -> bool:
    """Return True when a contract term matches all fields in a golden spec."""
    if "pricing_model_id" in spec:
        if not term.pricing_model_id or term.pricing_model_id.value != spec["pricing_model_id"]:
            return False
    if "network_id" in spec:
        if term.network_id != spec["network_id"]:
            return False
    if "calendar_year" in spec:
        if term.calendar_year != spec["calendar_year"]:
            return False
    if "term_category" in spec:
        if term.term_category.value != spec["term_category"]:
            return False
    label = term.source_row_label or ""
    if "source_row_label_contains" in spec:
        if spec["source_row_label_contains"].lower() not in label.lower():
            return False
    return True


def _matches_service_spec(service, spec: dict[str, Any]) -> bool:
    """Return True when an included service matches all fields in a golden spec."""
    if "source_section" in spec:
        if service.source_section.value != spec["source_section"]:
            return False
    name = service.service_name or ""
    if "service_name_contains" in spec:
        if spec["service_name_contains"].lower() not in name.lower():
            return False
    return True


def _check_term_fields(term, spec: dict[str, Any]) -> str | None:
    """Return an error message when term field values do not match the spec."""
    if "value_numeric" in spec:
        expected = spec["value_numeric"]
        if term.value_numeric is None or term.value_numeric != expected:
            return f"expected value_numeric={expected}, got {term.value_numeric}"
    return None


def _check_service_fields(service, spec: dict[str, Any]) -> str | None:
    """Return an error message when service field values do not match the spec."""
    if "value_numeric" in spec:
        expected = spec["value_numeric"]
        if service.value_numeric is None or service.value_numeric != expected:
            return f"expected value_numeric={expected}, got {service.value_numeric}"
    if "is_included" in spec and service.is_included != spec["is_included"]:
        return f"expected is_included={spec['is_included']}, got {service.is_included}"
    return None


def _run_metadata_checks(result: ExtractionResult, spec: dict[str, Any]) -> GoldenCheckResult:
    """Run golden metadata spot checks against an extraction result."""
    outcome = GoldenCheckResult()
    if not spec:
        return outcome

    if "vendor_name_contains" in spec:
        vendor = result.metadata.vendor_name or ""
        if spec["vendor_name_contains"].lower() not in vendor.lower():
            outcome.failures.append(
                GoldenCheckFailure(
                    spec="metadata.vendor_name_contains",
                    reason=f"expected substring '{spec['vendor_name_contains']}' in '{vendor}'",
                )
            )
            outcome.spot_checks_failed += 1
        else:
            outcome.spot_checks_passed += 1

    if spec.get("client_name_not_null"):
        if not result.metadata.client_name:
            outcome.failures.append(
                GoldenCheckFailure(
                    spec="metadata.client_name_not_null",
                    reason="client_name is null",
                )
            )
            outcome.spot_checks_failed += 1
        else:
            outcome.spot_checks_passed += 1

    return outcome


def _run_contract_term_checks(result: ExtractionResult, specs: list[dict[str, Any]]) -> GoldenCheckResult:
    """Run golden spot checks against contract term rows."""
    outcome = GoldenCheckResult()
    for index, spec in enumerate(specs):
        spec_label = f"contract_terms[{index}]"
        matches = [term for term in result.contract_terms if _matches_term_spec(term, spec)]
        if not matches:
            outcome.failures.append(
                GoldenCheckFailure(
                    spec=spec_label,
                    reason=f"no matching row for spec {spec}",
                )
            )
            outcome.spot_checks_failed += 1
            continue

        field_error = _check_term_fields(matches[0], spec)
        if field_error:
            outcome.failures.append(GoldenCheckFailure(spec=spec_label, reason=field_error))
            outcome.spot_checks_failed += 1
        else:
            outcome.spot_checks_passed += 1

    return outcome


def _run_service_checks(result: ExtractionResult, specs: list[dict[str, Any]]) -> GoldenCheckResult:
    """Run golden spot checks against included service rows."""
    outcome = GoldenCheckResult()
    for index, spec in enumerate(specs):
        spec_label = f"included_services[{index}]"
        matches = [
            service for service in result.included_services if _matches_service_spec(service, spec)
        ]
        if not matches:
            outcome.failures.append(
                GoldenCheckFailure(
                    spec=spec_label,
                    reason=f"no matching row for spec {spec}",
                )
            )
            outcome.spot_checks_failed += 1
            continue

        field_error = _check_service_fields(matches[0], spec)
        if field_error:
            outcome.failures.append(GoldenCheckFailure(spec=spec_label, reason=field_error))
            outcome.spot_checks_failed += 1
        else:
            outcome.spot_checks_passed += 1

    return outcome


def _merge_outcomes(base: GoldenCheckResult, addition: GoldenCheckResult) -> GoldenCheckResult:
    """Merge pass/fail counts and failures from one outcome into another."""
    base.spot_checks_passed += addition.spot_checks_passed
    base.spot_checks_failed += addition.spot_checks_failed
    base.threshold_checks_passed += addition.threshold_checks_passed
    base.threshold_checks_failed += addition.threshold_checks_failed
    base.failures.extend(addition.failures)
    return base


def run_threshold_checks(
    metrics: ValidationMetrics,
    validated: ExtractionResult,
    golden: dict[str, Any],
) -> GoldenCheckResult:
    """Verify extraction row counts and drop rates against golden thresholds."""
    outcome = GoldenCheckResult()
    thresholds = golden.get("thresholds", {})

    checks: list[tuple[str, bool, str]] = []

    if "min_terms_out" in thresholds:
        minimum = thresholds["min_terms_out"]
        checks.append(
            (
                "thresholds.min_terms_out",
                metrics.terms_out >= minimum,
                f"expected >= {minimum}, got {metrics.terms_out}",
            )
        )

    if "min_services_out" in thresholds:
        minimum = thresholds["min_services_out"]
        checks.append(
            (
                "thresholds.min_services_out",
                metrics.services_out >= minimum,
                f"expected >= {minimum}, got {metrics.services_out}",
            )
        )

    if "min_assumptions_out" in thresholds:
        minimum = thresholds["min_assumptions_out"]
        actual = len(validated.assumptions)
        checks.append(
            (
                "thresholds.min_assumptions_out",
                actual >= minimum,
                f"expected >= {minimum}, got {actual}",
            )
        )

    if "max_terms_drop_rate" in thresholds:
        maximum = thresholds["max_terms_drop_rate"]
        checks.append(
            (
                "thresholds.max_terms_drop_rate",
                metrics.terms_drop_rate <= maximum,
                f"expected <= {maximum}, got {metrics.terms_drop_rate:.4f}",
            )
        )

    if "max_services_drop_rate" in thresholds:
        maximum = thresholds["max_services_drop_rate"]
        checks.append(
            (
                "thresholds.max_services_drop_rate",
                metrics.services_drop_rate <= maximum,
                f"expected <= {maximum}, got {metrics.services_drop_rate:.4f}",
            )
        )

    for spec, passed, reason in checks:
        if passed:
            outcome.threshold_checks_passed += 1
        else:
            outcome.threshold_checks_failed += 1
            outcome.failures.append(GoldenCheckFailure(spec=spec, reason=reason))

    return outcome


def verify_numerics_in_source(result: ExtractionResult) -> GoldenCheckResult:
    """Ensure all numeric contract terms and fee rows appear in raw markdown."""
    outcome = GoldenCheckResult()
    source = result.raw_markdown.replace(",", "")

    for term in result.contract_terms:
        if term.value_numeric is None:
            continue
        num_str = f"{term.value_numeric:g}"
        spec = f"numeric_in_source:term:{term.source_row_label}:{num_str}"
        if num_str in source:
            outcome.spot_checks_passed += 1
        else:
            alt = f"{term.value_numeric:.2f}"
            if alt in source:
                outcome.spot_checks_passed += 1
            else:
                outcome.spot_checks_failed += 1
                outcome.failures.append(
                    GoldenCheckFailure(
                        spec=spec,
                        reason=f"numeric {term.value_numeric} not found in source markdown",
                    )
                )

    for service in result.included_services:
        if service.source_section.value != "allowances_fees" or service.value_numeric is None:
            continue
        num_str = f"{service.value_numeric:g}"
        spec = f"numeric_in_source:service:{service.service_name}:{num_str}"
        if num_str in source:
            outcome.spot_checks_passed += 1
        else:
            outcome.spot_checks_failed += 1
            outcome.failures.append(
                GoldenCheckFailure(
                    spec=spec,
                    reason=f"numeric {service.value_numeric} not found in source markdown",
                )
            )

    return outcome


def run_golden_checks(
    validated: ExtractionResult,
    golden: dict[str, Any],
    metrics: ValidationMetrics | None = None,
    *,
    verify_numerics: bool = True,
) -> GoldenCheckResult:
    """Run all golden metadata, row, threshold, and numeric-in-source checks."""
    outcome = GoldenCheckResult()
    _merge_outcomes(outcome, _run_metadata_checks(validated, golden.get("metadata", {})))
    _merge_outcomes(outcome, _run_contract_term_checks(validated, golden.get("contract_terms", [])))
    _merge_outcomes(outcome, _run_service_checks(validated, golden.get("included_services", [])))

    if metrics is not None:
        _merge_outcomes(outcome, run_threshold_checks(metrics, validated, golden))

    if verify_numerics and validated.raw_markdown:
        _merge_outcomes(outcome, verify_numerics_in_source(validated))

    return outcome


def default_golden_path() -> Path:
    """Return the default path to the Northwind golden fixture JSON."""
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "northwind_expected.json"
