"""`awprism mcp` -- the stdio server, its two tools, and the traceback strategy.

The fixture `pytest_chained_importerror.txt` is a REAL captured pytest run
(paths anonymised): a module written for mcp 2.x importing `MCPServer` on a
host with mcp 1.x, re-raised as an install hint. The right answer is the FIRST
exception in the chain, not the wrapper that pytest prints last.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from awprism import mcp_server, tracebacks

FIXTURE = Path(__file__).parent / "fixtures" / "pytest_chained_importerror.txt"


def _rpc(method: str, params: dict | None = None, mid: int = 1) -> dict:
    reply = mcp_server.handle({"jsonrpc": "2.0", "id": mid, "method": method,
                               "params": params or {}})
    assert reply is not None
    return reply


def _call(name: str, args: dict) -> tuple[bool, str]:
    res = _rpc("tools/call", {"name": name, "arguments": args})["result"]
    return res["isError"], res["content"][0]["text"]


def test_tools_list_names_and_schemas():
    tools = {t["name"]: t for t in _rpc("tools/list")["result"]["tools"]}
    assert set(tools) == {"diagnose", "strategies"}
    assert tools["diagnose"]["inputSchema"]["required"] == ["failure_text"]
    assert "confirm_by" in tools["diagnose"]["description"]


def test_initialize_and_notification():
    res = _rpc("initialize", {"protocolVersion": "2025-06-18"})["result"]
    assert res["serverInfo"]["name"] == "awprism"
    assert res["protocolVersion"] == "2025-06-18"
    assert mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert _rpc("no/such")["error"]["code"] == -32601


def test_diagnose_real_chained_pytest_failure_ranks_the_root_cause_first():
    err, text = _call("diagnose", {"failure_text": FIXTURE.read_text(encoding="utf-8")})
    assert not err, text
    out = json.loads(text)
    assert "python_traceback" in out["strategies_matched"]
    parsed = out["parsed"]
    assert parsed["exception"] == "ImportError"
    assert "cannot import name 'MCPServer'" in parsed["message"]  # root, not the wrapper
    assert parsed["root_of_chain"] is True
    assert parsed["location"].endswith("mcp_server.py:90")
    top = out["causes"][0]
    assert top["rank"] == 1
    assert "different version" in top["cause"] and "MCPServer" in top["cause"]
    assert "pip show mcp" in top["confirm_by"]
    assert all(c["confirm_by"].strip() for c in out["causes"])
    confs = [c["confidence"] for c in out["causes"]]
    assert confs == sorted(confs, reverse=True)


def test_diagnose_module_not_found_names_the_module_in_the_check():
    tb = ('Traceback (most recent call last):\n  File "app/run.py", line 7, in <module>\n'
          "    import yaml\nModuleNotFoundError: No module named 'yaml'\n")
    out = mcp_server.diagnose(tb, k=3)
    assert out["parsed"]["location"] == "app/run.py:7 (in <module>)"
    assert out["causes"][0]["confirm_by"].startswith('Run `python -c "import yaml"`')
    assert len(out["causes"]) == 3


def test_diagnose_plain_symptom_falls_back_to_pattern_strategies():
    out = mcp_server.diagnose("the API returns 403 forbidden for the service account")
    assert "auth" in out["strategies_matched"]
    assert "parsed" not in out
    assert len(out["causes"]) >= 2


def test_context_paths_are_read_bounded_and_skips_are_reported(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("x" * (mcp_server.MAX_BYTES + 500), encoding="utf-8")
    out = mcp_server.diagnose("service hung", context_paths=[str(log), str(tmp_path),
                                                              str(tmp_path / "nope.txt")])
    assert out["context_read"] == [str(log.resolve())] or out["context_read"] == [
        str(log.absolute())]
    reasons = sorted(s["reason"] for s in out["context_skipped"])
    assert reasons == ["is a directory", "not found"]
    assert log.read_text(encoding="utf-8").startswith("x")  # read-only: untouched


def test_bad_arguments_are_tool_errors_not_crashes():
    err, text = _call("diagnose", {"failure_text": "   "})
    assert err and "must not be empty" in text
    err, text = _call("diagnose", {"failure_text": "boom", "k": "many"})
    assert err and "k must be an integer" in text
    err, text = _call("diagnose", {"failure_text": "boom", "context_paths": 5})
    assert err and "context_paths" in text
    err, text = _call("nope", {})
    assert err and "unknown tool" in text


def test_strategies_tool_lists_the_traceback_strategy():
    err, text = _call("strategies", {})
    assert not err
    names = [s["name"] for s in json.loads(text)["strategies"]]
    assert "python_traceback" in names and "unknown" in names


@pytest.mark.parametrize("text,expected", [
    ("E       KeyError: 'region'\n\nsrc/cfg.py:12: KeyError\n", ("KeyError", "src/cfg.py:12")),
    ("AttributeError: 'NoneType' object has no attribute 'json'\n", ("AttributeError", "")),
])
def test_parse_pytest_and_bare_lines(text, expected):
    p = tracebacks.parse(text)
    assert (p.exc_type, f"{p.file}:{p.line}" if p.file else "") == expected


def test_none_attribute_ranks_unchecked_failure_first():
    out = mcp_server.diagnose("AttributeError: 'NoneType' object has no attribute 'json'")
    assert "returns None" in out["causes"][0]["cause"]


def test_stdio_server_starts_fast_and_answers_over_a_real_pipe():
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "diagnose",
            "arguments": {"failure_text": FIXTURE.read_text(encoding="utf-8")}}},
    ]
    stdin = "".join(json.dumps(m) + "\n" for m in msgs)
    t0 = time.monotonic()
    proc = subprocess.run([sys.executable, "-m", "awprism.cli", "mcp"], input=stdin,
                          capture_output=True, text=True, encoding="utf-8", timeout=30)
    elapsed = time.monotonic() - t0
    assert proc.returncode == 0, proc.stderr
    replies = [json.loads(ln) for ln in proc.stdout.splitlines() if ln.strip()]
    assert [r["id"] for r in replies] == [1, 2, 3]
    body = json.loads(replies[2]["result"]["content"][0]["text"])
    assert "MCPServer" in body["causes"][0]["cause"]
    assert elapsed < 5.0  # whole round trip incl. interpreter start; startup itself is <1 s


@pytest.mark.parametrize(
    "text, strategy",
    [
        ("connection refused on port 8111 after restart", "connection"),
        ("curl: (6) Could not resolve host: Temporary failure in name resolution", "connection"),
        ("HTTP 502 Bad Gateway from genesis", "upstream_http"),
        ("the API returned 503 Service Unavailable", "upstream_http"),
        ("podman: no container with name aitheros-security-core", "runtime"),
        ("worker exited (137) after the deploy", "runtime"),
    ],
)
def test_fleet_failure_classes_match_a_strategy_not_only_unknown(text, strategy):
    # 2026-10-07: these fleet-incident shapes matched only "unknown", so the v22 pillars
    # builder discarded 384 of ~400 real incidents as matching no diagnose strategy.
    matched = mcp_server.diagnose(failure_text=text, k=3)["strategies_matched"]
    assert strategy in matched, matched


def test_plain_slowness_is_still_timeout_not_connection():
    matched = mcp_server.diagnose(failure_text="the dashboard is slow and hung for a minute", k=3)[
        "strategies_matched"
    ]
    assert "timeout" in matched and "connection" not in matched
