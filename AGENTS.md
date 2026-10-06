# awprism for agents

Read this if you are an agent (or a human) editing this package. Short on
purpose: the commands, the traps that cost a session, and where the rest lives.
Nothing here is read at runtime — it is for you.

## What this is

PyPI distribution **`awprism`** (version in `pyproject.toml`), import package
`awprism`, Python >= 3.10. Turn a failure into ranked hypotheses — and say what
would confirm each one. A reasoning brick, exposed over MCP.

This repository is a **synced mirror** of the AitherOS monorepo (lane
`.github/workflows/sync-awprism.yml`). Hand edits made here are overwritten on
the next sync — change the source and let the lane publish.

## Build, test, verify

```bash
python -m pytest tests -q        # the suite: 55 tests, green at v0.1.1
pip install -e .                 # editable install for developing against it
```

The suite was run from a source checkout with no prior install. The publish
lane (`publish-brick.yml`) additionally builds the wheel, installs it and
imports it — a tree that tests green can still ship a broken wheel.

## Rules that keep this useful

- **A hypothesis without a confirming test is a guess.** The scorer
  (`test_scorer.py`) ranks hypotheses by what would CONFIRM them; never let a
  ranking change land without it, or the ordering silently becomes vibes.
- **The MCP server is a surface people depend on.** `test_mcp_server.py` and
  `test_stdio_robust.py` exist because a stdio server that crashes on a bad
  frame reads as a dead tool with no error — every new frame shape gets its
  robustness case.
- **Bad input is could-not-judge, never a ranking.** Refusing loudly beats
  emitting a confident top-3 over garbage.
- **The registry drives the public surface.** This repo's README header,
  `llms.txt` and `aither-manifest.json` are generated from the ecosystem
  registry (one yaml in the AitherOS monorepo) and rewritten on every sync.
  Change the registry; do not hand-edit the generated blocks.

## Read next

- `llms.txt` — the install/use card written for an agent to execute
- `README.md` — the human front door
- `docs/` — the generated docs site source
