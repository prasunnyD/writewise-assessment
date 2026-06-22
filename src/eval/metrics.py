"""Validation metrics computed from pre/post validator extraction results."""

from __future__ import annotations

from dataclasses import dataclass, field

from models.extraction import ExtractionResult

CRITICAL_WARNING_FRAGMENTS = ("No contract terms survived validation",)


@dataclass
class ValidationMetrics:
    """Row counts and warning deltas from pre/post validation."""

    terms_in: int
    terms_out: int
    terms_dropped: int
    services_in: int
    services_out: int
    services_dropped: int
    assumptions_in: int
    warnings_before: int
    warnings_after: int
    warnings_added: list[str] = field(default_factory=list)
    critical_warnings: list[str] = field(default_factory=list)

    @property
    def terms_drop_rate(self) -> float:
        """Fraction of contract terms removed by validation."""
        if self.terms_in == 0:
            return 0.0
        return self.terms_dropped / self.terms_in

    @property
    def services_drop_rate(self) -> float:
        """Fraction of included services removed by validation."""
        if self.services_in == 0:
            return 0.0
        return self.services_dropped / self.services_in


def build_validation_metrics(before: ExtractionResult, after: ExtractionResult) -> ValidationMetrics:
    """Compare extraction results before and after validation."""
    warnings_before = len(before.warnings)
    warnings_after = len(after.warnings)
    warnings_added = after.warnings[warnings_before:]
    critical_warnings = [
        warning
        for warning in after.warnings
        if any(fragment in warning for fragment in CRITICAL_WARNING_FRAGMENTS)
    ]

    return ValidationMetrics(
        terms_in=len(before.contract_terms),
        terms_out=len(after.contract_terms),
        terms_dropped=len(before.contract_terms) - len(after.contract_terms),
        services_in=len(before.included_services),
        services_out=len(after.included_services),
        services_dropped=len(before.included_services) - len(after.included_services),
        assumptions_in=len(before.assumptions),
        warnings_before=warnings_before,
        warnings_after=warnings_after,
        warnings_added=warnings_added,
        critical_warnings=critical_warnings,
    )
