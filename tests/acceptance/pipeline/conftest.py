"""Shared fixtures for the pipeline acceptance tests.

The tests drive the real `sdash` console script as a subprocess (black box) with
`--data-dir <tmp>`. The CLI contract they rely on is documented in docs/TESTS.md.
Nothing here touches the network or real data.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _synth import SYNTH_BOX  # noqa: E402

REPO = HERE.parents[2]
WEB = REPO / "web"


def sdash_command() -> list[str]:
    exe = Path(sys.executable).with_name("sdash")
    if exe.exists():
        return [str(exe)]
    found = shutil.which("sdash")
    if found:
        return [found]
    return [sys.executable, "-m", "sdash"]


@dataclass
class Result:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + "\n" + self.stderr

    def ok(self) -> Result:
        assert self.returncode == 0, (
            f"sdash {' '.join(self.args)} exited {self.returncode}\n"
            f"--- stdout\n{self.stdout}\n--- stderr\n{self.stderr}"
        )
        return self


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def base_env(tmp_path: Path) -> dict[str, str]:
    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("SDASH_")}
    env.update(
        {
            "TMPDIR": str(tmpdir),  # downloads/temp files must stay inside the test tmp
            "GIT_AUTHOR_NAME": "sdash test",
            "GIT_AUTHOR_EMAIL": "sdash-test@example.invalid",
            "GIT_COMMITTER_NAME": "sdash test",
            "GIT_COMMITTER_EMAIL": "sdash-test@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
            "NO_COLOR": "1",
            # never reach the real network: any accidental proxy use fails fast
            "http_proxy": "http://127.0.0.1:9",
            "https_proxy": "http://127.0.0.1:9",
            "no_proxy": "localhost,127.0.0.1",
        }
    )
    return env


SdashRunner = Callable[..., Result]


@pytest.fixture
def sdash(data_dir: Path, base_env: dict[str, str], tmp_path: Path) -> SdashRunner:
    """sdash(*args, env=None, timeout=120, data=data_dir) -> Result (never raises on exit code)."""

    def run(
        *args: str | Path,
        env: dict[str, str] | None = None,
        timeout: float = 180,
        data: Path | None = None,
        cwd: Path | None = None,
    ) -> Result:
        str_args = ["--data-dir", str(data or data_dir), *map(str, args)]
        proc = subprocess.run(
            [*sdash_command(), *str_args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**base_env, **(env or {})},
            cwd=cwd or tmp_path,
            check=False,
        )
        return Result(str_args, proc.returncode, proc.stdout, proc.stderr)

    return run


def run_pipeline(sdash: SdashRunner, out: Path) -> Path:
    """parse -> match -> build-data --out <out>; each step must succeed."""
    sdash("parse").ok()
    sdash("match").ok()
    sdash("build-data", "--out", out).ok()
    return out


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_cached_track(data_dir: Path, activity_id: str) -> dict[str, list[float]]:
    """ARCHITECTURE.md: cache/<id>.json.gz with arrays t, lat, lon, d."""
    path = data_dir / "cache" / f"{activity_id}.json.gz"
    assert path.exists(), f"no cached track for activity {activity_id} at {path}"
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        track: dict[str, list[float]] = json.load(fh)
    return track


def segment_slug(out: Path, name: str) -> str:
    index = load_json(out / "index.json")
    slugs = [s["slug"] for s in index["segments"] if s["name"] == name]
    assert len(slugs) == 1, f"segment {name!r} not in index.json: {index['segments']}"
    return str(slugs[0])


def efforts_by_activity(out: Path, name: str) -> dict[str, list[dict[str, Any]]]:
    seg = load_json(out / "segments" / f"{segment_slug(out, name)}.json")
    result: dict[str, list[dict[str, Any]]] = {}
    for e in seg["efforts"]:
        result.setdefault(str(e["activity_id"]), []).append(e)
    return result


# ---- privacy scan (REQ-005, REQ-009, REQ-010) ---------------------------------------------
COORD_KEYS = {
    "lat", "lon", "lng", "latitude", "longitude", "start", "end", "coords", "coordinates",
    "points", "track", "ref_points", "polyline", "position", "latlng",
}  # fmt: skip
_NUM = re.compile(r"-?\d+\.\d+")


def _in_box(v: float) -> bool:
    (la0, la1), (lo0, lo1) = SYNTH_BOX["lat"], SYNTH_BOX["lon"]
    return la0 <= v <= la1 or lo0 <= v <= lo1


def coordinate_leaks(obj: Any, path: str = "$") -> list[str]:
    """Keys that look like coordinates, and any number inside the synthetic lat/lon ranges."""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in COORD_KEYS:
                found.append(f"{path}.{k} (coordinate key)")
            found += coordinate_leaks(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += coordinate_leaks(v, f"{path}[{i}]")
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, int | float):
        if _in_box(float(obj)):
            found.append(f"{path}={obj} (synthetic coordinate value)")
    elif isinstance(obj, str):
        for m in _NUM.findall(obj):
            if _in_box(float(m)):
                found.append(f"{path} contains {m} (synthetic coordinate value)")
    return found


# ---- web build helpers (REQ-009) ------------------------------------------------------------
def require_web_toolchain() -> None:
    if not (WEB / "node_modules").is_dir() or shutil.which("npm") is None:
        pytest.skip("web/node_modules missing: run `npm --prefix web ci` first (CI does)")


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@dataclass
class SiteRepo:
    root: Path  # a throwaway git repo with a copy of web/
    web: Path  # root/web (pass as --web-dir)
    remote: Path  # local bare repo (pass as --remote); has a `main` branch

    def remote_branches(self) -> set[str]:
        out = git("for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=self.remote)
        return set(out.split())

    def remote_files(self, branch: str = "gh-pages") -> set[str]:
        return set(git("ls-tree", "-r", "--name-only", branch, cwd=self.remote).split())


@pytest.fixture
def site_repo(tmp_path: Path, base_env: dict[str, str]) -> Iterator[SiteRepo]:
    """Copy of web/ inside a temp git repo whose origin is a local bare repo. Deploy tests push
    there only; the real repository and GitHub are never touched."""
    root = tmp_path / "site-repo"
    web = root / "web"
    shutil.copytree(
        WEB,
        web,
        ignore=shutil.ignore_patterns(
            "node_modules", "dist", "test-results", "playwright-report", "data"
        ),
    )
    shutil.copy(REPO / ".gitignore", root / ".gitignore")
    if (WEB / "node_modules").is_dir():
        (web / "node_modules").symlink_to(WEB / "node_modules", target_is_directory=True)
    remote = tmp_path / "remote.git"
    env = {**base_env}
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True, env=env)
    for cmd in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["commit", "-q", "-m", "synthetic site repo"],
        ["remote", "add", "origin", str(remote)],
        ["push", "-q", "origin", "main"],
    ):
        subprocess.run(["git", *cmd], cwd=root, check=True, env=env, capture_output=True)
    yield SiteRepo(root, web, remote)
