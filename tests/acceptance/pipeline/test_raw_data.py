"""REQ-010: Raw data never in Git. Implemented by the harness itself (.gitignore,
scripts/check_raw_data.py, the CI step), so these tests pass from the start."""

from __future__ import annotations

import csv
import gzip
import io
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

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
TRACK_SUFFIXES = (".gpx", ".fit", ".tcx")


def _positions(name: str, data: bytes) -> list[tuple[float, float]]:
    """All coordinates in a fixture file (gpx/fit/tcx, optionally .gz; segments.csv; zip members)."""
    if name.endswith(".gz"):
        data = gzip.decompress(data)
        name = name.removesuffix(".gz")
    base = name.rsplit("/", 1)[-1]
    if name.endswith(".zip"):
        out: list[tuple[float, float]] = []
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in zf.namelist():
                inner = member.removesuffix(".gz")
                relevant = inner.endswith(TRACK_SUFFIXES) or inner.endswith("segments.csv")
                if relevant and "corrupt" not in member.lower():
                    out += _positions(member, zf.read(member))
        return out
    if name.endswith(".gpx"):
        gpx = gpxpy.parse(data.decode())
        return [(p.latitude, p.longitude) for t in gpx.tracks for s in t.segments for p in s.points]
    if name.endswith(".fit"):
        out = []
        with fitdecode.FitReader(io.BytesIO(data)) as fit:
            for frame in fit:
                if isinstance(frame, fitdecode.FitDataMessage) and frame.name == "record":
                    lat = frame.get_value("position_lat", fallback=None)
                    lon = frame.get_value("position_long", fallback=None)
                    if lat is not None and lon is not None:
                        out.append((lat * 180 / 2**31, lon * 180 / 2**31))
        return out
    if name.endswith(".tcx"):
        root = ElementTree.fromstring(data.strip())
        out = []
        for pos in root.iter():
            if pos.tag.endswith("Position"):
                vals = {c.tag.rsplit("}", 1)[-1]: float(c.text or "nan") for c in pos}
                out.append((vals["LatitudeDegrees"], vals["LongitudeDegrees"]))
        return out
    if base == "segments.csv":
        rows = csv.DictReader(io.StringIO(data.decode()))
        out = []
        for r in rows:
            out.append((float(r["Starting Latitude"]), float(r["Starting Longitude"])))
            out.append((float(r["Ending Latitude"]), float(r["Ending Longitude"])))
        return out
    return []


def _outside_box(name: str, data: bytes) -> list[str]:
    (la0, la1), (lo0, lo1) = SYNTH_BOX["lat"], SYNTH_BOX["lon"]
    return [
        f"{name}: ({lat}, {lon}) outside the synthetic area"
        for lat, lon in _positions(name, data)
        if not (la0 <= lat <= la1 and lo0 <= lon <= lo1)
    ]


def _fixture_files() -> list[Path]:
    fixtures = REPO / "tests" / "fixtures"
    return [
        p
        for p in fixtures.rglob("*")
        if p.is_file()
        and (
            p.name.removesuffix(".gz").endswith((*TRACK_SUFFIXES, ".zip"))
            or p.name == "segments.csv"
        )
    ]


def test_req010_fixture_tracks_lie_in_the_synthetic_area() -> None:
    """Every coordinate in tests/fixtures/ (tracks, segments.csv, inside zips) lies in SYNTH_BOX
    (open South Pacific). Only files named *corrupt* may fail to parse; any other parse error fails."""
    files = _fixture_files()
    assert files, "expected at least the harness's minimal GPX fixture"
    problems: list[str] = []
    for path in files:
        if "corrupt" in path.name.lower():
            continue
        try:
            problems += _outside_box(path.name, path.read_bytes())
        except Exception as exc:
            problems.append(
                f"{path}: cannot be parsed ({exc!r}); name deliberately broken files *corrupt*"
            )
    assert not problems, "\n".join(problems[:20])


def test_req010_area_check_flags_real_places() -> None:
    """Self-check: the area check above really rejects a point on land (central Europe)."""
    from _synth import Point, encode_track, segments_csv

    pts = [Point(1_700_000_000, 50.08, 14.42, 0.0)]
    for fmt in ("gpx", "fit.gz", "tcx"):
        assert _outside_box(f"x.{fmt}", encode_track(pts, fmt)), fmt
    assert _outside_box("segments.csv", segments_csv([("x", "1", 50.08, 14.42, -47.0, -134.0)]))


def test_req010_site_data_fixture_has_no_coordinates() -> None:
    site = REPO / "tests" / "acceptance" / "web" / "site-data"
    files = list(site.rglob("*.json"))
    assert files
    for p in files:
        assert not coordinate_leaks(json.loads(p.read_text())), p
