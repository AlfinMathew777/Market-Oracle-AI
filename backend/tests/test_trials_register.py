"""Trials register: chain integrity contract (see docs/trials/README.md)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTER = REPO / "docs" / "trials" / "register.jsonl"
VERIFIER = REPO / "backend" / "scripts" / "verify" / "verify_trials_register.py"
APPENDER = REPO / "backend" / "scripts" / "append_trial.py"


def _run_verifier(register: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFIER), "--register", str(register)],
        capture_output=True, text=True,
    )


def test_committed_register_chain_is_intact():
    result = _run_verifier(REGISTER)
    assert result.returncode == 0, result.stdout + result.stderr


def test_tampered_entry_breaks_chain(tmp_path):
    tampered = tmp_path / "register.jsonl"
    shutil.copy(REGISTER, tampered)
    lines = tampered.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["result"] = "quietly improved"
    lines[0] = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = _run_verifier(tampered)
    assert result.returncode == 1
    assert "entry_hash mismatch" in result.stdout


def test_append_extends_chain_verifiably(tmp_path):
    register = tmp_path / "register.jsonl"
    shutil.copy(REGISTER, register)
    result = subprocess.run(
        [
            sys.executable, str(APPENDER), "--register", str(register),
            "--description", "test trial", "--config", "X=1",
            "--metric", "none", "--result", "pending",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _run_verifier(register).returncode == 0
