"""Manifest: capture the immutable inputs of a single experimental run.

A manifest is written before the first API call and is never modified after.
It serves as the audit trail: anyone reading the run later can verify
exactly which protocol, plantillas, models, and code commit produced it.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _file_sha256(path: Path) -> Optional[str]:
    """Short sha256 hash of a file's contents, or None if the file is missing."""
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _git_commit() -> Optional[str]:
    """Best-effort current git commit (short hash). None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2.0,
        )
        return result.stdout.strip()[:12]
    except Exception:
        return None


def _git_dirty() -> Optional[bool]:
    """Best-effort: does the working tree have uncommitted changes?"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2.0,
        )
        return bool(result.stdout.strip())
    except Exception:
        return None


def make_run_id() -> str:
    """UTC ISO-like timestamp suitable for directory names and sorting."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def create_manifest(
    experiment_id: str,
    config: dict,
    data_files: Optional[list[Path]] = None,
    extra: Optional[dict] = None,
    run_id: Optional[str] = None,
) -> dict:
    """Build a manifest dict capturing the immutable inputs of a run.

    Args:
        experiment_id: short identifier of the experiment module.
        config: serializable config used for this run (e.g. parsed YAML).
        data_files: list of data files to hash into the manifest.
        extra: additional metadata to embed (any JSON-serializable dict).
        run_id: override timestamp-based id.

    Returns:
        A dict ready to write to manifest.json.
    """
    manifest = {
        "experiment_id": experiment_id,
        "run_id": run_id or make_run_id(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git": {
            "commit": _git_commit(),
            "dirty": _git_dirty(),
        },
        "config": config,
        "data_hashes": {
            p.name: _file_sha256(p) for p in (data_files or [])
        },
    }
    if extra:
        manifest["extra"] = extra
    return manifest


def write_manifest(run_dir: Path, manifest: dict) -> Path:
    """Write the manifest as pretty-printed JSON. Returns the path."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "manifest.json"
    out.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return out


def read_manifest(run_dir: Path) -> dict:
    """Read and return the manifest of an existing run."""
    return json.loads((Path(run_dir) / "manifest.json").read_text(encoding="utf-8"))
