"""REQ-009: One-command refresh. `sdash refresh [zip|link] [--no-deploy] --web-dir <W> --remote <R>`
runs against a throwaway copy of web/ in a temp git repo (site_repo fixture) and pushes only to a
local bare repo. Needs web/node_modules (npm --prefix web ci) because it builds the site."""

from __future__ import annotations

import json
import re
from pathlib import Path

import _scenarios as sc
import pytest
from _synth import Activity, Ride, export_files, segments_yaml, write_raw, write_zip
from conftest import SdashRunner, SiteRepo, git, load_json, require_web_toolchain

pytestmark = pytest.mark.req("REQ-009")
NOT_DONE = "REQ-009 refresh not implemented (T-011)"
CORRUPT_ID = "1000000009"


@pytest.fixture(autouse=True)
def _web_toolchain() -> None:
    require_web_toolchain()


def _rides() -> list[Ride]:
    corrupt = Ride(
        Activity(CORRUPT_ID, sc.DAY0, "Synthetic corrupt ride"),
        None,
        fmt="fit",
        raw_bytes=b"not a fit file" * 10,
    )
    run = sc.ride("1000000008", [(0, 0), (0, 3000)], day=3, type="Run", name="Synthetic run")
    return [sc.reference_ride(), sc.normal_with_stop(), corrupt, run]


def _zip(tmp_path: Path) -> Path:
    return write_zip(tmp_path / "export.zip", export_files(_rides()))


def _main_sha(repo: SiteRepo) -> str:
    return git("rev-parse", "main", cwd=repo.remote)


@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req009_refresh_from_zip_builds_deploys_and_reports(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path, site_repo: SiteRepo
) -> None:
    (data_dir / "segments.yaml").write_text(segments_yaml([sc.segment()]))
    main_before = _main_sha(site_repo)
    result = sdash(
        "refresh", _zip(tmp_path), "--web-dir", site_repo.web, "--remote", site_repo.remote
    ).ok()

    assert "gh-pages" in site_repo.remote_branches()
    files = site_repo.remote_files("gh-pages")
    assert "index.html" in files and "data/index.json" in files, files
    assert _main_sha(site_repo) == main_before, "refresh must never push to main"

    lines = result.output.splitlines()
    assert any(re.search(r"pars", ln, re.I) and re.search(r"\d", ln) for ln in lines), (
        "no 'rides parsed' count"
    )
    assert any(CORRUPT_ID in ln for ln in lines), "failed ride not in the report"
    assert any(sc.SEGMENT_NAME in ln and re.search(r"\b2\b", ln) for ln in lines), (
        "no efforts-per-segment line"
    )


@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req009_refresh_without_argument_rebuilds_from_existing_data(
    sdash: SdashRunner, data_dir: Path, site_repo: SiteRepo
) -> None:
    write_raw(data_dir, _rides())
    (data_dir / "segments.yaml").write_text(segments_yaml([sc.segment()]))
    sdash("refresh", "--no-deploy", "--web-dir", site_repo.web).ok()
    index = load_json(site_repo.web / "dist" / "data" / "index.json")
    assert [s["name"] for s in index["segments"]] == [sc.SEGMENT_NAME]

    # e.g. after `sdash segment add`: a new segment appears without a new export
    (data_dir / "segments.yaml").write_text(
        segments_yaml([sc.segment(), sc.segment(name="Synthetic climb again")])
    )
    sdash("refresh", "--no-deploy", "--web-dir", site_repo.web).ok()
    index = load_json(site_repo.web / "dist" / "data" / "index.json")
    counts = {s["name"]: s["efforts"] for s in index["segments"]}
    assert counts == {sc.SEGMENT_NAME: 2, "Synthetic climb again": 2}


@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req009_no_deploy_stops_after_local_build(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path, site_repo: SiteRepo
) -> None:
    (data_dir / "segments.yaml").write_text(segments_yaml([sc.segment()]))
    sdash(
        "refresh",
        _zip(tmp_path),
        "--no-deploy",
        "--web-dir",
        site_repo.web,
        "--remote",
        site_repo.remote,
    ).ok()
    assert (site_repo.web / "dist" / "index.html").is_file()
    assert (site_repo.web / "dist" / "data" / "index.json").is_file()
    assert site_repo.remote_branches() == {"main"}, "--no-deploy pushed something"


@pytest.mark.parametrize("failure", ["invalid-segments", "broken-zip", "site-build-fails"])
@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req009_any_failed_step_deploys_nothing(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path, site_repo: SiteRepo, failure: str
) -> None:
    segs = [sc.segment()]
    source = _zip(tmp_path)
    if failure == "invalid-segments":
        segs = [sc.segment(), sc.segment()]  # duplicate name
    elif failure == "broken-zip":
        source.write_bytes(b"this is not a zip archive")
    elif failure == "site-build-fails":
        (site_repo.web / "src" / "main.ts").write_text("export const broken = ;\n")
    (data_dir / "segments.yaml").write_text(segments_yaml(segs))
    result = sdash("refresh", source, "--web-dir", site_repo.web, "--remote", site_repo.remote)
    assert result.returncode != 0, f"refresh succeeded despite {failure}"
    assert "not implemented" not in result.output
    assert site_repo.remote_branches() == {"main"}, f"deployed despite {failure}"


@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req009_refresh_guard_blocks_raw_file_in_site(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path, site_repo: SiteRepo
) -> None:
    (data_dir / "segments.yaml").write_text(segments_yaml([sc.segment()]))
    leak = site_repo.web / "public" / "leak.gpx"  # Vite copies public/ into dist/
    leak.write_text(json.dumps({"synthetic": True}))
    result = sdash(
        "refresh", _zip(tmp_path), "--web-dir", site_repo.web, "--remote", site_repo.remote
    )
    assert result.returncode != 0
    assert "leak.gpx" in result.output, f"guard must name the offending file:\n{result.output}"
    assert site_repo.remote_branches() == {"main"}
