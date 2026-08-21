"""The Prism diagnostic engine."""

from __future__ import annotations

import json
from typing import Callable

from awprism.models import Diagnosis, Hypothesis
from awprism.registry import StrategyRegistry
from awprism.scorer import HypothesisScorer


class Prism:
    """
    Turns a failure into ranked hypotheses, each with a test that would confirm or rule it out.

    The Prism engine is pluggable: you supply a completion backend (or use heuristics),
    and it ranks candidate causes by available evidence.
    """

    def __init__(
        self,
        complete: Callable[[str], str] | None = None,
        registry: StrategyRegistry | None = None,
    ):
        """
        Initialize Prism.

        Args:
            complete: A callable that takes a prompt string and returns a completion.
                      If None, Prism operates in heuristic/structural mode.
            registry: A StrategyRegistry for reusable diagnostic patterns.
                      If None, a default registry is created.
        """
        self.complete = complete
        self.registry = registry or StrategyRegistry()
        self.scorer = HypothesisScorer()

    def diagnose(
        self,
        symptom: str,
        context: str = "",
        k: int = 5,
    ) -> Diagnosis:
        """
        Generate ranked hypotheses explaining a failure symptom.

        Args:
            symptom: The failure or issue (e.g., "the API returns 500 on login").
            context: Additional context about the system or recent changes.
            k: Maximum number of hypotheses to return (default 5).

        Returns:
            A Diagnosis with ranked hypotheses, or an empty Diagnosis if none apply.

        Raises:
            ValueError: If the symptom is empty.
        """
        if not symptom or not symptom.strip():
            raise ValueError("symptom must not be empty")

        symptom = symptom.strip()
        context = (context or "").strip()

        # Find applicable diagnostic strategies
        applicable_strategies = self.registry.find_applicable(symptom)

        # Collect hypotheses from all applicable strategies
        all_hypotheses: dict[str, Hypothesis] = {}

        for strategy in applicable_strategies:
            hypotheses = strategy.diagnose(symptom, context)
            for h in hypotheses:
                # Use the claim as a key to avoid duplicates
                if h.claim not in all_hypotheses:
                    all_hypotheses[h.claim] = h

        # If we have an LLM backend, enhance the hypotheses
        if self.complete:
            all_hypotheses = self._enhance_with_llm(
                symptom, context, all_hypotheses
            )

        # Score, rank, and limit to k
        hypotheses_list = list(all_hypotheses.values())

        if hypotheses_list:
            hypotheses_list = self.scorer.rank_by_confidence(hypotheses_list)
            hypotheses_list = hypotheses_list[:k]

        # REQUIREMENT: at least 2 hypotheses if any generated
        if len(hypotheses_list) == 1:
            # If only 1, generate at least one more (fallback)
            fallback = self._generate_fallback_hypothesis(symptom)
            hypotheses_list.append(fallback)
            hypotheses_list = self.scorer.rank_by_confidence(hypotheses_list)

        return Diagnosis(
            hypotheses=hypotheses_list,
            symptom=symptom,
            context=context,
        )

    def _enhance_with_llm(
        self,
        symptom: str,
        context: str,
        hypotheses: dict[str, Hypothesis],
    ) -> dict[str, Hypothesis]:
        """
        Use the completion backend to enhance or generate additional hypotheses.

        This is a simple integration point; a more sophisticated version could
        use structured extraction or few-shot prompting.
        """
        if not self.complete or not hypotheses:
            return hypotheses

        try:
            prompt = self._build_llm_prompt(symptom, context, hypotheses)
            response = self.complete(prompt)

            # Try to extract JSON-formatted hypotheses from the response
            enhanced = self._parse_llm_response(response)
            for hyp in enhanced:
                if hyp.claim not in hypotheses:
                    hypotheses[hyp.claim] = hyp
        except Exception:
            # If LLM enhancement fails, fall back to the structural hypotheses
            pass

        return hypotheses

    def _build_llm_prompt(
        self,
        symptom: str,
        context: str,
        hypotheses: dict[str, Hypothesis],
    ) -> str:
        """Build a prompt for the LLM to refine hypotheses."""
        existing = "\n".join(
            [f"- {h.claim} ({int(h.score * 100)}%)" for h in hypotheses.values()]
        )

        prompt = f"""You are a diagnostic expert. Analyze this failure and provide ranked hypotheses.

FAILURE: {symptom}

CONTEXT: {context or "(none)"}

EXISTING HYPOTHESES:
{existing}

Your task:
1. Rank these by likelihood (consider which is most commonly the cause).
2. For EACH hypothesis, provide:
   - A falsifier: the one observation that would confirm or rule it out
   - Evidence for: observations supporting it
   - Evidence against: observations contradicting it
3. If applicable, suggest 1-2 additional hypotheses not listed.

Output as JSON with this structure:
{{
  "hypotheses": [
    {{
      "claim": "...",
      "score": 0.X,
      "falsifier": "...",
      "evidence_for": [...],
      "evidence_against": [...],
      "rationale": "..."
    }}
  ]
}}

Be concise. Focus on the most likely causes."""

        return prompt

    def _parse_llm_response(self, response: str) -> list[Hypothesis]:
        """Parse hypothesis objects from an LLM response."""
        hypotheses = []
        try:
            # Find JSON in the response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                data = json.loads(json_str)

                for item in data.get("hypotheses", []):
                    try:
                        hyp = Hypothesis(
                            claim=item.get("claim", "").strip(),
                            score=float(item.get("score", 0.5)),
                            falsifier=item.get("falsifier", "").strip(),
                            evidence_for=item.get("evidence_for", []),
                            evidence_against=item.get("evidence_against", []),
                            rationale=item.get("rationale", "").strip(),
                        )
                        hypotheses.append(hyp)
                    except (ValueError, TypeError):
                        # Skip malformed hypotheses
                        pass
        except (json.JSONDecodeError, AttributeError):
            pass

        return hypotheses

    def _generate_fallback_hypothesis(self, symptom: str) -> Hypothesis:
        """Generate a fallback hypothesis when none apply."""
        return Hypothesis(
            claim="The problem is a rare edge case or a misconfiguration specific to this setup",
            score=0.3,
            falsifier="Review the system configuration and compare to a known-good baseline",
            evidence_for=[],
            evidence_against=[],
            rationale="When common causes don't fit, look for unusual configuration or environment.",
        )


class PrismError(Exception):
    """Raised when Prism encounters an unrecoverable error."""

    pass
