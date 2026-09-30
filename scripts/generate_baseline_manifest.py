"""Release tooling: generate the web-pentest baseline manifest.

Records the committed baseline, workspace status, interpreter versions,
test commands, known skips, and SHA-256 digests of the proof-contract
sources, then self-hashes the manifest. Paths default repo-relative so
the tool runs on any checkout; pass --root/--out to override.

NOTE: the handoff is deliberately EXCLUDED from source_digests. It
references the manifest by sha, so including it would make
manifest<->handoff freshness unachievable (each edit invalidates the
other). Verify with scripts/check_baseline_manifest.py.

Usage:
    python scripts/generate_baseline_manifest.py [--root .] [--out tmp/p1-target/evidence/baseline-manifest.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

KEY_FILES = [
    "plugins/_web_pentest/helpers/portfolio.py",
    "plugins/_web_pentest/helpers/service.py",
    "plugins/_web_pentest/helpers/closure.py",
    "plugins/_web_pentest/helpers/benchmark.py",
]

SCHEMA = "agent-zero-web-pentest-baseline-manifest/v1"


def run(args, cwd, timeout=240):
    out = subprocess.run(args, capture_output=True, text=True,
                         timeout=timeout, cwd=str(cwd))
    return (out.stdout.strip() + out.stderr.strip()).strip()


def build(root: Path, framework_python: str, capture_python: str) -> dict:
    manifest: dict = {
        "schema": SCHEMA,
        "committed_baseline": {
            "commit": "29ff9f379a3daf99c8daa3cb0dd76e63082d98f4",
            "subject": "fix(web-pentest): fence managed execution and proxy egress",
            "branch": "feat/web-pentest-engine",
        },
        "workspace": {
            "git_log": run(["git", "log", "-1", "--format=%H %s"], root),
            "git_status": run(["git", "status", "--short"], root),
        },
        "interpreters": {
            "framework_python": run([framework_python, "--version"], root),
            "pytest": run([framework_python, "-m", "pytest", "--version"], root),
            "capture_python": run([capture_python, "--version"], root),
            "mitmproxy": run([capture_python, "-c",
                              "from mitmproxy.version import VERSION; print(VERSION)"],
                             root),
        },
        "test_commands": [
            "PYTHONASYNCIODEBUG=1 <framework-python> -m pytest tests/test_web_pentest*.py -q",
            "<framework-python> -m pytest tests/test_browser_agent_regressions.py "
            "tests/test_parallel_tool.py tests/test_parallel_tool_args.py "
            "tests/test_parallel_code_lifetime.py tests/test_persist_chat_log_ids.py "
            "tests/test_persist_chat_deletion_guards.py tests/test_http_auth_csrf.py "
            "tests/test_ws_csrf.py -q",
        ],
        "known_skips": [
            "capture normalization (mitmproxy lives in separate env, not framework interpreter)",
            "browser-dependent tests skip when Patchright/Chromium unavailable",
            "posix-only worker socket tests skip on non-posix",
        ],
        "notes": [
            "Workspace (not baseline) is the tested source; recount git status before citing.",
            "Historical totals are implementation evidence, not acceptance.",
        ],
    }
    digests = {}
    for rel in KEY_FILES:
        digests[rel] = hashlib.sha256((root / rel).read_bytes()).hexdigest()
    manifest["source_digests"] = digests
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "manifest_sha256"},
                   sort_keys=True).encode()).hexdigest()
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                        help="repository root")
    parser.add_argument("--out", default=None,
                        help="manifest output path (default: <root>/tmp/p1-target/evidence/baseline-manifest.json)")
    parser.add_argument("--framework-python", default=sys.executable,
                        help="framework interpreter to record and probe")
    parser.add_argument("--capture-python", default=None,
                        help="capture interpreter to probe (skipped with a note when absent)")
    args = parser.parse_args(argv)
    root = Path(args.root)
    out_path = Path(args.out) if args.out else root / "tmp" / "p1-target" / "evidence" / "baseline-manifest.json"
    capture = args.capture_python
    if capture is None:
        manifest = build(root, args.framework_python, sys.executable)
        manifest["interpreters"]["capture_python"] = "not configured (pass --capture-python)"
        manifest["interpreters"]["mitmproxy"] = "not probed (pass --capture-python)"
        manifest["manifest_sha256"] = hashlib.sha256(
            json.dumps({k: v for k, v in manifest.items() if k != "manifest_sha256"},
                       sort_keys=True).encode()).hexdigest()
    else:
        manifest = build(root, args.framework_python, capture)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(out_path), "manifest_sha256": manifest["manifest_sha256"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
