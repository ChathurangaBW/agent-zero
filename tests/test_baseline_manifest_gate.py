"""Gate-script coverage: match, drift, and manifest-hash verification."""
import hashlib
import importlib.util
import json
from pathlib import Path

_gate_path = Path(__file__).resolve().parent.parent / "scripts" / "check_baseline_manifest.py"
_spec = importlib.util.spec_from_file_location("check_baseline_manifest", _gate_path)
assert _spec is not None and _spec.loader is not None
_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gate)
check, main = _gate.check, _gate.main

_gen_path = Path(__file__).resolve().parent.parent / "scripts" / "generate_baseline_manifest.py"
_gspec = importlib.util.spec_from_file_location("generate_baseline_manifest", _gen_path)
assert _gspec is not None and _gspec.loader is not None
_gen = importlib.util.module_from_spec(_gspec)
_gspec.loader.exec_module(_gen)


def _manifest(tmp_path, body=b"hello"):
    target = tmp_path / "src.txt"
    target.write_bytes(body)
    manifest: dict = {
        "source_digests": {
            "src.txt": hashlib.sha256(body).hexdigest(),
        },
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items()
                    if k != "manifest_sha256"},
                   sort_keys=True).encode()).hexdigest()
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def test_gate_matches_clean_tree(tmp_path, capsys):
    path = _manifest(tmp_path)
    assert check(tmp_path, path) == []
    assert main(["--root", str(tmp_path), "--manifest", str(path)]) == 0
    assert "ALL_MATCH" in capsys.readouterr().out


def test_gate_fails_on_content_drift(tmp_path, capsys):
    # Tree drift trips the per-file line; the manifest hash itself is
    # untouched (it covers manifest content, catching manifest tampering).
    path = _manifest(tmp_path)
    (tmp_path / "src.txt").write_bytes(b"tampered")
    failures = check(tmp_path, path)
    assert failures == ["src.txt"]
    assert main(["--root", str(tmp_path), "--manifest", str(path)]) == 1
    assert "STALE_PRESENT" in capsys.readouterr().out


def test_gate_fails_on_forged_hash(tmp_path, capsys):
    path = _manifest(tmp_path)
    manifest = json.loads(path.read_text())
    manifest["manifest_sha256"] = "0" * 64
    path.write_text(json.dumps(manifest))
    failures = check(tmp_path, path)
    assert failures == ["manifest_sha256"]
    assert main(["--root", str(tmp_path), "--manifest", str(path)]) == 1
    assert "STALE" in capsys.readouterr().out


def test_generator_roundtrip_verifies(tmp_path, capsys):
    """The tracked generator's output passes the tracked gate without
    hardcoded machine paths."""
    import sys as _sys
    for rel in _gen.KEY_FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"dummy source")
    out = tmp_path / "m.json"
    assert _gen.main(["--root", str(tmp_path), "--out", str(out),
                      "--framework-python", _sys.executable]) == 0
    assert check(tmp_path, out) == []
    capsys.readouterr()
    assert main(["--root", str(tmp_path), "--manifest", str(out)]) == 0
    assert "ALL_MATCH" in capsys.readouterr().out


def test_gate_fails_on_missing_file(tmp_path, capsys):
    path = _manifest(tmp_path)
    (tmp_path / "src.txt").unlink()
    failures = check(tmp_path, path)
    assert failures == ["src.txt"]
    assert main(["--root", str(tmp_path), "--manifest", str(path)]) == 1
    assert "MISSING" in capsys.readouterr().out
