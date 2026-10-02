"""awprism as an MCP server (stdio, stdlib only).

    awprism mcp

    {"mcpServers": {"awprism": {"command": "awprism", "args": ["mcp"]}}}

Two tools, both read-only:

  diagnose(failure_text, context_paths?, k?)  ranked candidate causes, each with
                                              the ONE observation that confirms it
  strategies()                                which failure classes are recognised

WHY STDLIB
----------
awprism has no dependencies and this keeps it that way: the server is a
newline-delimited JSON-RPC loop, so it starts in well under a second, works on
any Python >= 3.10, and never breaks because the `mcp` SDK changed its surface
between major versions.

READ-ONLY BY DESIGN
-------------------
`context_paths` are READ, never written, and bounded: at most MAX_FILES regular
files, the LAST MAX_BYTES of each (the tail of a log is where the failure is).
A path that is missing, a directory, or unreadable is reported under
`context_skipped` with the reason, never silently dropped -- a caller who
believes its context was used when it was not will trust the ranking too much.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

PROTOCOL = "2024-11-05"
MAX_FILES = 8
MAX_BYTES = 64 * 1024
MAX_FAILURE_CHARS = 40_000

_DIAGNOSE = (
    "Hand it a failure -- a pytest traceback, a stack trace, an error log line, or a plain "
    "description like 'the API returns 500 only on the replica' -- and get back ranked "
    "candidate causes. Each cause carries `confirm_by`: the single observation or command "
    "that would confirm or rule it out, so you test the top cause instead of guessing. "
    "Python tracebacks are parsed (exception class, message, innermost file:line) and get "
    "exception-specific causes; other text gets pattern-based causes (timeout, auth, "
    "resource exhaustion) plus generic ones. Pass `context_paths` (log files, the failing "
    "test, a config) to include them as context; they are read, never written. Heuristic, "
    "offline, no model call: treat `confidence` as a ranking, not a probability.")
_STRATEGIES = ("List the failure classes awprism recognises (name + description). Use it "
               "to see why a diagnosis came back generic: no strategy matched the text.")

TOOLS: List[Dict[str, Any]] = [
    {"name": "diagnose", "description": _DIAGNOSE,
     "inputSchema": {"type": "object", "required": ["failure_text"], "properties": {
         "failure_text": {"type": "string",
                          "description": "The failure verbatim: traceback, error output, or a "
                                         "one-line description of the symptom."},
         "context_paths": {"type": "array", "items": {"type": "string"},
                           "description": f"Optional files to read as context (max "
                                          f"{MAX_FILES}, last {MAX_BYTES // 1024} KiB each). "
                                          "Relative paths resolve against the server's cwd."},
         "k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20,
               "description": "Maximum number of causes to return."}}}},
    {"name": "strategies", "description": _STRATEGIES,
     "inputSchema": {"type": "object", "properties": {}}},
]


def _read_context(paths: Any) -> Tuple[str, List[str], List[Dict[str, str]]]:
    """Read the tail of each context file. Returns (text, read, skipped)."""
    if paths is None:
        return "", [], []
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list):
        raise ValueError("context_paths must be a list of file paths")
    chunks: List[str] = []
    read: List[str] = []
    skipped: List[Dict[str, str]] = []
    for raw in paths:
        p = os.path.abspath(os.path.expanduser(str(raw)))
        if len(read) >= MAX_FILES:
            skipped.append({"path": str(raw), "reason": f"over the {MAX_FILES}-file limit"})
            continue
        if not os.path.isfile(p):
            why = "is a directory" if os.path.isdir(p) else "not found"
            skipped.append({"path": str(raw), "reason": why})
            continue
        try:
            size = os.path.getsize(p)
            with open(p, "rb") as fh:
                if size > MAX_BYTES:
                    fh.seek(size - MAX_BYTES)
                data = fh.read(MAX_BYTES).decode("utf-8", errors="replace")
        except OSError as exc:
            skipped.append({"path": str(raw), "reason": f"unreadable: {exc.strerror or exc}"})
            continue
        chunks.append(f"--- {p} ---\n{data}")
        read.append(p)
    return "\n".join(chunks), read, skipped


def diagnose(failure_text: Any, context_paths: Any = None, k: Any = 5) -> Dict[str, Any]:
    """The `diagnose` tool. Raises ValueError on a malformed request."""
    from awprism import tracebacks
    from awprism.prism import Prism

    text = str(failure_text or "").strip()
    if not text:
        raise ValueError("failure_text must not be empty")
    try:
        k_int = max(1, min(20, int(k if k is not None else 5)))
    except (TypeError, ValueError):
        raise ValueError("k must be an integer") from None
    truncated = len(text) > MAX_FAILURE_CHARS
    if truncated:  # keep the tail: the final exception and innermost frame live there
        text = text[-MAX_FAILURE_CHARS:]
    ctx, read, skipped = _read_context(context_paths)

    prism = Prism()
    matched = [s.name for s in prism.registry.find_applicable(text)]
    diag = prism.diagnose(text, context=ctx, k=k_int)
    parsed = tracebacks.parse(text) if "python_traceback" in matched else None

    causes = []
    for i, h in enumerate(diag.hypotheses, 1):
        causes.append({
            "rank": i,
            "cause": h.claim,
            "confidence": round(h.score, 2),
            "confirm_by": h.falsifier,
            "why": h.rationale,
            "evidence_for": list(h.evidence_for),
        })
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")[:200]
    out: Dict[str, Any] = {
        "failure": first_line,
        "strategies_matched": matched,
        "causes": causes,
        "context_read": read,
        "context_skipped": skipped,
    }
    if parsed is not None:
        out["parsed"] = parsed.to_dict()
    if truncated:
        out["note"] = f"failure_text truncated to its last {MAX_FAILURE_CHARS} characters"
    return out


def strategies() -> Dict[str, Any]:
    from awprism.registry import StrategyRegistry

    reg = StrategyRegistry()
    return {"strategies": [{"name": s.name, "description": s.description}
                           for s in reg.strategies.values()]}


def call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch one tool call. Raises ValueError for an unknown tool or bad args."""
    if name == "diagnose":
        return diagnose(args.get("failure_text"), args.get("context_paths"), args.get("k", 5))
    if name == "strategies":
        return strategies()
    raise ValueError(f"unknown tool {name!r}")


def handle(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One JSON-RPC message in, one reply out; None for a notification."""
    mid, method = msg.get("id"), msg.get("method", "")
    if mid is None:
        return None
    if method == "initialize":
        from awprism import __version__
        result: Dict[str, Any] = {
            "protocolVersion": (msg.get("params") or {}).get("protocolVersion") or PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "awprism", "version": __version__},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = msg.get("params") or {}
        try:
            text = json.dumps(call(str(p.get("name")), p.get("arguments") or {}))
            err = False
        except (ValueError, TypeError) as exc:
            text, err = str(exc), True
        result = {"content": [{"type": "text", "text": text}], "isError": err}
    else:
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": f"no method {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main(argv: Optional[List[str]] = None) -> int:
    """Serve newline-delimited JSON-RPC over stdio until stdin closes."""
    stdin = sys.stdin
    # MCP clients write UTF-8. A Windows console codepage would turn a non-ASCII
    # failure_text into mojibake (and lone surrogates in the reply), so decode as UTF-8.
    reconfigure = getattr(stdin, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")
    for line in stdin:
        if not line.strip():
            continue
        # Reset per line: `null` is valid JSON that parses to None, so None cannot
        # double as the "parse failed" sentinel and a stale reply must never resend.
        reply: Optional[Dict[str, Any]] = None
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": "parse error"}}
        else:
            if not isinstance(msg, dict):
                reply = {"jsonrpc": "2.0", "id": None,
                         "error": {"code": -32600, "message": "invalid request"}}
            else:
                try:
                    reply = handle(msg)
                except Exception as exc:  # one bad call never kills the server
                    err = f"internal error: {type(exc).__name__}"
                    reply = {"jsonrpc": "2.0", "id": msg.get("id"),
                             "error": {"code": -32603, "message": err}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
