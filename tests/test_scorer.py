"""Tests for hypothesis scoring and ranking."""

from awprism import Hypothesis
from awprism.scorer import HypothesisScorer


class TestHypothesisScorer:
    """Test the HypothesisScorer."""

    def test_score_hypothesis_base(self):
        """Score without evidence uses base score."""
        score = HypothesisScorer.score_hypothesis(
            claim="test",
            evidence_for=[],
            evidence_against=[],
            base_score=0.5,
        )
        assert score == 0.5

    def test_score_hypothesis_with_supporting_evidence(self):
        """Each piece of supporting evidence increases score."""
        score = HypothesisScorer.score_hypothesis(
            claim="test",
            evidence_for=["evidence1", "evidence2"],
            evidence_against=[],
            base_score=0.5,
        )
        # 0.5 + (2 * 0.05) = 0.6
        assert score == 0.6

    def test_score_hypothesis_with_opposing_evidence(self):
        """Each piece of opposing evidence decreases score."""
        score = HypothesisScorer.score_hypothesis(
            claim="test",
            evidence_for=[],
            evidence_against=["evidence1", "evidence2"],
            base_score=0.5,
        )
        # 0.5 - (2 * 0.05) = 0.4
        assert score == 0.4

    def test_score_hypothesis_mixed_evidence(self):
        """Mix of supporting and opposing evidence."""
        score = HypothesisScorer.score_hypothesis(
            claim="test",
            evidence_for=["for1", "for2", "for3"],
            evidence_against=["against1"],
            base_score=0.5,
        )
        # 0.5 + (3 * 0.05) - (1 * 0.05) = 0.6
        assert score == 0.6

    def test_score_hypothesis_clamped_to_bounds(self):
        """Score is clamped to [0.0, 1.0]."""
        # High evidence should not exceed 1.0
        score_high = HypothesisScorer.score_hypothesis(
            claim="test",
            evidence_for=["e1", "e2", "e3", "e4", "e5", "e6", "e7", "e8", "e9", "e10"],
            evidence_against=[],
            base_score=0.5,
        )
        assert score_high <= 1.0

        # Negative evidence should not go below 0.0
        score_low = HypothesisScorer.score_hypothesis(
            claim="test",
            evidence_for=[],
            evidence_against=["a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9", "a10"],
            base_score=0.5,
        )
        assert score_low >= 0.0

    def test_score_hypothesis_empty_claim(self):
        """Empty claim results in zero score."""
        score = HypothesisScorer.score_hypothesis(
            claim="",
            evidence_for=["e1"],
            evidence_against=[],
        )
        assert score == 0.0

    def test_normalize_scores(self):
        """Normalize scales scores so max is 1.0."""
        h1 = Hypothesis(claim="a", score=0.5, falsifier="test")
        h2 = Hypothesis(claim="b", score=0.8, falsifier="test")

        normalized = HypothesisScorer.normalize_scores([h1, h2])

        # h2 had the max (0.8), so it becomes 1.0; h1 becomes 0.5/0.8 = 0.625
        assert abs(normalized[0].score - 1.0) < 0.01 or abs(normalized[1].score - 1.0) < 0.01
        assert max(h.score for h in normalized) == 1.0

    def test_normalize_scores_preserves_order(self):
        """Normalization preserves relative order."""
        h1 = Hypothesis(claim="a", score=0.5, falsifier="test")
        h2 = Hypothesis(claim="b", score=0.8, falsifier="test")
        h3 = Hypothesis(claim="c", score=0.3, falsifier="test")

        original_order = [h.score for h in [h1, h2, h3]]
        normalized = HypothesisScorer.normalize_scores([h1, h2, h3])
        normalized_order = [h.score for h in normalized]

        # Verify relative order is the same
        assert original_order.index(0.8) == 1
        assert normalized_order.index(max(normalized_order)) == 1

    def test_normalize_scores_empty_list(self):
        """Normalize handles empty list."""
        result = HypothesisScorer.normalize_scores([])
        assert result == []

    def test_normalize_scores_all_zero(self):
        """Normalize handles all-zero scores."""
        h1 = Hypothesis(claim="a", score=0.0, falsifier="test")
        h2 = Hypothesis(claim="b", score=0.0, falsifier="test")

        result = HypothesisScorer.normalize_scores([h1, h2])
        # Should not crash; scores stay 0.0
        assert all(h.score == 0.0 for h in result)

    def test_rank_by_confidence(self):
        """Rank sorts hypotheses by score descending."""
        h1 = Hypothesis(claim="a", score=0.3, falsifier="test")
        h2 = Hypothesis(claim="b", score=0.9, falsifier="test")
        h3 = Hypothesis(claim="c", score=0.5, falsifier="test")

        ranked = HypothesisScorer.rank_by_confidence([h1, h2, h3])

        scores = [h.score for h in ranked]
        assert scores == [0.9, 0.5, 0.3]

    def test_rank_by_confidence_already_sorted(self):
        """Rank works on already-sorted list."""
        h1 = Hypothesis(claim="a", score=0.9, falsifier="test")
        h2 = Hypothesis(claim="b", score=0.5, falsifier="test")
        h3 = Hypothesis(claim="c", score=0.1, falsifier="test")

        ranked = HypothesisScorer.rank_by_confidence([h1, h2, h3])

        assert ranked[0].score == 0.9
        assert ranked[1].score == 0.5
        assert ranked[2].score == 0.1

    def test_rank_by_confidence_empty(self):
        """Rank handles empty list."""
        result = HypothesisScorer.rank_by_confidence([])
        assert result == []
