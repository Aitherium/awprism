"""A diagnostic strategy for Python tracebacks and pytest failure output.

The generic strategies only see words ("timeout", "403"). A traceback carries
far more: the exception class, its message, and the innermost frame. This
strategy parses those three and turns them into hypotheses whose falsifier
names the exact file, line, module or attribute to look at -- the observation
that settles the question, not "check the logs".

Stdlib only; parsing never raises (a strategy that throws is swallowed by the
registry and silently contributes nothing, which reads as "no idea").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from awprism.models import Hypothesis

# `File "path", line N, in func` -- CPython's frame line.
_FRAME = re.compile(r'File "([^"]+)", line (\d+)(?:, in (\S+))?')
# pytest's short location line: `path/to/test_x.py:42: AssertionError`
_PYTEST_LOC = re.compile(r"^((?:[A-Za-z]:)?[^\s:][^:\n]*\.py):(\d+):\s+(\w+)?", re.M)
# Chained exceptions: the FIRST block is the root cause, later ones its consequences.
_CHAIN = re.compile(
    r"^(?:The above exception was the direct cause of the following exception"
    r"|During handling of the above exception, another exception occurred):?\s*$",
    re.M,
)
# The exception line. pytest prefixes it with `E   `; CPython does not.
_EXC = re.compile(
    r"^(?:E\s+)?((?:[A-Za-z_][\w]*\.)*[A-Z]\w*(?:Error|Exception|Exit|Interrupt|Failed|Timeout)"
    r"|AssertionError|StopIteration|KeyboardInterrupt)(?::\s*(.*))?$",
    re.M,
)
_MISSING_MODULE = re.compile(r"No module named '([^']+)'")
_CANNOT_IMPORT = re.compile(r"cannot import name '([^']+)' from '([^']+)'")
_NO_ATTR = re.compile(r"'([^']+)' object has no attribute '([^']+)'")
_MODULE_NO_ATTR = re.compile(r"module '([^']+)' has no attribute '([^']+)'")


@dataclass
class ParsedTraceback:
    """What a traceback says, reduced to the parts that pick a hypothesis."""

    exc_type: str = ""
    message: str = ""
    file: str = ""
    line: int = 0
    func: str = ""
    chained: bool = False

    @property
    def location(self) -> str:
        if not self.file:
            return ""
        return f"{self.file}:{self.line}" + (f" (in {self.func})" if self.func else "")

    def to_dict(self) -> dict:
        return {
            "exception": self.exc_type,
            "message": self.message,
            "location": self.location,
            "root_of_chain": self.chained,
        }


def looks_like_traceback(text: str) -> bool:
    """True for CPython tracebacks and pytest failure blocks (case-insensitive input)."""
    low = text.lower()
    if "traceback (most recent call last)" in low:
        return True
    if "short test summary info" in low or re.search(r"^e\s{2,}\w", low, re.M):
        return True
    # The registry lower-cases the symptom before asking, so match case-free here.
    return bool(re.search(r"^(?:e\s+)?[a-z_][\w.]*(?:error|exception)(?::|$)", low, re.M))


def parse(text: str) -> ParsedTraceback:
    """Pull the root exception and its innermost frame out of `text`.

    Unchained: the last exception. Chained (`raise ... from`, or an error while
    handling another): the FIRST block, because everything after it is a
    consequence -- diagnosing the wrapper sends the reader after the wrong fix.
    """
    out = ParsedTraceback()
    try:
        chain = _CHAIN.search(text)
        if chain:
            out.chained = True
            text = text[: chain.start()]
        excs = list(_EXC.finditer(text))
        if excs:
            last = excs[-1]
            out.exc_type = last.group(1).rsplit(".", 1)[-1]
            out.message = (last.group(2) or "").strip()
        frames = list(_FRAME.finditer(text))
        if frames:
            f = frames[-1]
            out.file, out.line, out.func = f.group(1), int(f.group(2)), f.group(3) or ""
        else:
            locs = list(_PYTEST_LOC.finditer(text))
            if locs:
                loc = locs[-1]
                out.file, out.line = loc.group(1), int(loc.group(2))
                if not out.exc_type and loc.group(3):
                    out.exc_type = loc.group(3)
    except Exception:  # pragma: no cover - the contract is "never raise"
        return ParsedTraceback()
    return out


def _h(claim: str, score: float, falsifier: str, rationale: str, ev: str) -> Hypothesis:
    return Hypothesis(
        claim=claim, score=score, falsifier=falsifier, rationale=rationale,
        evidence_for=[ev] if ev else [],
    )


def hypotheses(symptom: str, context: str) -> list[Hypothesis]:
    """Hypotheses specific to the exception class, each naming its confirming check."""
    tb = parse(symptom)
    exc, msg = tb.exc_type, tb.message
    where = tb.location or "the innermost frame of the traceback"
    ev = f"{exc}: {msg}".strip(": ") if exc else ""
    out: list[Hypothesis] = []

    m = _MISSING_MODULE.search(msg) if exc in ("ModuleNotFoundError", "ImportError") else None
    ci = _CANNOT_IMPORT.search(msg) if exc == "ImportError" else None
    if m:
        mod = m.group(1)
        top, leaf = mod.split(".")[0], mod.split(".")[-1]
        out += [
            _h(f"The package providing '{top}' is not installed in the interpreter that ran this",
               0.85,
               f"Run `python -c \"import {mod}\"` with the SAME interpreter/venv that failed "
               f"(and `pip show {top}`); success means the failing run used another interpreter",
               "ModuleNotFoundError nearly always means the running interpreter lacks the "
               "distribution, most often a different venv than the one it was installed into.",
               ev),
            _h(f"'{mod}' exists in the source tree but is not on sys.path for this run",
               0.55,
               "Print sys.path from the failing entry point (or run from the repo root / with "
               "the package installed -e) and check the parent directory of the module is listed",
               "Local packages import in one cwd and not another; tests run from a different "
               "rootdir hit this.", ev),
            _h(f"'{mod}' was renamed, moved or deleted and the import at {where} is stale",
               0.4,
               f"Search the tree for a file named like '{leaf}' (`rg --files -g '*{leaf}*'`) "
               f"and `git log --diff-filter=DR -- '*{leaf}*'` for a rename or deletion",
               "A missing module after a refactor points at the importer, not the environment.",
               ev),
        ]
    elif ci:
        name, src = ci.group(1), ci.group(2)
        out += [
            _h(f"The installed '{src}' is a different version that has no '{name}'",
               0.8,
               f"`pip show {src.split('.')[0]}` for the installed version, then "
               f"`python -c \"import {src}; print({src}.__file__)\"` and grep that file "
               f"for '{name}'; absent there = version mismatch",
               "'cannot import name' with the module found means the module is the wrong "
               "version or the wrong copy (a shadowing file/editable install).", ev),
            _h(f"'{name}' was renamed or removed from '{src}' and the import at {where} is stale",
               0.6,
               f"`rg -n \"(def|class) {name}\\b|^{name} =\"` inside the package that defines "
               f"'{src}'",
               "API drift between the caller and the module it imports.", ev),
            _h(f"A circular import leaves '{src}' half-initialised when '{name}' is requested",
               0.35,
               f"Import '{src}' alone in a fresh interpreter; if that works but the failing "
               "import chain does not, the cycle is in the chain",
               "Partially initialised modules raise exactly this message.", ev),
        ]
    elif exc == "AttributeError":
        na = _NO_ATTR.search(msg) or _MODULE_NO_ATTR.search(msg)
        typ, attr = (na.group(1), na.group(2)) if na else ("the object", "the attribute")
        if typ == "NoneType":
            out.append(_h(
                f"A call that returns None on failure fed None into '.{attr}' at {where}",
                0.8,
                f"Inspect the value one line before {where}: find which call produced it and "
                "what it returns on its failure path",
                "'NoneType' has no attribute is almost always an unchecked failure return.", ev))
        out += [
            _h(f"The API of {typ} changed: '{attr}' does not exist in the installed version",
               0.65,
               f"`python -c \"print(dir(<{typ}>))\"` against the installed package, and compare "
               "the version pinned where the code was written",
               "Library upgrades rename/remove attributes; the traceback is the first sign.", ev),
            _h(f"A mock/fake stands in for {typ} and does not define '{attr}'",
               0.4,
               "Check whether the test patches this object (grep the test for patch/Mock on "
               "the same name) and whether the patch targets the name actually used",
               "Mocks patched on the wrong name look like a broken real object.", ev),
        ]
    elif exc == "AssertionError":
        out += [
            _h(f"A real regression: the code under test changed behaviour and the assertion at "
               f"{where} caught it", 0.7,
               "Run the same test against the last known-good commit of the code under test; "
               "a pass there and a fail here confirms a regression",
               "An assertion is the test doing its job until shown otherwise.", ev),
            _h("The test's expectation is stale: behaviour changed on purpose and the test "
               "was not updated", 0.5,
               f"Read the assertion at {where} and the commit that last changed the code path "
               "it covers; an intentional change in that commit confirms it",
               "Intended changes break old expectations as often as bugs do.", ev),
            _h("The test is order- or environment-dependent (shared state, time, network)",
               0.35,
               "Run the single failing test alone (`pytest <nodeid> -p no:randomly`) three "
               "times; a pass in isolation confirms a dependency on other tests",
               "Flaky failures pass in isolation and fail in the suite.", ev),
        ]
    elif exc in ("FileNotFoundError", "NotADirectoryError", "IsADirectoryError"):
        out += [
            _h("The path is relative and the process ran from a different working directory",
               0.75,
               f"Print os.getcwd() and the resolved absolute path just before {where}",
               "Relative paths resolve against the cwd, which differs between CLI, IDE and CI.",
               ev),
            _h("The file genuinely does not exist yet (not generated, not checked out, "
               "gitignored)", 0.6,
               "`ls` the exact path from the message; check .gitignore and the step that "
               "should produce it", "Build artifacts and fixtures are often missing on a "
               "clean checkout.", ev),
        ]
    elif exc == "KeyError":
        out += [
            _h(f"The input/config lacks the key {msg or '(see message)'}", 0.7,
               f"Print the keys of the mapping indexed at {where}",
               "KeyError names the missing key; the question is only which mapping.", ev),
            _h("The producer of that mapping changed its schema", 0.45,
               "Compare the producer's current output to the shape the consumer expects "
               "(one real sample)", "Schema drift between writer and reader.", ev),
        ]
    elif exc == "TypeError":
        out += [
            _h(f"A function's signature changed and the call at {where} passes the old "
               "arguments", 0.65,
               "`python -c \"import inspect, <mod>; print(inspect.signature(<mod>.<fn>))\"` "
               "for the callee named in the message",
               "'unexpected keyword' / 'missing positional' is signature drift.", ev),
            _h("A value of the wrong type (None, str vs bytes, sync vs async) reached the call",
               0.5, f"Log type(x) for each argument at {where}",
               "Type errors usually originate one call upstream of where they surface.", ev),
        ]
    elif exc in ("ConnectionRefusedError", "ConnectionError", "ConnectError",
                 "ConnectionResetError", "RemoteDisconnected"):
        out += [
            _h("Nothing is listening at the target host:port (service down or wrong port)",
               0.75, "Probe the exact URL from the failing config with curl -v from the same "
               "host/container", "Refused = no listener; reset = listener that hung up.", ev),
            _h("The client dials the wrong scheme or address (http into a TLS port, "
               "localhost resolving to ::1)", 0.5,
               "Retry with https:// and with 127.0.0.1 instead of localhost; a success on either "
               "confirms", "A TLS port closes a plaintext socket; ::1 refuses where 127.0.0.1 "
               "listens.", ev),
        ]
    elif exc == "PermissionError":
        out.append(_h(
            "The process user cannot read/write the path (ownership, mode, or a lock held by "
            "another process)", 0.75,
            "`ls -l` the path and compare to `id` of the failing process; on Windows check "
            "for a process holding the file open", "Permission errors are rarely wrong.", ev))

    # Always: the exception is real but originates upstream of where it surfaced.
    if exc:
        out.append(_h(
            f"The {exc} at {where} is a downstream symptom of an earlier failure in the same "
            "run", 0.3,
            "Scroll to the FIRST error/warning in the full output (not the last); if an earlier "
            "one exists, diagnose that instead",
            "The last traceback is often the second failure.", ev))
    else:
        out.append(_h(
            f"The failure originates at {where}", 0.5,
            f"Open {where} and read the statement that raised with the variable values printed",
            "No exception class could be parsed; start at the innermost frame.", ev))
    return out
