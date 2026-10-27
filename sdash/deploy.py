"""Output guard (REQ-009/REQ-010) and segments.yaml backups (D-004).

The guard runs on the built site (web/dist) before anything is published. `deploy()` then commits
web/dist (and nothing else) to the gh-pages branch through a temporary git worktree and pushes it
with a plain fast-forward push: never --force, never main.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any

RAW_SUFFIXES = (
    ".fit", ".fit.gz", ".gpx", ".gpx.gz", ".tcx", ".tcx.gz", ".zip", ".csv", ".csv.gz",
)  # fmt: skip
COORD_KEYS = frozenset(
    {
        "lat",
        "lon",
        "lng",
        "latitude",
        "longitude",
        "start",
        "end",
        "coords",
        "coordinates",
        "points",
        "track",
        "ref_points",
        "polyline",
        "position",
        "latlng",
    }
)
KEEP_BACKUPS = 10


class GuardError(Exception):
    """The built site must not be published; the message names every offending file."""


class DeployError(Exception):
    """Deploying failed (after the guard passed)."""


LATLON_KEYS = frozenset({"lat", "lon", "lng", "latitude", "longitude", "latlng"})
JSON_SUFFIXES = (".json", ".geojson")


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _looks_like_pair(items: list[Any]) -> bool:
    """Two numbers, at least one non-integer, within lat/lon ranges: a coordinate pair."""
    if len(items) != 2 or not all(_is_number(x) for x in items):
        return False
    a, b = items
    return (
        all(isfinite(x) for x in items)
        and any(x != int(x) for x in items)
        and abs(a) <= 90
        and abs(b) <= 180
    )


def _coordinate_findings(obj: Any, keys: frozenset[str], pairs: bool) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in keys:
                found.add(f"field {key}")
            found |= _coordinate_findings(value, keys, pairs)
    elif isinstance(obj, list):
        if pairs and _looks_like_pair(obj):
            found.add("lat/lon-like number pair")
        for value in obj:
            found |= _coordinate_findings(value, keys, pairs)
    return found


def check_site(dist: Path) -> list[str]:
    """One line per problem: raw files, symlinks, and coordinates in any JSON/GeoJSON file.

    Under data/ and in any *.geojson the full key list and the lat/lon pair shape are checked;
    elsewhere (e.g. Vite manifests) only lat/lon-style keys. Unreadable JSON is a problem anywhere.
    Symlinks are flagged and never followed.
    """
    problems: list[str] = []
    for root, dirs, files in os.walk(dist):
        for name in sorted(dirs + files):
            path = Path(root) / name
            if path.is_symlink():
                problems.append(f"{path.relative_to(dist).as_posix()}: symlink")
        for name in sorted(files):
            path = Path(root) / name
            rel = path.relative_to(dist).as_posix()
            if path.is_symlink():
                continue
            if name.lower().endswith(RAW_SUFFIXES):
                problems.append(f"{rel}: raw ride/export file")
            elif name.lower().endswith(JSON_SUFFIXES):
                in_data = rel.startswith("data/")
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):  # fails closed, wherever the file is
                    problems.append(f"{rel}: unreadable JSON, cannot verify no coordinates")
                    continue
                full = in_data or name.lower().endswith(".geojson")
                found = _coordinate_findings(data, COORD_KEYS if full else LATLON_KEYS, full)
                if found:
                    problems.append(f"{rel}: coordinates ({', '.join(sorted(found))})")
    return sorted(problems)


def guard(dist: Path) -> None:
    """Raise GuardError unless `dist` is a built site without raw files or coordinates."""
    if not (dist / "index.html").is_file():
        raise GuardError(f"{dist} has no index.html: the site was not built")
    problems = check_site(dist)
    if problems:
        raise GuardError("output guard failed, nothing deployed:\n  " + "\n  ".join(problems))


DEFAULT_REMOTE = "origin"
BRANCH = "gh-pages"
COMMIT_MESSAGE = "Deploy site"
_URL_CREDENTIALS = re.compile(r"(://)[^/@\s]+@")


def _git(
    args: list[str], cwd: Path, *, ok: tuple[int, ...] = (0,)
) -> subprocess.CompletedProcess[str]:
    """Run git with a fixed argv (no shell); a failure becomes a DeployError without credentials."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise DeployError(f"cannot run git ({exc.strerror})") from None
    if proc.returncode not in ok:
        lines = [ln for ln in proc.stderr.strip().splitlines() if ln.strip()]
        detail = _URL_CREDENTIALS.sub(r"\1", "; ".join(lines[-3:]))
        raise DeployError(f"git {args[0]} failed (exit {proc.returncode}): {detail}")
    return proc


def deploy(web_dir: Path, remote: str | None) -> bool:
    """Guard, then publish web/dist as one new commit on `gh-pages` of `remote` (default origin).

    Returns True if pushed, False if the site is identical to what gh-pages already has. The
    commit is built in a temporary worktree whose only content is web/dist (+ .nojekyll), on top of
    the remote's gh-pages (or as a root commit if there is none), then pushed as a plain
    fast-forward `<commit>:refs/heads/gh-pages`. A rejected push is an error; nothing is retried.
    """
    dist = web_dir / "dist"
    guard(dist)
    target = remote or DEFAULT_REMOTE
    repo = web_dir.resolve()
    tmp = Path(tempfile.mkdtemp(prefix="sdash-deploy-"))
    work = tmp / "wt"
    registered = False
    try:
        listing = _git(["ls-remote", "--exit-code", "--heads", target, BRANCH], repo, ok=(0, 2))
        parent: str | None = None
        if listing.returncode == 0:
            _git(["fetch", "--no-tags", "-q", target, f"refs/heads/{BRANCH}"], repo)
            parent = _git(["rev-parse", "FETCH_HEAD^{commit}"], repo).stdout.strip()
        _git(["worktree", "add", "--detach", "--no-checkout", str(work), "HEAD"], repo)
        registered = True
        shutil.copytree(dist, work, symlinks=True, dirs_exist_ok=True)
        (work / ".nojekyll").touch()
        _git(["add", "-A", "-f", "."], work)
        tree = _git(["write-tree"], work).stdout.strip()
        if parent and _git(["rev-parse", f"{parent}^{{tree}}"], work).stdout.strip() == tree:
            return False
        ident = ["-c", "user.name=sdash deploy", "-c", "user.email=sdash@localhost"]
        have_ident = _git(["var", "GIT_COMMITTER_IDENT"], work, ok=(0, 128)).returncode == 0
        commit_args = [*([] if have_ident else ident), "commit-tree", tree]
        if parent:
            commit_args += ["-p", parent]
        commit = _git([*commit_args, "-m", COMMIT_MESSAGE], work).stdout.strip()
        try:
            _git(["push", "-q", target, f"{commit}:refs/heads/{BRANCH}"], work)
        except DeployError as exc:
            raise DeployError(
                f"push to {BRANCH} rejected or failed, nothing forced: {exc}"
            ) from None
        return True
    finally:
        if registered:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(work)],
                cwd=repo, capture_output=True, check=False,
            )  # fmt: skip
            subprocess.run(["git", "worktree", "prune"], cwd=repo, capture_output=True, check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def backup_segments(path: Path, keep: int = KEEP_BACKUPS) -> Path | None:
    """Copy segments.yaml to segments.bak/ (last `keep` copies); None if missing or unchanged."""
    if not path.is_file():
        return None
    folder = path.with_name("segments.bak")
    content = path.read_bytes()
    existing = sorted(folder.glob("segments-*.yaml")) if folder.is_dir() else []
    if existing and existing[-1].read_bytes() == content:
        return None
    folder.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = folder / f"segments-{stamp}.yaml"
    target.write_bytes(content)
    for old in sorted(folder.glob("segments-*.yaml"))[:-keep]:
        old.unlink()
    return target
