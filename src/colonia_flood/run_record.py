"""Run provenance, kept physically separate from the manifest.

This split is the architectural answer to requirement 7. Because the retrieval
timestamp, library versions, and git commit are assembled here and written to a
different file, it is structurally impossible for a wall-clock value to change
the bytes of ``acquisitions.json``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from . import __version__
from .manifest import serialize, write_atomic
from .stac_client import to_rfc3339

RUN_RECORD_FILENAME = "last_run.json"
RUN_RECORD_SCHEMA_VERSION = "1"

TRACKED_LIBRARIES = ("pystac-client", "pystac", "pydantic")

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def library_versions() -> dict[str, str]:
    """Installed versions of the libraries whose behaviour affects the output."""
    versions: dict[str, str] = {}
    for name in TRACKED_LIBRARIES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return versions


def git_commit(repo_root: Path) -> str | None:
    """Best-effort commit SHA.

    ``None`` when git is unavailable or this is not a repository.
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    return commit or None


def build_run_record(
    *,
    catalog_url: str,
    config_sha256: str,
    manifest_bytes: bytes,
    manifest_sha256: str,
    acquisition_count: int,
    excluded_count: int,
    repo_root: Path,
    clock: Clock = utc_now,
) -> dict[str, Any]:
    """Assemble the provenance envelope for one run.

    ``manifest_sha256`` links this record to exactly the bytes it describes.
    """
    return {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "retrieved_at_utc": to_rfc3339(clock()),
        "catalog_url": catalog_url,
        "tool_version": __version__,
        "git_commit": git_commit(repo_root),
        "client_library_versions": library_versions(),
        "config_sha256": config_sha256,
        "manifest_sha256": manifest_sha256,
        "manifest_bytes": len(manifest_bytes),
        "acquisition_count": acquisition_count,
        "excluded_count": excluded_count,
    }


def write_run_record(path: Path, record: dict[str, Any]) -> bytes:
    payload = serialize(record)
    write_atomic(path, payload)
    return payload
