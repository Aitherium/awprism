# awprism

**Turn a failure into ranked hypotheses — and say what would confirm each one.**

```bash
pip install awprism
```

```python
from awprism import Prism

prism = Prism()
diagnosis = prism.diagnose(
    "the database connection timed out",
    context="this happens only on the replica, not primary",
)

for hyp in diagnosis:
    print(f"• {hyp.claim}")
    print(f"  Test: {hyp.falsifier}")
    print()
```

```bash
awprism diagnose "the API returns 500"
awprism diagnose "service is slow" --context config.txt --markdown
awprism diagnose "network timeout" -k 3 --json
awprism health
awprism --self-test
```

---

## What this is

When debugging with an agent, the conversation collapses onto the **first plausible story**.
That's not wrong, but it's systematically biased: the loudest error in the logs often names
an innocent service, so the first plausible explanation leads away from the root cause.

Prism breaks the first-story bias by generating **multiple ranked hypotheses** for every
failure, each with a **falsifier** — the single observation that would confirm or rule it
out. Instead of picking a theory and defending it, you now know what to check first.

Prism ranks candidates by the evidence at hand, degrades gracefully without an LLM, and
works offline.

| thing | what it does |
|---|---|
| `Prism.diagnose()` | Takes a symptom + context, returns ranked hypotheses |
| `Hypothesis` | A candidate cause with a claim, score, and the test that would separate it |
| `Diagnosis` | A ranked list of hypotheses with `.to_dict()` / `.to_markdown()` |
| `StrategyRegistry` | Reusable diagnostic patterns for timeout, auth, resource, etc. |

---

## The bug this package exists to prevent

Debugging produces a narrative. A narrative is a story that sounds good, which is the
exact opposite of what you want. The story you pick is the one you'll defend, which is
the story you won't question.

Prism forces the question: *What if I'm wrong about this?* It doesn't answer for you —
it just hands you the test that would tell.

---

## Core API

### `Prism(complete=None, registry=None)`

Create a diagnostic engine.

**Arguments:**
- `complete` — Optional LLM completion callable: `(prompt: str) -> str`. If omitted, Prism
  operates in heuristic mode using structural patterns.
- `registry` — Optional `StrategyRegistry`. If omitted, a default registry with built-in
  strategies is created.

### `diagnosis = prism.diagnose(symptom, context="", k=5)`

Generate ranked hypotheses for a failure.

**Arguments:**
- `symptom` — Description of the failure (required, non-empty).
- `context` — Additional background (optional).
- `k` — Maximum number of hypotheses to return (default 5).

**Returns:**
- `Diagnosis` object with `.hypotheses` (sorted by score) and `.to_dict()` / `.to_markdown()`.

**Raises:**
- `ValueError` if symptom is empty.

### `Hypothesis`

```python
Hypothesis(
    claim="the service is down",
    score=0.7,                                     # 0.0 to 1.0
    falsifier="check the service status endpoint", # the one test
    evidence_for=["timeout occurred"],             # supporting observations
    evidence_against=[],                           # contradicting observations
    rationale="timeouts are common when services are overloaded",
)
```

- **claim** — The hypothesis statement (required).
- **score** — Confidence from 0.0 (ruled out) to 1.0 (certain). Always in [0, 1].
- **falsifier** — The single observation that would confirm or rule this out (required,
  non-empty).
- **evidence_for** — List of supporting observations (default: `[]`).
- **evidence_against** — List of contradicting observations (default: `[]`).
- **rationale** — Explanation of the score (default: `""`).

A hypothesis without a falsifier is an opinion. The package enforces non-empty falsifiers.

### `Diagnosis`

```python
diagnosis.hypotheses       # list of Hypothesis, sorted by score (descending)
diagnosis.symptom          # the original symptom string
diagnosis.context          # the context, if provided

len(diagnosis)             # number of hypotheses
for h in diagnosis:        # iterate hypotheses
    ...
diagnosis[0]               # first hypothesis (highest score)

diagnosis.to_dict()        # serialize to dict (for JSON)
diagnosis.to_markdown()    # render as markdown (for human reading)
```

---

## Degraded mode (no LLM)

Prism generates hypotheses even without a completion backend, using a registry of
reusable diagnostic patterns:

- **timeout** — service overload, network throughput, crash+restart
- **auth** — wrong credentials, missing permissions, auth system down
- **resource** — disk full, out of memory, quota hit, memory leak
- **unknown** — fallback for anything else

Each pattern comes with ranked hypotheses backed by structural reasoning. You can add
your own with `registry.register(DiagnosticStrategy(...))`.

---

## CLI

### `awprism diagnose SYMPTOM [OPTIONS]`

Analyze a failure.

**Options:**
- `--context FILE` — Path to a file with additional context.
- `-k N` — Max hypotheses to return (default 5).
- `--json` — Output as JSON.
- `--markdown` — Output as Markdown.

**Examples:**
```bash
awprism diagnose "API returns 500"
awprism diagnose "database timed out" --context logs.txt --markdown
awprism diagnose "network unreachable" -k 3 --json
```

### `awprism health`

Run the self-test to verify Prism is working.

### `awprism --self-test`

Prove Prism holds its core contracts offline (no network, no LLM).

---

## What this does NOT do

**It does not execute checks.** Prism tells you what to measure, not how to measure it or
whether the measurement passes. You decide.

**It does not fix anything.** It diagnoses and ranks; fixing is your call.

**It does not replace a monitoring system.** Alerts tell you something broke; Prism tells
you what might have broken it.

**It does not substitute for domain knowledge.** Prism works with what you tell it. If you
know the system well, use that — Prism augments it, not replaces it.

---

## Adding diagnostic strategies

A `DiagnosticStrategy` is a pattern that applies to a class of failures and generates
relevant hypotheses.

```python
from awprism import Prism, DiagnosticStrategy, Hypothesis

def my_pattern_applies(symptom: str) -> bool:
    return "crash" in symptom.lower()

def my_hypotheses(symptom: str, context: str) -> list[Hypothesis]:
    return [
        Hypothesis(
            claim="the process ran out of memory",
            score=0.8,
            falsifier="check memory usage at the crash time",
        ),
        Hypothesis(
            claim="a signal was sent to terminate the process",
            score=0.5,
            falsifier="check system logs for SIGKILL or administrative actions",
        ),
    ]

strategy = DiagnosticStrategy(
    name="crash",
    description="Diagnoses process crashes",
    pattern_check=my_pattern_applies,
    generate_hypotheses=my_hypotheses,
)

prism = Prism()
prism.registry.register(strategy)

diagnosis = prism.diagnose("the worker process crashed")
```

---

## `--self-test`

Every install can prove Prism still holds its contracts, offline:

```console
$ awprism --self-test
  PASS  Hypothesis requires claim, score, and falsifier
  PASS  Diagnosis sorts by score; Prism generates >= 2 hypotheses
  PASS  Every hypothesis has a non-empty falsifier
  PASS  Registry includes timeout, auth, resource, and unknown strategies
SELF-TEST: awprism ok
```

The key assertions:
- A `Hypothesis` without a falsifier is rejected.
- `Prism.diagnose()` always generates at least 2 hypotheses (or none).
- Every hypothesis has a non-empty, non-whitespace falsifier.
- The `StrategyRegistry` includes built-in patterns for common failure classes.

---

## The aw family

Standalone tools that share one idea: **replace something you would otherwise have to _trust_
with something you can _check_.**

Each installs on its own, works offline, and needs no account.

| instead of trusting | you check |
|---|---|
| that a framework's idea of how your agents should run | one loop you can read, pointed at a backend you already pay for |
| that an agent knows your procedure | the procedure written down, versioned, and loadable by any agent |
| that memory stayed in its lane | tenant:user:project scopes, so a write cannot cross a boundary |
| that a vendor's cloud with every prompt | a local gateway routing to backends you chose |
| that grep found everything | an AST + tree-sitter call graph an agent can traverse |
| that no one else is editing this file | a lease, refused at commit time if you do not hold it |
| that the artifact came from who you think | an Ed25519 seal — the key that verifies is not the key that forges |
| that the download is intact | content-addressed bundles, verified on fetch |
| that there is a person on the other end | a verdict with evidence, where "we could not tell" is not "yes" |
| a share link anyone who sees it can use | an invitation addressed to one person, for one gate, revocable |
| that the box is what you left it as | an immutable image you built, with atomic rollback |
| that the restore worked | a restore that fully lands or does not land at all |
| a SaaS in the middle of your agents | findings, alerts and coordination over your own transport |
| a mailbox somebody else can read | mail your agents send and receive over your own server |
| one vendor's idea of the web | results from whichever providers you configured |
| that the page said what you were told | the render, the DOM and the requests it made |
| a vendor's quantisation defaults | sub-byte KV cache kernels you can benchmark yourself |
| a pile of scripts nobody has numbered | numbered, discoverable automation with declarative playbooks |
| what a page tells your browser to do | a federated search and desktop bridge you host |
| **a first-plausible diagnosis** | **ranked candidates, each with a test** |

[Full list](https://github.com/Aitherium/awdk#the-aw-family)

---

## License

Apache 2.0. See LICENSE file.
