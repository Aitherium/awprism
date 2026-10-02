"""A valid-JSON line that is not an object must not kill the stdio server."""
import io
import json
import sys

from awprism import mcp_server


def test_non_object_line_then_ping(monkeypatch):
    lines = '[1,2]\n{"jsonrpc":"2.0","id":7,"method":"ping"}\n'
    monkeypatch.setattr(sys, "stdin", io.StringIO(lines))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert mcp_server.main([]) == 0
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    assert replies[0]["error"]["code"] == -32600
    assert replies[1]["id"] == 7 and "result" in replies[1]


def _serve(monkeypatch, lines):
    monkeypatch.setattr(sys, "stdin", io.StringIO(lines))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert mcp_server.main([]) == 0
    return [json.loads(x) for x in out.getvalue().splitlines()]


def test_json_null_as_first_line_is_an_invalid_request_not_a_crash(monkeypatch):
    replies = _serve(monkeypatch, 'null\n{"jsonrpc":"2.0","id":7,"method":"ping"}\n')
    assert replies[0]["error"]["code"] == -32600 and replies[0]["id"] is None
    assert replies[1]["id"] == 7 and "result" in replies[1]
    assert len(replies) == 2


def test_json_null_after_a_request_does_not_resend_the_previous_reply(monkeypatch):
    replies = _serve(monkeypatch, '{"jsonrpc":"2.0","id":7,"method":"ping"}\nnull\n')
    assert [r.get("id") for r in replies] == [7, None]
    assert replies[1]["error"]["code"] == -32600


def test_notification_after_a_request_writes_nothing_extra(monkeypatch):
    lines = ('{"jsonrpc":"2.0","id":7,"method":"ping"}\n'
             '{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
    replies = _serve(monkeypatch, lines)
    assert [r.get("id") for r in replies] == [7]


def test_non_ascii_failure_text_is_read_as_utf8_over_a_real_pipe():
    import os
    import subprocess

    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "diagnose", "arguments": {"failure_text": "KeyError: 'région Á'"}}}
    raw = json.dumps(msg, ensure_ascii=False).encode("utf-8") + b"\n"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    proc = subprocess.run([sys.executable, "-m", "awprism.cli", "mcp"], input=raw,
                          capture_output=True, timeout=30, env=env)
    assert proc.returncode == 0, proc.stderr
    reply = json.loads(proc.stdout.decode("utf-8").splitlines()[0])
    body = json.loads(reply["result"]["content"][0]["text"])
    assert body["failure"] == "KeyError: 'région Á'"
