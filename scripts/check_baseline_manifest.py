"""Release gate: verify a baseline manifest against the working tree.

Recomputes every recorded source digest plus the manifest hash itself.
Any drift prints STALE_* lines and exits 1, so CI cannot mistake a stale
manifest for provenance. Exits 0 with ALL_MATCH only when everything
recomputes exactly.

Usage:
    python scripts/check_baseline_manifest.py \
        [--root <repo-root>] [--manifest <manifest-json>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def check(root: Path, manifest_path: Path) -> list[str]:
    """Return a list of failure descriptions (empty means ALL_MATCH)."""
    failures: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"manifest unreadable: {exc}"]
    digests = manifest.get("source_digests")
    if not isinstance(digests, dict) or not digests:
        failures.append("manifest has no source_digests")
    else:
        for rel, recorded in digests.items():
            target = root / rel
            try:
                current = hashlib.sha256(target.read_bytes()).hexdigest()
            except OSError as exc:
                print(f"MISSING {rel} ({str(exc)[:100]})")
                failures.append(rel)
                continue
            match = current == recorded
            print(("MATCH " if match else "STALE ") + rel)
            print(f"  recorded={str(recorded)[:16]} current={current[:16]}")
            if not match:
                failures.append(rel)
    recomputed = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "manifest_sha256"},
                   sort_keys=True).encode()).hexdigest()
    stored = str(manifest.get("manifest_sha256", ""))
    hash_match = bool(stored) and recomputed == stored
    print(f"manifest_sha256 stored={stored[:16]} recomputed={recomputed[:16]}"
          f" {'MATCH' if hash_match else 'STALE'}")
    if not hash_match:
        failures.append("manifest_sha256")
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                        help="repository root the digests are relative to")
    parser.add_argument("--manifest",
                        default=str(Path(__file__).resolve().parent.parent
                                    / "tmp" / "p1-target" / "evidence"
                                    / "baseline-manifest.json"),
                        help="baseline manifest JSON to verify")
    args = parser.parse_args(argv)
    failures = check(Path(args.root), Path(args.manifest))
    if failures:
        print("STALE_PRESENT: " + ", ".join(failures))
        return 1
    print("ALL_MATCH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
