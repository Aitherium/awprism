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

<!-- aither-ecosystem:start GENERATED from the ecosystem registry. Edits here are overwritten; change the registry instead. -->

## The aw family

Standalone tools that share one idea: **replace something you would otherwise have to _trust_ with something you can _check_.**

Each installs on its own, works offline, and needs no account.

| | instead of trusting | you check |
|---|---|---|
| [awdk](https://github.com/Aitherium/awdk) | a framework's idea of how your agents should run | one loop you can read, pointed at a backend you already pay for |
| [awskills](https://github.com/Aitherium/awskills) | that an agent knows your procedure | the procedure written down, versioned, and loadable by any agent |
| [awm](https://github.com/Aitherium/awm) | that memory stayed in its lane | tenant:user:project scopes, so a write cannot cross a boundary |
| [awnode](https://github.com/Aitherium/awnode) | a vendor's cloud with every prompt | a local gateway routing to backends you chose |
| [awgraph](https://github.com/Aitherium/awgraph) | that grep found everything | an AST + tree-sitter call graph an agent can traverse |
| [awgit](https://github.com/Aitherium/awgit) | that no one else is editing this file | a lease, refused at commit time if you do not hold it |
| [awseal](https://github.com/Aitherium/awseal) | that the artifact came from who you think | an Ed25519 seal — the key that verifies is not the key that forges |
| [awshare](https://github.com/Aitherium/awshare) | that the download is intact | content-addressed bundles, verified on fetch |
| [awnest](https://github.com/Aitherium/awnest) | that there is a person on the other end | a verdict with evidence, where "we could not tell" is not "yes" |
| [awnboard](https://github.com/Aitherium/awnboard) | a share link anyone who sees it can use | an invitation addressed to one person, for one gate, revocable |
| [awnix](https://github.com/Aitherium/awnix) | that the box is what you left it as | an immutable image you built, with atomic rollback |
| [awrecover](https://github.com/Aitherium/awrecover) | that the restore worked | a restore that fully lands or does not land at all |
| [awrelay](https://github.com/Aitherium/awrelay) | a SaaS in the middle of your agents | findings, alerts and coordination over your own transport |
| [awmail](https://github.com/Aitherium/awmail) | a mailbox somebody else can read | mail your agents send and receive over your own server |
| [awfind](https://github.com/Aitherium/awfind) | one vendor's idea of the web | results from whichever providers you configured |
| [awbrowse](https://github.com/Aitherium/awbrowse) | that the page said what you were told | the render, the DOM and the requests it made |
| [aitherkvcache](https://github.com/Aitherium/aitherkvcache) | a vendor's quantisation defaults | sub-byte KV cache kernels you can benchmark yourself |
| [AitherZero](https://github.com/Aitherium/AitherZero) | a pile of scripts nobody has numbered | numbered, discoverable automation with declarative playbooks |
| [AitherConnect](https://github.com/Aitherium/AitherConnect) | what a page tells your browser to do | a federated search and desktop bridge you host |
| [awreason](https://github.com/Aitherium/awreason) | a confident paragraph | the phases it went through, and every tool call it made to get there |
| [awrecurse](https://github.com/Aitherium/awrecurse) | that everything you pasted in was actually read | which slices it opened, and what it concluded from each |
| **awprism** _(you are here)_ | the first explanation that fits | the ranked alternatives, and the observation that separates them |
| [awrepl](https://github.com/Aitherium/awrepl) | what the agent believes the value is | the value, printed from the live session |
| [awresearch](https://github.com/Aitherium/awresearch) | a summary of pages nobody opened | every claim against the source it came from |
| [awkno](https://github.com/Aitherium/awkno) | that the docs site is up, or that you remember the family | the whole ecosystem in your terminal, with no network at all |

[**awnix**](https://github.com/Aitherium/awnix) is the ground floor — A Linux you can hand to an agent — immutable base, capabilities included.

## The Aitherium ecosystem

Every repository here is public. Each publishes an `aither-manifest.json` beside its page, so any surface can read every sibling's — the network is browsable from any node in it.

| repo | what it is | pages |
|---|---|---|
| [awdk](https://github.com/Aitherium/awdk) | Build AI agent fleets — 3 lines, any backend, local or cloud | [docs](https://aitherium.github.io/awdk/) |
| [awskills](https://github.com/Aitherium/awskills) | Portable agent skills — self-contained procedures an agent loads on demand | [docs](https://aitherium.github.io/awskills/) |
| [awm](https://github.com/Aitherium/awm) | A portable, scoped agent memory | [docs](https://aitherium.github.io/awm/) |
| [awnode](https://github.com/Aitherium/awnode) | A lightweight local gateway — bridges your apps to the AI backends you chose | [docs](https://aitherium.github.io/awnode/) |
| [awrun](https://github.com/Aitherium/awrun) | A priority-aware queue and dispatcher for agentic runs and ad-hoc CI builds | [docs](https://aitherium.github.io/awrun/) |
| [awgraph](https://github.com/Aitherium/awgraph) | A semantic code graph for agents — AST + tree-sitter, call graphs | [docs](https://aitherium.github.io/awgraph/) |
| [awgit](https://github.com/Aitherium/awgit) | Semantic version control on top of git — edit-ops and leases | [docs](https://aitherium.github.io/awgit/) |
| [awseal](https://github.com/Aitherium/awseal) | Sign an artifact so a stranger can verify it | [docs](https://aitherium.github.io/awseal/) |
| [awshare](https://github.com/Aitherium/awshare) | Publish an artifact and fetch it back verified | [docs](https://aitherium.github.io/awshare/) |
| [awnest](https://github.com/Aitherium/awnest) | Prove there is a human before you let them into the nest | [docs](https://aitherium.github.io/awnest/) |
| [awnboard](https://github.com/Aitherium/awnboard) | A front gate you can put in front of anything, and hand someone the key to | [docs](https://aitherium.github.io/awnboard/) |
| [awnix](https://github.com/Aitherium/awnix) | A Linux you can hand to an agent — immutable base, capabilities included | [docs](https://aitherium.github.io/awnix/) |
| [awrecover](https://github.com/Aitherium/awrecover) | Labelled snapshots with an all-or-nothing restore | [docs](https://aitherium.github.io/awrecover/) |
| [awrelay](https://github.com/Aitherium/awrelay) | Portable agent messaging — findings, alerts, coordination | [docs](https://aitherium.github.io/awrelay/) |
| [awmail](https://github.com/Aitherium/awmail) | Give an agent an email address — send, and actually receive | [docs](https://aitherium.github.io/awmail/) |
| [awfind](https://github.com/Aitherium/awfind) | A portable search client — query, results, ranking | [docs](https://aitherium.github.io/awfind/) |
| [awbrowse](https://github.com/Aitherium/awbrowse) | A portable browser client — navigate, console, network, DOM, screenshot | [docs](https://aitherium.github.io/awbrowse/) |
| [awknowledge](https://github.com/Aitherium/awknowledge) | How to run a coding agent so the result survives — the laws, with evidence | [docs](https://aitherium.github.io/awknowledge/) |
| [aitherkvcache](https://github.com/Aitherium/aitherkvcache) | Near-optimal KV cache quantization for LLM inference — sub-byte compression | [docs](https://aitherium.github.io/aitherkvcache/) |
| [AitherZero](https://github.com/Aitherium/AitherZero) | PowerShell 7+ automation framework — numbered, self-describing scripts | [docs](https://aitherium.github.io/AitherZero/) |
| [AitherConnect](https://github.com/Aitherium/AitherConnect) | Browser extension — federated AI search, page context, and the Living OS overlay | [docs](https://aitherium.github.io/AitherConnect/) |
| [awreason](https://github.com/Aitherium/awreason) | A portable reasoning client — sessions, phases, thoughts, and the chain that produced the answer | [docs](https://aitherium.github.io/awreason/) |
| [awrecurse](https://github.com/Aitherium/awrecurse) | Answer a question over a context far larger than the window — recursively, with the trace kept | [docs](https://aitherium.github.io/awrecurse/) |
| **awprism** _(you are here)_ | Turn a failure into ranked hypotheses — and say what would confirm each one | [docs](https://aitherium.github.io/awprism/) |
| [awrepl](https://github.com/Aitherium/awrepl) | A REPL an agent can actually use — state that survives between turns | [docs](https://aitherium.github.io/awrepl/) |
| [awresearch](https://github.com/Aitherium/awresearch) | Ask a research question, get a cited report you can check | [docs](https://aitherium.github.io/awresearch/) |
| [awkno](https://github.com/Aitherium/awkno) | The man page for the Aither World — every brick, stack and law, offline | [docs](https://aitherium.github.io/awkno/) |

<div id="aither-constellation" data-self="awprism"></div>
<script src="aither-constellation.js"></script>

<!-- aither-ecosystem:end -->
## License

Apache 2.0. See LICENSE file.
