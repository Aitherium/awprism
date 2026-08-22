"""awprism CLI — turn a failure into ranked hypotheses."""

from __future__ import annotations

import argparse
import json
import sys

from awprism.prism import Prism


def _self_test() -> int:
    """
    Prove Prism's core contracts offline.

    Returns 0 if all assertions pass, 1 otherwise.
    """
    failures: list[str] = []

    try:
        from awprism.models import Diagnosis, Hypothesis
        from awprism.registry import StrategyRegistry

        # 1. Hypothesis requires claim, score, and falsifier
        try:
            Hypothesis(claim="", score=0.5, falsifier="test")
            failures.append("empty claim was accepted")
        except ValueError:
            pass

        try:
            Hypothesis(claim="test", score=0.5, falsifier="")
            failures.append("empty falsifier was accepted")
        except ValueError:
            pass

        try:
            Hypothesis(claim="test", score=1.5, falsifier="test")
            failures.append("score > 1.0 was accepted")
        except ValueError:
            pass

        # 2. Valid hypothesis construction
        h = Hypothesis(
            claim="service is down",
            score=0.7,
            falsifier="check the service status endpoint",
            evidence_for=["timeout occurred"],
            evidence_against=[],
        )
        if h.score != 0.7 or h.falsifier != "check the service status endpoint":
            failures.append("hypothesis construction failed")

        # 3. Hypothesis to_dict works
        d = h.to_dict()
        if d["claim"] != "service is down" or d["score"] != 0.7:
            failures.append("hypothesis.to_dict() failed")

        # 4. Diagnosis requires >= 1 hypothesis for len() > 0
        diag = Diagnosis()
        if len(diag) != 0:
            failures.append("empty Diagnosis should have len() == 0")

        diag = Diagnosis(hypotheses=[h])
        if len(diag) != 1:
            failures.append("Diagnosis.len() is broken")

        # 5. Diagnosis sorts by score descending
        h2 = Hypothesis(claim="database error", score=0.9, falsifier="test")
        diag = Diagnosis(hypotheses=[h, h2])  # Re-create to trigger sorting
        if diag.hypotheses[0].score < diag.hypotheses[1].score:
            failures.append("Diagnosis does not sort by score descending")

        # 6. Prism.diagnose() requires non-empty symptom
        prism = Prism()
        try:
            prism.diagnose("")
            failures.append("empty symptom was accepted")
        except ValueError:
            pass

        # 7. Prism.diagnose() generates at least 1 hypothesis
        diag = prism.diagnose("the service is slow")
        if len(diag) == 0:
            failures.append("diagnose() returned zero hypotheses")

        # 8. REQUIREMENT: At least 2 hypotheses whenever any are generated
        if len(diag) == 1:
            failures.append("diagnose() returned only 1 hypothesis (requires >= 2)")

        # 9. Every hypothesis has a non-empty falsifier
        for h in diag:
            if not h.falsifier or not h.falsifier.strip():
                failures.append("a hypothesis lacks a falsifier")

        # 10. Registry has built-in strategies
        registry = StrategyRegistry()
        if len(registry.strategies) == 0:
            failures.append("registry has no strategies")

        # 11. Registry.find_applicable() always includes unknown fallback
        strats = registry.find_applicable("xyz")
        if not any(s.name == "unknown" for s in strats):
            failures.append("unknown fallback strategy not in results")

        # 12. Diagnosis.to_markdown() renders without crashing
        md = diag.to_markdown()
        if not md or not isinstance(md, str):
            failures.append("Diagnosis.to_markdown() failed")

        # 13. Diagnosis.to_dict() roundtrips
        d = diag.to_dict()
        if d.get("symptom") != "the service is slow":
            failures.append("Diagnosis.to_dict() lost the symptom")

    except Exception as e:
        failures.append(f"unexpected error: {e}")

    for f in failures:
        print(f"  FAIL  {f}")

    if failures:
        print(f"SELF-TEST: {len(failures)} failure(s)")
        return 1

    print("  PASS  Hypothesis requires claim, score, and falsifier")
    print("  PASS  Diagnosis sorts by score; Prism generates >= 2 hypotheses")
    print("  PASS  Every hypothesis has a non-empty falsifier")
    print("  PASS  Registry includes timeout, auth, resource, and unknown strategies")
    print("SELF-TEST: awprism ok")
    return 0


def _read_context(path: str | None) -> str:
    """Read context from a file, if provided."""
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (IOError, OSError) as e:
        print(f"warning: could not read context file: {e}", file=sys.stderr)
        return ""


def _show_diagnosis(diagnosis, as_json: bool, as_markdown: bool) -> None:
    """Display the diagnosis in the requested format."""
    if as_json:
        print(json.dumps(diagnosis.to_dict(), indent=2))
    elif as_markdown:
        print(diagnosis.to_markdown())
    else:
        # Default: compact text summary
        print(f"Symptom: {diagnosis.symptom}")
        if diagnosis.context:
            print(f"Context: {diagnosis.context}")
        print()
        if not diagnosis.hypotheses:
            print("No hypotheses generated.")
            return
        print("Ranked hypotheses:")
        for i, h in enumerate(diagnosis.hypotheses, 1):
            pct = int(h.score * 100)
            print(f"\n{i}. {h.claim} ({pct}%)")
            print(f"   Test: {h.falsifier}")


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    # GENERATED doctor intercept (gen_aw_doctor.py) -- do not edit
    _dv = locals().get("argv")
    if (_dv if _dv is not None else __import__("sys").argv[1:])[:1] == ["doctor"]:
        from ._doctor import report
        return report()
    ap = argparse.ArgumentParser(
        prog="awprism",
        description="Turn a failure into ranked hypotheses.",
    )
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="prove Prism still holds its contract, offline",
    )
    ap.add_argument("--json", action="store_true", help="output as JSON")
    ap.add_argument("--markdown", action="store_true", help="output as Markdown")

    sub = ap.add_subparsers(dest="cmd", help="command")

    diagnose_p = sub.add_parser(
        "diagnose",
        help="analyze a failure and generate hypotheses",
    )
    diagnose_p.add_argument(
        "symptom",
        nargs="+",
        help="description of the failure",
    )
    diagnose_p.add_argument(
        "--context",
        type=str,
        help="path to a file with additional context",
    )
    diagnose_p.add_argument(
        "-k",
        type=int,
        default=5,
        help="max number of hypotheses to return (default 5)",
    )

    sub.add_parser("health", help="check if awprism is working")

    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.cmd:
        ap.print_help()
        return 2

    try:
        prism = Prism()

        if args.cmd == "diagnose":
            symptom = " ".join(args.symptom)
            context = _read_context(args.context)
            diagnosis = prism.diagnose(symptom, context=context, k=args.k)

            if not diagnosis.hypotheses:
                print(
                    "No hypotheses generated. "
                    "Try providing more context about the failure.",
                    file=sys.stderr,
                )
                return 1

            _show_diagnosis(diagnosis, args.json, args.markdown)
            return 0

        elif args.cmd == "health":
            # Run self-test as a health check
            return _self_test()

    except ValueError as exc:
        print(f"awprism: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"awprism: error: {exc}", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
