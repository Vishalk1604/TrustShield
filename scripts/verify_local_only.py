#!/usr/bin/env python3
"""Fail loudly if any runtime code makes (or hardcodes) an outbound network call.

This is the machine-checkable proof behind TrustShield's core promise: 100% local, no external
calls at runtime. Every external verification is a local mock. Run it at the end of every phase:

    python scripts/verify_local_only.py        # exit 0 = clean, exit 1 = violations found

What it scans: source files (.py/.js/.jsx/.ts/.tsx), excluding build/vendor dirs.
What it flags:
  1. Network *call* patterns (requests/httpx/urllib/aiohttp/axios/XMLHttpRequest/raw sockets,
     and fetch() to an absolute URL).
  2. Hardcoded external URLs — any http(s)://host where host is not localhost/127.0.0.1/0.0.0.0
     or a known compose service name.

Allowed to contain those (by design): `tests/` (may simulate or guard against network) and
`shared/mocks/` (carries illustrative "this is where the real API would go" comments). This very
script is also exempt from scanning itself.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCAN_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}
EXCLUDE_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build",
    "__pycache__", ".vite", ".pytest_cache", ".mypy_cache", ".idea", ".vscode",
}

# Paths (relative to repo root, POSIX style) exempt from BOTH checks.
# - tests may legitimately reference network APIs to assert they are NOT used.
# - shared/mocks carries the documented "real implementation would call X" comments.
# - this script contains the detection patterns themselves.
EXEMPT_PREFIXES = (
    "tests/",
    "shared/mocks/",
    "scripts/verify_local_only.py",
)

# Hosts that are fine to hardcode (everything is on the laptop).
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "forensics", "risk", "dashboard"}

# (regex, human reason) — these denote an actual outbound call.
CALL_PATTERNS = [
    (re.compile(r"\brequests\.(get|post|put|delete|patch|head|request|Session|session)\b"), "requests network call"),
    (re.compile(r"\bhttpx\.(get|post|put|delete|patch|head|request|stream|Client|AsyncClient)\b"), "httpx network call"),
    (re.compile(r"\burllib\.request\b"), "urllib.request network call"),
    (re.compile(r"\burllib2\b"), "urllib2 network call"),
    (re.compile(r"\baiohttp\b"), "aiohttp network call"),
    (re.compile(r"\bsocket\.create_connection\b"), "raw socket connection"),
    (re.compile(r"\baxios\b"), "axios network call"),
    (re.compile(r"\bXMLHttpRequest\b"), "XMLHttpRequest network call"),
    (re.compile(r"""fetch\(\s*[`'\"]https?://"""), "fetch() to an absolute URL"),
]

URL_PATTERN = re.compile(r"""https?://([^/\s'\"`)\\]+)""")


def _is_exempt(rel_posix: str) -> bool:
    return any(rel_posix == p or rel_posix.startswith(p) for p in EXEMPT_PREFIXES)


def _iter_source_files():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_EXTENSIONS:
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        yield path


def _host_of(url_netloc: str) -> str:
    # strip credentials and port: user:pass@host:port -> host
    netloc = url_netloc.split("@")[-1]
    return netloc.split(":")[0].lower()


def scan() -> list[tuple[str, int, str]]:
    violations: list[tuple[str, int, str]] = []
    for path in _iter_source_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if _is_exempt(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pat, reason in CALL_PATTERNS:
                if pat.search(line):
                    violations.append((rel, lineno, reason))
            for m in URL_PATTERN.finditer(line):
                host = _host_of(m.group(1))
                if host not in ALLOWED_HOSTS:
                    violations.append((rel, lineno, f"hardcoded external URL host '{host}'"))
    return violations


def main() -> int:
    scanned = sum(1 for _ in _iter_source_files())
    violations = scan()
    if violations:
        print("=" * 70)
        print("  LOCAL-ONLY CHECK FAILED - outbound network usage detected:")
        print("=" * 70)
        for rel, lineno, reason in violations:
            print(f"  {rel}:{lineno}  ->  {reason}")
        print("-" * 70)
        print(f"  {len(violations)} violation(s). TrustShield must make NO external calls at runtime.")
        print("  If this is a documented mock/test, move it under shared/mocks/ or tests/.")
        return 1
    print(f"OK - local-only check passed. Scanned {scanned} source files; no outbound network usage.")
    print("     (external verification is mocked in shared/mocks; all hosts are localhost.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
