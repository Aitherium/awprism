"""Tests for the core Prism diagnostic engine."""

import pytest
from awprism import Diagnosis, Hypothesis, Prism


class TestHypothesis:
    """Test the Hypothesis data class."""

    def test_valid_hypothesis(self):
        """A valid hypothesis with all fields."""
        h = Hypothesis(
            claim="the service is down",
            score=0.7,
            falsifier="check the status endpoint",
            evidence_for=["timeout occurred"],
            evidence_against=["recent deployments were clean"],
        )
        assert h.claim == "the service is down"
        assert h.score == 0.7
        assert h.falsifier == "check the status endpoint"
        assert len(h.evidence_for) == 1
        assert len(h.evidence_against) == 1

    def test_hypothesis_requires_claim(self):
        """Hypothesis rejects empty claim."""
        with pytest.raises(ValueError, match="claim must not be empty"):
            Hypothesis(claim="", score=0.5, falsifier="test")

    def test_hypothesis_requires_falsifier(self):
        """Hypothesis rejects empty falsifier."""
        with pytest.raises(ValueError, match="falsifier must not be empty"):
            Hypothesis(claim="test claim", score=0.5, falsifier="")

    def test_hypothesis_requires_falsifier_not_just_whitespace(self):
        """Hypothesis rejects whitespace-only falsifier."""
        with pytest.raises(ValueError, match="falsifier must not be empty"):
            Hypothesis(claim="test claim", score=0.5, falsifier="   ")

    def test_hypothesis_score_bounds(self):
        """Hypothesis enforces score in [0.0, 1.0]."""
        with pytest.raises(ValueError, match="score must be in"):
            Hypothesis(claim="test", score=-0.1, falsifier="test")

        with pytest.raises(ValueError, match="score must be in"):
            Hypothesis(claim="test", score=1.1, falsifier="test")

    def test_hypothesis_score_at_bounds(self):
        """Hypothesis accepts score at 0.0 and 1.0."""
        h1 = Hypothesis(claim="test", score=0.0, falsifier="test")
        assert h1.score == 0.0

        h2 = Hypothesis(claim="test", score=1.0, falsifier="test")
        assert h2.score == 1.0

    def test_hypothesis_to_dict(self):
        """Hypothesis converts to dict for JSON."""
        h = Hypothesis(
            claim="test",
            score=0.5,
            falsifier="check X",
            evidence_for=["obs1"],
            rationale="because Y",
        )
        d = h.to_dict()
        assert d["claim"] == "test"
        assert d["score"] == 0.5
        assert d["falsifier"] == "check X"
        assert d["evidence_for"] == ["obs1"]
        assert d["rationale"] == "because Y"


class TestDiagnosis:
    """Test the Diagnosis ranked list."""

    def test_empty_diagnosis(self):
        """Empty diagnosis has length 0."""
        diag = Diagnosis()
        assert len(diag) == 0

    def test_diagnosis_sorts_by_score(self):
        """Diagnosis sorts hypotheses by score descending on init."""
        h1 = Hypothesis(claim="low", score=0.3, falsifier="test")
        h2 = Hypothesis(claim="high", score=0.9, falsifier="test")
        h3 = Hypothesis(claim="mid", score=0.5, falsifier="test")

        diag = Diagnosis(hypotheses=[h1, h2, h3])

        # Should be sorted: high, mid, low
        assert diag.hypotheses[0].score == 0.9
        assert diag.hypotheses[1].score == 0.5
        assert diag.hypotheses[2].score == 0.3

    def test_diagnosis_iteration(self):
        """Diagnosis is iterable."""
        h1 = Hypothesis(claim="a", score=0.5, falsifier="test")
        h2 = Hypothesis(claim="b", score=0.7, falsifier="test")
        diag = Diagnosis(hypotheses=[h1, h2])

        collected = list(diag)
        assert len(collected) == 2
        assert collected[0].score == 0.7  # sorted

    def test_diagnosis_indexing(self):
        """Diagnosis supports indexing."""
        h1 = Hypothesis(claim="first", score=0.5, falsifier="test")
        h2 = Hypothesis(claim="second", score=0.7, falsifier="test")
        diag = Diagnosis(hypotheses=[h1, h2])

        assert diag[0].claim == "second"  # sorted by score
        assert diag[1].claim == "first"

    def test_diagnosis_to_dict(self):
        """Diagnosis converts to dict for JSON."""
        h = Hypothesis(claim="test", score=0.5, falsifier="test")
        diag = Diagnosis(hypotheses=[h], symptom="the API is slow", context="high load")

        d = diag.to_dict()
        assert d["symptom"] == "the API is slow"
        assert d["context"] == "high load"
        assert len(d["hypotheses"]) == 1
        assert d["hypotheses"][0]["claim"] == "test"

    def test_diagnosis_to_markdown(self):
        """Diagnosis renders as markdown."""
        h = Hypothesis(
            claim="database is down",
            score=0.8,
            falsifier="check DB status",
            evidence_for=["connection refused"],
        )
        diag = Diagnosis(hypotheses=[h], symptom="API returns 500")

        md = diag.to_markdown()
        assert isinstance(md, str)
        assert "API returns 500" in md
        assert "database is down" in md
        assert "check DB status" in md
        assert "80%" in md  # score as percentage


class TestPrism:
    """Test the main Prism diagnostic engine."""

    def test_prism_init_default(self):
        """Prism initializes with defaults."""
        prism = Prism()
        assert prism.complete is None
        assert prism.registry is not None

    def test_prism_diagnose_requires_symptom(self):
        """Prism.diagnose() requires non-empty symptom."""
        prism = Prism()

        with pytest.raises(ValueError, match="symptom must not be empty"):
            prism.diagnose("")

        with pytest.raises(ValueError, match="symptom must not be empty"):
            prism.diagnose("   ")

    def test_prism_diagnose_timeout(self):
        """Prism diagnoses timeout symptoms."""
        prism = Prism()
        diagnosis = prism.diagnose("the request timed out")

        assert len(diagnosis) >= 2, "Should generate at least 2 hypotheses"
        assert all(h.falsifier for h in diagnosis), "Every hypothesis needs a falsifier"

    def test_prism_diagnose_auth(self):
        """Prism diagnoses auth failures."""
        prism = Prism()
        diagnosis = prism.diagnose("got 401 unauthorized")

        assert len(diagnosis) >= 2
        assert any("credential" in h.claim.lower() or "permission" in h.claim.lower()
                   for h in diagnosis), "Should suggest credential or permission issues"

    def test_prism_diagnose_resource(self):
        """Prism diagnoses resource exhaustion."""
        prism = Prism()
        diagnosis = prism.diagnose("out of memory error")

        assert len(diagnosis) >= 2

    def test_prism_diagnose_respects_k(self):
        """Prism respects the k parameter."""
        prism = Prism()
        diagnosis = prism.diagnose("the service is slow", k=2)

        assert len(diagnosis) <= 2

    def test_prism_diagnose_at_least_two_hypotheses(self):
        """REQUIREMENT: Prism generates at least 2 hypotheses."""
        prism = Prism()

        # Test with various symptoms to ensure the rule holds
        for symptom in [
            "the service is slow",
            "got a 500 error",
            "database timed out",
            "permission denied",
        ]:
            diagnosis = prism.diagnose(symptom)
            assert len(diagnosis) >= 2, f"Should have 2+ hypotheses for: {symptom}"

    def test_prism_diagnose_all_hypotheses_have_falsifier(self):
        """REQUIREMENT: Every hypothesis has a non-empty falsifier."""
        prism = Prism()
        diagnosis = prism.diagnose("something went wrong")

        for h in diagnosis:
            assert h.falsifier, f"Hypothesis '{h.claim}' lacks a falsifier"
            assert h.falsifier.strip(), f"Hypothesis '{h.claim}' has empty falsifier"

    def test_prism_diagnose_scores_normalized(self):
        """Diagnosis scores are in [0, 1]."""
        prism = Prism()
        diagnosis = prism.diagnose("the service failed")

        for h in diagnosis:
            assert 0.0 <= h.score <= 1.0, f"Score {h.score} out of range"

    def test_prism_diagnose_scores_sorted(self):
        """Diagnosis hypotheses are sorted by score descending."""
        prism = Prism()
        diagnosis = prism.diagnose("network timeout")

        scores = [h.score for h in diagnosis]
        assert scores == sorted(scores, reverse=True), "Scores not sorted descending"

    def test_prism_diagnose_with_context(self):
        """Prism accepts context parameter."""
        prism = Prism()
        diagnosis = prism.diagnose(
            "the API is slow",
            context="this happens every Tuesday at 3 AM",
        )

        assert diagnosis.context == "this happens every Tuesday at 3 AM"
        assert len(diagnosis) >= 2

    def test_prism_diagnose_fallback_for_unknown(self):
        """Prism includes fallback hypotheses for unknown symptoms."""
        prism = Prism()
        diagnosis = prism.diagnose("xyz123nonsense failure")

        # Should still generate hypotheses even for unknown symptoms
        assert len(diagnosis) >= 2
        assert all(h.falsifier for h in diagnosis)
