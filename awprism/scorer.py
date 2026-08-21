"""Scoring and ranking of hypotheses."""

from __future__ import annotations

from awprism.models import Hypothesis


class HypothesisScorer:
    """Scores and ranks hypotheses based on evidence and structure."""

    @staticmethod
    def score_hypothesis(
        claim: str,
        evidence_for: list[str],
        evidence_against: list[str],
        base_score: float = 0.5,
    ) -> float:
        """
        Compute a normalized score for a hypothesis.

        The score starts at base_score and is adjusted by evidence:
        - Each piece of supporting evidence increases the score
        - Each piece of contradicting evidence decreases the score
        - The result is clamped to [0.0, 1.0]

        Args:
            claim: The hypothesis claim (for logging).
            evidence_for: List of supporting observations.
            evidence_against: List of contradicting observations.
            base_score: Starting confidence, typically 0.5.

        Returns:
            A score in [0.0, 1.0].
        """
        if not claim:
            return 0.0

        # Simple evidence-based adjustment: each piece of evidence moves by 0.1
        # More sophisticated scoring could weigh evidence differently
        score = base_score + (len(evidence_for) * 0.05) - (len(evidence_against) * 0.05)

        # Normalize to [0.0, 1.0]
        return max(0.0, min(1.0, score))

    @staticmethod
    def normalize_scores(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        """
        Normalize hypothesis scores so the highest is 1.0 or close.

        Preserves relative ordering while making scores more interpretable.
        """
        if not hypotheses:
            return hypotheses

        scores = [h.score for h in hypotheses]
        max_score = max(scores) if scores else 1.0

        if max_score <= 0.0:
            return hypotheses

        normalized = []
        for h in hypotheses:
            h.score = h.score / max_score
            normalized.append(h)

        return normalized

    @staticmethod
    def rank_by_confidence(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        """
        Sort hypotheses by score descending (highest confidence first).

        Returns:
            Sorted list (highest score first).
        """
        return sorted(hypotheses, key=lambda h: h.score, reverse=True)
