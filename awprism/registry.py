"""Registry of reusable diagnostic strategies and patterns."""

from __future__ import annotations

from typing import Callable

from awprism.models import Hypothesis


class DiagnosticStrategy:
    """A reusable diagnostic pattern for a class of failures."""

    def __init__(
        self,
        name: str,
        description: str,
        pattern_check: Callable[[str], bool],
        generate_hypotheses: Callable[[str, str], list[Hypothesis]],
    ):
        """
        Initialize a diagnostic strategy.

        Args:
            name: Strategy identifier (e.g., "network_timeout").
            description: Human-readable explanation.
            pattern_check: Function that returns True if this strategy applies.
            generate_hypotheses: Function that generates hypotheses for this pattern.
        """
        self.name = name
        self.description = description
        self.pattern_check = pattern_check
        self.generate_hypotheses = generate_hypotheses

    def applies_to(self, symptom: str) -> bool:
        """Check if this strategy applies to the given symptom."""
        try:
            return self.pattern_check(symptom.lower())
        except Exception:
            return False

    def diagnose(self, symptom: str, context: str = "") -> list[Hypothesis]:
        """Generate hypotheses using this strategy."""
        try:
            return self.generate_hypotheses(symptom, context)
        except Exception:
            return []


class StrategyRegistry:
    """Collection of diagnostic strategies that apply to common failures."""

    def __init__(self):
        """Initialize with built-in strategies."""
        self.strategies: dict[str, DiagnosticStrategy] = {}
        self._register_builtin_strategies()

    def _register_builtin_strategies(self) -> None:
        """Register commonly useful diagnostic patterns."""

        # Network/connectivity issues
        def timeout_pattern(s: str) -> bool:
            return any(
                w in s
                for w in [
                    "timeout",
                    "took too long",
                    "never responded",
                    "slow",
                    "hung",
                    "stalled",
                    "freezing",
                ]
            )

        def timeout_hyps(symptom: str, context: str) -> list[Hypothesis]:
            return [
                Hypothesis(
                    claim="The service is genuinely slow or under heavy load",
                    score=0.7,
                    falsifier="Run the same operation at off-peak hours and measure latency",
                    evidence_for=["Timeout happened"],
                    evidence_against=[],
                    rationale="Services degrade under load; this is the most common case.",
                ),
                Hypothesis(
                    claim="A network interface is dropping packets or has poor throughput",
                    score=0.5,
                    falsifier="Check network metrics (packet loss, bandwidth utilization) during the timeout",
                    evidence_for=["Timeout happened"],
                    evidence_against=[],
                    rationale="Network problems often appear as timeouts before any error message.",
                ),
                Hypothesis(
                    claim="The service or a critical dependency has crashed and restarted",
                    score=0.4,
                    falsifier="Check service logs and restart timestamps around the time of the timeout",
                    evidence_for=["Timeout happened"],
                    evidence_against=[],
                    rationale="A restart is usually brief; a one-off timeout might indicate this.",
                ),
            ]

        self.register(
            DiagnosticStrategy(
                name="timeout",
                description="Diagnoses timeout and slowness issues",
                pattern_check=timeout_pattern,
                generate_hypotheses=timeout_hyps,
            )
        )

        # Authentication/access issues
        def auth_pattern(s: str) -> bool:
            return any(
                w in s for w in ["unauthorized", "401", "403", "forbidden", "denied", "permission"]
            )

        def auth_hyps(symptom: str, context: str) -> list[Hypothesis]:
            return [
                Hypothesis(
                    claim="The provided credentials are incorrect or expired",
                    score=0.7,
                    falsifier="Verify the credential against the service's own settings or re-authenticate",
                    evidence_for=["Authorization failed"],
                    evidence_against=[],
                    rationale="Expired or wrong credentials are the most common auth failure.",
                ),
                Hypothesis(
                    claim="The account lacks the required permissions for this operation",
                    score=0.6,
                    falsifier="Check the account's role and grant permissions, then retry",
                    evidence_for=["Authorization failed"],
                    evidence_against=[],
                    rationale="Permission mismatches often hide behind 403 errors.",
                ),
                Hypothesis(
                    claim="The service's auth system is temporarily unavailable",
                    score=0.4,
                    falsifier="Check the auth service status and try a different account if possible",
                    evidence_for=["Authorization failed"],
                    evidence_against=[],
                    rationale="Auth service outages are rare but leave no error trail.",
                ),
            ]

        self.register(
            DiagnosticStrategy(
                name="auth",
                description="Diagnoses authentication and authorization failures",
                pattern_check=auth_pattern,
                generate_hypotheses=auth_hyps,
            )
        )

        # Resource exhaustion
        def resource_pattern(s: str) -> bool:
            return any(
                w in s
                for w in ["out of memory", "disk full", "no space", "resource", "quota", "limit"]
            )

        def resource_hyps(symptom: str, context: str) -> list[Hypothesis]:
            return [
                Hypothesis(
                    claim="A resource has truly been exhausted on the service or host",
                    score=0.8,
                    falsifier="Check available disk/memory on the affected server at the time of failure",
                    evidence_for=["Resource error reported"],
                    evidence_against=[],
                    rationale="Resource errors are usually accurate; the OS does not lie about them.",
                ),
                Hypothesis(
                    claim="A resource limit (quota, connection pool) has been hit",
                    score=0.7,
                    falsifier="Check configured limits and current usage; increase or clear the limit and retry",
                    evidence_for=["Resource error reported"],
                    evidence_against=[],
                    rationale="Soft limits can be raised; this is a common mis-configuration.",
                ),
                Hypothesis(
                    claim="A long-running process or memory leak is consuming resources",
                    score=0.5,
                    falsifier="Restart the service and monitor resource usage over time",
                    evidence_for=["Resource error reported"],
                    evidence_against=[],
                    rationale="Leaks are harder to spot; a restart often works temporarily.",
                ),
            ]

        self.register(
            DiagnosticStrategy(
                name="resource",
                description="Diagnoses resource exhaustion",
                pattern_check=resource_pattern,
                generate_hypotheses=resource_hyps,
            )
        )

        # Generic/unknown failures
        def unknown_pattern(s: str) -> bool:
            return True  # Always matches as fallback

        def unknown_hyps(symptom: str, context: str) -> list[Hypothesis]:
            return [
                Hypothesis(
                    claim="The immediate cause is misdiagnosed or the error message is misleading",
                    score=0.6,
                    falsifier="Re-run the operation and capture full logs; compare to the reported error",
                    evidence_for=["Failure occurred"],
                    evidence_against=[],
                    rationale="The first error is often a symptom, not the root cause.",
                ),
                Hypothesis(
                    claim="A required service or dependency is down or unreachable",
                    score=0.5,
                    falsifier="Verify connectivity and status of all upstream services",
                    evidence_for=["Failure occurred"],
                    evidence_against=[],
                    rationale="Dependency failures cascade; check the dependency chain.",
                ),
                Hypothesis(
                    claim="The operation is not supported or was never implemented",
                    score=0.4,
                    falsifier="Check the service's documentation or API schema for this operation",
                    evidence_for=["Failure occurred"],
                    evidence_against=[],
                    rationale="Silent no-ops can look like failures; verify the feature exists.",
                ),
            ]

        self.register(
            DiagnosticStrategy(
                name="unknown",
                description="Generic fallback strategies for unclassified failures",
                pattern_check=unknown_pattern,
                generate_hypotheses=unknown_hyps,
            )
        )

    def register(self, strategy: DiagnosticStrategy) -> None:
        """Register a new diagnostic strategy."""
        self.strategies[strategy.name] = strategy

    def find_applicable(self, symptom: str) -> list[DiagnosticStrategy]:
        """Find all strategies that apply to the given symptom."""
        applicable = [s for s in self.strategies.values() if s.applies_to(symptom)]

        # Ensure unknown/fallback is always last
        fallback = self.strategies.get("unknown")
        if fallback and fallback in applicable:
            applicable.remove(fallback)
            applicable.append(fallback)

        return applicable

    def get(self, name: str) -> DiagnosticStrategy | None:
        """Get a strategy by name."""
        return self.strategies.get(name)
