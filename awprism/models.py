"""Data models for hypotheses and diagnoses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Hypothesis:
    """A candidate explanation for a symptom.

    Attributes:
        claim: The hypothesis statement (e.g., "the service is down")
        score: Confidence from 0.0 (ruled out) to 1.0 (certain). Always normalized.
        falsifier: The single observation that would confirm or rule this out.
                   Must be non-empty; empty falsifier is a validation error.
        evidence_for: List of observations supporting this hypothesis.
        evidence_against: List of observations contradicting this hypothesis.
        rationale: Explanation of why this hypothesis ranks as it does.
    """

    claim: str
    score: float
    falsifier: str
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    rationale: str = ""

    def __post_init__(self) -> None:
        """Validate and normalize the hypothesis."""
        if not self.claim or not self.claim.strip():
            raise ValueError("claim must not be empty")
        if not self.falsifier or not self.falsifier.strip():
            raise ValueError("falsifier must not be empty; a hypothesis without a test is an opinion")
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"score must be in [0.0, 1.0], got {self.score}")

        self.claim = self.claim.strip()
        self.falsifier = self.falsifier.strip()
        self.rationale = self.rationale.strip() if self.rationale else ""

    def to_dict(self) -> dict:
        """Convert to a dictionary for serialization."""
        return asdict(self)


@dataclass
class Diagnosis:
    """A ranked set of hypotheses explaining a symptom.

    Attributes:
        hypotheses: List of Hypothesis objects, ordered by score (descending).
        symptom: The failure or issue being diagnosed.
        context: Additional context provided to the diagnostic engine.
    """

    hypotheses: list[Hypothesis] = field(default_factory=list)
    symptom: str = ""
    context: str = ""

    def __post_init__(self) -> None:
        """Ensure hypotheses are sorted by score descending and validate count."""
        if self.hypotheses:
            self.hypotheses.sort(key=lambda h: h.score, reverse=True)

    def __len__(self) -> int:
        """Return the number of hypotheses."""
        return len(self.hypotheses)

    def __iter__(self):
        """Iterate over hypotheses in order of confidence."""
        return iter(self.hypotheses)

    def __getitem__(self, idx: int) -> Hypothesis:
        """Access hypothesis by index."""
        return self.hypotheses[idx]

    def to_dict(self) -> dict:
        """Convert to a dictionary for JSON serialization."""
        return {
            "symptom": self.symptom,
            "context": self.context,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
        }

    def to_markdown(self) -> str:
        """Render as markdown for human reading."""
        lines = []
        if self.symptom:
            lines.append(f"# Diagnosis: {self.symptom}\n")
        if self.context:
            lines.append(f"**Context:** {self.context}\n")

        if not self.hypotheses:
            lines.append("No hypotheses generated.\n")
            return "\n".join(lines)

        lines.append("## Ranked Hypotheses\n")
        for i, h in enumerate(self.hypotheses, 1):
            pct = int(h.score * 100)
            lines.append(f"### {i}. {h.claim} ({pct}%)\n")

            if h.rationale:
                lines.append(f"**Why:** {h.rationale}\n")

            if h.falsifier:
                lines.append(f"**Test:** {h.falsifier}\n")

            if h.evidence_for:
                lines.append("**For:**\n")
                for ev in h.evidence_for:
                    lines.append(f"- {ev}\n")

            if h.evidence_against:
                lines.append("**Against:**\n")
                for ev in h.evidence_against:
                    lines.append(f"- {ev}\n")

            lines.append("")

        return "\n".join(lines)
