"""Provenance marker `data/build-info.json` (D-008).

`sdash build-data` writes it last; `sdash deploy` recomputes the digest over the built site's
`data/` and refuses anything not produced by build-data. The digest covers every other file under
the data dir, sorted by relative POSIX path, each fed as `path\\0<bytes>\\0`.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

NAME = "build-info.json"
SOURCE = "sdash build-data"
MAX_MARKER_BYTES = 4096


class BuildInfoError(Exception):
    """The data was not produced by `sdash build-data` (message names the cause)."""


def compute_digest(data_dir: Path) -> str:
    """SHA-256 over all files but the top-level marker; a symlink is an error (never followed)."""
    files: list[tuple[str, Path]] = []
    for root, dirs, names in os.walk(data_dir):
        for name in dirs + names:
            if (Path(root) / name).is_symlink():
                rel = (Path(root) / name).relative_to(data_dir).as_posix()
                raise BuildInfoError(f"data/{rel} is a symlink; data must be real files")
        for name in names:
            path = Path(root) / name
            rel = path.relative_to(data_dir).as_posix()
            if rel != NAME:
                files.append((rel, path))
    digest = hashlib.sha256()
    for rel, path in sorted(files):
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise BuildInfoError(f"cannot read data/{rel} ({exc.strerror})") from None
        digest.update(rel.encode() + b"\0" + content + b"\0")
    return digest.hexdigest()


def write(data_dir: Path) -> None:
    """Write the marker for the current content of `data_dir` (call after everything else)."""
    info = {"source": SOURCE, "data_sha256": compute_digest(data_dir)}
    (data_dir / NAME).write_text(
        json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def verify(data_dir: Path) -> None:
    """Raise BuildInfoError unless `data_dir` holds a marker matching its content."""
    marker = data_dir / NAME
    if not marker.is_file() or marker.is_symlink():
        if marker.exists() or marker.is_symlink():
            raise BuildInfoError(f"{NAME} is not a regular file")
        raise BuildInfoError(f"no {NAME}: web/dist was not built from sdash build-data data")
    try:
        with marker.open("rb") as fh:
            raw = fh.read(MAX_MARKER_BYTES + 1)
        if len(raw) > MAX_MARKER_BYTES:
            raise ValueError("too large")
        info = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):  # includes UnicodeDecodeError
        raise BuildInfoError(f"{NAME} is unreadable") from None
    if not isinstance(info, dict) or not isinstance(info.get("data_sha256"), str):
        raise BuildInfoError(f"{NAME} is malformed")
    if info.get("source") != SOURCE:
        raise BuildInfoError(f"{NAME} has the wrong source (expected {SOURCE!r})")
    if info["data_sha256"] != compute_digest(data_dir):
        raise BuildInfoError("data changed after build-data: web/dist/data does not match")
