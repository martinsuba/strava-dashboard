"""REQ-010: Raw data never in Git. Implemented by the harness itself (.gitignore,
scripts/check_raw_data.py, the CI step), so these tests pass from the start."""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import sys
from pathlib import Path

import fitdecode
import gpxpy
import pytest
import yaml
from _synth import SYNTH_BOX
from conftest import REPO, coordinate_leaks

pytestmark = pytest.mark.req("REQ-010")

RAW_PATTERNS = [
    "x.fit",
    "x.fit.gz",
    "x.gpx",
    "x.gpx.gz",
    "x.tcx",
    "x.tcx.gz",
    "export.zip",
    "activities.csv",
]


def _ignored(path: str) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=REPO, check=False)
    assert r.returncode in (0, 1), r
    return r.returncode == 0


@pytest.mark.parametrize("name", RAW_PATTERNS)
def test_req010_gitignore_excludes_raw_files_outside_fixtures(name: str) -> None:
    for where in ("", "sub/dir/", "web/public/", "sdash/"):
        assert _ignored(where + name), f"{where + name} is not git-ignored"
    assert not _ignored(f"tests/fixtures/{name}"), f"tests/fixtures/{name} must stay committable"
    assert not _ignored(f"tests/fixtures/export/activities/{name}")


@pytest.mark.parametrize(
    "path", ["data/raw/x.txt", "web/public/data/index.json", "strava-export/raw/a.txt"]
)
def test_req010_gitignore_excludes_data_dirs(path: str) -> None:
    assert _ignored(path), f"{path} is not git-ignored"


def _repo_with(tmp_path: Path, files: list[str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    for f in files:
        (repo / f).parent.mkdir(parents=True, exist_ok=True)
        (repo / f).write_bytes(b"synthetic")
    subprocess.run(["git", "add", "-f", "--", *files], cwd=repo, check=True)
    return repo


def _check(repo: Path) -> subprocess.CompletedProcess[str]:
    script = REPO / "scripts" / "check_raw_data.py"
    return subprocess.run(
        [sys.executable, str(script)], cwd=repo, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize("name", RAW_PATTERNS)
def test_req010_ci_check_fails_on_raw_file_outside_fixtures(tmp_path: Path, name: str) -> None:
    result = _check(_repo_with(tmp_path, ["README.md", f"some/dir/{name}"]))
    assert result.returncode != 0, f"raw-data check accepted some/dir/{name}"
    assert f"some/dir/{name}" in result.stdout + result.stderr


def test_req010_ci_check_allows_fixtures(tmp_path: Path) -> None:
    files = ["README.md"] + [f"tests/fixtures/export/{n}" for n in RAW_PATTERNS]
    result = _check(_repo_with(tmp_path, files))
    assert result.returncode == 0, result.stdout + result.stderr


def test_req010_ci_runs_the_raw_data_check() -> None:
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text())
    steps = [s.get("run", "") for job in workflow["jobs"].values() for s in job.get("steps", [])]
    assert any("scripts/check_raw_data.py" in s for s in steps)


def test_req010_repo_currently_clean() -> None:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    result = _check(REPO)
    assert result.returncode == 0, result.stdout + result.stderr


# ---- fixtures are synthetic ----------------------------------------------------------------
def _positions(path: Path) -> list[tuple[float, float]]:
    data = path.read_bytes()
    if path.name.endswith(".gz"):
        data = gzip.decompress(data)
    name = path.name.removesuffix(".gz")
    if name.endswith(".gpx"):
        gpx = gpxpy.parse(data.decode())
        return [(p.latitude, p.longitude) for t in gpx.tracks for s in t.segments for p in s.points]
    if name.endswith(".fit"):
        out = []
        import io

        with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.DISABLED) as fit:
            for frame in fit:
                if isinstance(frame, fitdecode.FitDataMessage) and frame.name == "record":
                    lat, lon = (
                        frame.get_value("position_lat", fallback=None),
                        frame.get_value("position_long", fallback=None),
                    )
                    if lat is not None and lon is not None:
                        out.append((lat * 180 / 2**31, lon * 180 / 2**31))
        return out
    return []


def test_req010_fixture_tracks_lie_in_the_synthetic_area() -> None:
    """Every track under tests/fixtures/ must lie in SYNTH_BOX (open South Pacific): no real places."""
    fixtures = REPO / "tests" / "fixtures"
    tracks = [
        p
        for p in fixtures.rglob("*")
        if p.is_file() and p.name.removesuffix(".gz").endswith((".gpx", ".fit"))
    ]
    assert tracks, "expected at least the harness's minimal GPX fixture"
    for path in tracks:
        try:
            positions = _positions(path)
        except Exception:  # deliberately corrupt fixture files carry no positions
            continue
        for lat, lon in positions:
            assert SYNTH_BOX["lat"][0] <= lat <= SYNTH_BOX["lat"][1], (
                f"{path}: lat {lat} outside the synthetic area"
            )
            assert SYNTH_BOX["lon"][0] <= lon <= SYNTH_BOX["lon"][1], (
                f"{path}: lon {lon} outside the synthetic area"
            )


def test_req010_site_data_fixture_has_no_coordinates() -> None:
    site = REPO / "tests" / "fixtures" / "site-data"
    files = list(site.rglob("*.json"))
    assert files
    for p in files:
        assert not coordinate_leaks(json.loads(p.read_text())), p
