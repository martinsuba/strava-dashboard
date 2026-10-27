"""REQ-009/REQ-010 output guard and segments.yaml backups (synthetic data only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdash import deploy


def _site(tmp_path: Path, **files: str | bytes) -> Path:
    dist = tmp_path / "dist"
    base: dict[str, str | bytes] = {
        "index.html": "<title>x</title>",
        "assets/app.js": "const start = 1, end = 2;",
        "data/index.json": json.dumps({"generated": "g", "segments": [], "rides": []}),
        "data/rides/1.json": json.dumps({"id": "1", "start_t": 5, "efforts": [{"start_t": 5}]}),
    }
    base.update({k.replace("__", "/"): v for k, v in files.items()})
    for name, content in base.items():
        p = dist / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
    return dist


def test_clean_site_has_no_violations(tmp_path: Path) -> None:
    assert deploy.check_site(_site(tmp_path)) == []


@pytest.mark.parametrize(
    "name",
    [
        "a.fit",
        "A.FIT",
        "n/a.fit.gz",
        "a.gpx",
        "a.gpx.gz",
        "a.tcx",
        "a.tcx.gz",
        "a.zip",
        "x.csv",
        "x.csv.gz",
        "activities.csv",
    ],
)
def test_raw_files_are_flagged_by_path(tmp_path: Path, name: str) -> None:
    dist = _site(tmp_path)
    (dist / name).parent.mkdir(parents=True, exist_ok=True)
    (dist / name).write_bytes(b"x")
    bad = deploy.check_site(dist)
    assert len(bad) == 1 and name in bad[0]


@pytest.mark.parametrize("key", ["lat", "lon", "Latitude", "start", "end", "points", "polyline"])
def test_coordinate_keys_in_json_are_flagged_at_any_depth(tmp_path: Path, key: str) -> None:
    payload = json.dumps({"efforts": [{"deep": [{key: [1.5, 2.5]}]}]})
    dist = _site(tmp_path, data__segments__s=payload)
    (dist / "data" / "segments" / "s").rename(dist / "data" / "segments" / "s.json")
    bad = deploy.check_site(dist)
    assert len(bad) == 1 and "s.json" in bad[0] and key in bad[0]


def test_unparseable_json_is_flagged(tmp_path: Path) -> None:
    dist = _site(tmp_path)
    (dist / "data" / "broken.json").write_text("{not json")
    bad = deploy.check_site(dist)
    assert len(bad) == 1 and "broken.json" in bad[0]


def test_json_outside_data_is_not_scanned(tmp_path: Path) -> None:
    dist = _site(tmp_path)
    (dist / "manifest.json").write_text(json.dumps({"start": "/", "end": 1}))
    assert deploy.check_site(dist) == []


def test_guard_raises_naming_every_offender(tmp_path: Path) -> None:
    dist = _site(tmp_path)
    (dist / "one.gpx").write_text("x")
    (dist / "two.fit").write_text("x")
    with pytest.raises(deploy.GuardError) as exc:
        deploy.guard(dist)
    assert "one.gpx" in str(exc.value) and "two.fit" in str(exc.value)


def test_guard_without_dist_fails(tmp_path: Path) -> None:
    with pytest.raises(deploy.GuardError, match="dist"):
        deploy.guard(tmp_path / "dist")


def test_guard_ignores_symlinks_but_flags_them_when_raw(tmp_path: Path) -> None:
    dist = _site(tmp_path)
    (dist / "link.gpx").symlink_to(tmp_path / "nowhere")
    assert any("link.gpx" in b for b in deploy.check_site(dist))


def test_backup_keeps_the_last_ten(tmp_path: Path) -> None:
    seg = tmp_path / "segments.yaml"
    for i in range(13):
        seg.write_text(f"- name: v{i}\n")
        deploy.backup_segments(seg)
    kept = sorted((tmp_path / "segments.bak").iterdir())
    assert len(kept) == 10
    assert kept[-1].read_text() == "- name: v12\n"
    assert kept[0].read_text() == "- name: v3\n"


def test_backup_skips_identical_content_and_missing_file(tmp_path: Path) -> None:
    seg = tmp_path / "segments.yaml"
    assert deploy.backup_segments(seg) is None
    assert not (tmp_path / "segments.bak").exists()
    seg.write_text("a\n")
    assert deploy.backup_segments(seg) is not None
    assert deploy.backup_segments(seg) is None
    assert len(list((tmp_path / "segments.bak").iterdir())) == 1
