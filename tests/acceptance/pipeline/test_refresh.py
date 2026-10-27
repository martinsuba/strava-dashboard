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


@pytest.mark.parametrize("failure", ["unreadable-yaml", "broken-zip", "site-build-fails"])
def test_req009_any_failed_step_deploys_nothing(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path, site_repo: SiteRepo, failure: str
) -> None:
    source = _zip(tmp_path)
    yaml_text = segments_yaml([sc.segment()])
    if failure == "unreadable-yaml":  # a segment-level problem is only a warning; this is not
        yaml_text = "- name: [unclosed\n  ref_activity: ???\n"
    elif failure == "broken-zip":
        source.write_bytes(b"this is not a zip archive")
    elif failure == "site-build-fails":
        (site_repo.web / "src" / "main.ts").write_text("export const broken = ;\n")
    (data_dir / "segments.yaml").write_text(yaml_text)
    result = sdash("refresh", source, "--web-dir", site_repo.web, "--remote", site_repo.remote)
    assert result.returncode != 0, f"refresh succeeded despite {failure}"
    assert "not implemented" not in result.output
    assert site_repo.remote_branches() == {"main"}, f"deployed despite {failure}"


def _bad_and_good_segments() -> list[dict]:
    return [sc.segment(name="Broken segment", ref="1000000099"), sc.segment()]  # no such reference


def test_req009_invalid_segment_exits_2_and_still_deploys_the_valid_one(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path, site_repo: SiteRepo
) -> None:
    """Plan v3: a segment-level problem is a warning (exit 2); the rest is built and deployed."""
    (data_dir / "segments.yaml").write_text(segments_yaml(_bad_and_good_segments()))
    result = sdash(
        "refresh", _zip(tmp_path), "--web-dir", site_repo.web, "--remote", site_repo.remote
    )
    assert result.returncode == 2, f"expected exit 2:\n{result.output}"
    assert "not implemented" not in result.output
    assert any(
        "Broken segment" in ln and "reference" in ln.lower() for ln in result.output.splitlines()
    ), f"the warning must name the segment and the problem:\n{result.output}"
    assert "gh-pages" in site_repo.remote_branches(), "valid segments must still be deployed"
    files = site_repo.remote_files("gh-pages")
    assert "data/segments/synthetic-climb.json" in files, files
    assert not any("broken-segment" in f for f in files), files


def test_req009_invalid_segment_exits_2_and_builds_the_valid_one(
    sdash: SdashRunner, data_dir: Path, site_repo: SiteRepo
) -> None:
    """Same rule without deploying (works before deploy lands): exit 2, valid segment built."""
    write_raw(data_dir, _rides())
    (data_dir / "segments.yaml").write_text(segments_yaml(_bad_and_good_segments()))
    result = sdash("refresh", "--no-deploy", "--web-dir", site_repo.web)
    assert result.returncode == 2, f"expected exit 2:\n{result.output}"
    assert any(
        "Broken segment" in ln and "reference" in ln.lower() for ln in result.output.splitlines()
    ), f"the warning must name the segment and the problem:\n{result.output}"
    dist_data = site_repo.web / "dist" / "data"
    assert (dist_data / "segments" / "synthetic-climb.json").is_file()
    assert not (dist_data / "segments" / "broken-segment.json").exists()
    index = load_json(dist_data / "index.json")
    assert [s["name"] for s in index["segments"]] == [sc.SEGMENT_NAME]
    assert (site_repo.web / "dist" / "index.html").is_file()


def test_req009_unreadable_segments_yaml_fails_with_exit_1_and_builds_nothing(
    sdash: SdashRunner, data_dir: Path, site_repo: SiteRepo
) -> None:
    write_raw(data_dir, _rides())
    (data_dir / "segments.yaml").write_text("- name: [unclosed\n  ref_activity: ???\n")
    result = sdash("refresh", "--no-deploy", "--web-dir", site_repo.web)
    assert result.returncode == 1, f"expected exit 1:\n{result.output}"
    assert "segments.yaml" in result.stderr
    assert not (site_repo.web / "dist" / "index.html").exists(), "nothing may be built"


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
