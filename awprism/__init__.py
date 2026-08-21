"""awprism — turn a failure into ranked hypotheses.

    from awprism import Prism, Hypothesis, Diagnosis

    prism = Prism()
    diagnosis = prism.diagnose(
        "the database connection timed out",
        context="this happens only on the replica, not primary",
    )

    for hyp in diagnosis:
        print(f"• {hyp.claim}: {hyp.falsifier}")

    # Or use the CLI:
    # awprism diagnose "the API returns 500"
    # awprism diagnose "service is slow" --context config.txt --markdown

Read `prism.py` before adding a diagnostic strategy: the Prism class already has
everything in place; new strategies go in the registry (`registry.py`).
"""

from __future__ import annotations

from awprism.models import Diagnosis, Hypothesis
from awprism.prism import Prism, PrismError
from awprism.registry import DiagnosticStrategy, StrategyRegistry
from awprism.scorer import HypothesisScorer

__version__ = "0.1.0"

__all__ = [
    "Prism",
    "PrismError",
    "Hypothesis",
    "Diagnosis",
    "StrategyRegistry",
    "DiagnosticStrategy",
    "HypothesisScorer",
    "__version__",
]
