"""REQ-009/REQ-010 output guard and segments.yaml backups (synthetic data only)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from sdash import buildinfo, deploy


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
    buildinfo.write(dist / "data")
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


def test_symlinks_in_dist_are_flagged(tmp_path: Path) -> None:
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


def test_symlinks_are_flagged_files_and_dirs_alike(tmp_path: Path) -> None:
    dist = _site(tmp_path)
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "a.json").write_text("{}")
    (dist / "dirlink").symlink_to(tmp_path / "outside", target_is_directory=True)
    (dist / "ok.txt").symlink_to(tmp_path / "outside" / "a.json")
    bad = deploy.check_site(dist)
    assert sorted(b.split(":")[0] for b in bad) == ["dirlink", "ok.txt"]


def test_unlisted_key_holding_coordinate_pairs_is_flagged(tmp_path: Path) -> None:
    payload = json.dumps({"trace": [[-47.25, -134.75], [-47.26, -134.76]]})
    dist = _site(tmp_path, data__r=payload)
    (dist / "data" / "r").rename(dist / "data" / "r.json")
    bad = deploy.check_site(dist)
    assert len(bad) == 1 and "data/r.json" in bad[0] and "pair" in bad[0]


@pytest.mark.parametrize(
    "value", [[1, 2], [3600.5, 7.0, 1.5], [95.5, 10.5], [10.5, 181.5], [True, 1.5], ["a", 1.5]]
)
def test_non_coordinate_lists_are_not_pairs(tmp_path: Path, value: list) -> None:
    dist = _site(tmp_path)
    (dist / "data" / "ok.json").write_text(json.dumps({"series": [value]}))
    assert deploy.check_site(dist) == []


def test_lat_key_outside_data_is_flagged_but_start_is_not(tmp_path: Path) -> None:
    dist = _site(tmp_path)
    (dist / "other").mkdir()
    (dist / "other" / "c.json").write_text(json.dumps({"lat": -47.2}))
    (dist / "manifest.json").write_text(json.dumps({"start": "/", "p": [1.5, 2.5]}))
    bad = deploy.check_site(dist)
    assert len(bad) == 1 and "other/c.json" in bad[0]


def test_geojson_is_scanned(tmp_path: Path) -> None:
    dist = _site(tmp_path)
    geo = {"type": "LineString", "coordinates": [[-134.75, -47.25], [-134.76, -47.26]]}
    (dist / "data" / "x.geojson").write_text(json.dumps(geo))
    bad = deploy.check_site(dist)
    assert len(bad) == 1 and "x.geojson" in bad[0]


def test_geojson_outside_data_is_checked_against_the_full_key_list(tmp_path: Path) -> None:
    dist = _site(tmp_path)
    (dist / "map.geojson").write_text(json.dumps({"type": "Feature", "coordinates": "x"}))
    (dist / "manifest.json").write_text(json.dumps({"coordinates": "x"}))
    bad = deploy.check_site(dist)
    assert len(bad) == 1 and "map.geojson" in bad[0]


def test_unparseable_json_outside_data_fails_closed(tmp_path: Path) -> None:
    dist = _site(tmp_path)
    (dist / "manifest.json").write_text("{not json")
    (dist / "bin.json").write_bytes(b"\xff\xfe\x00")
    bad = deploy.check_site(dist)
    assert len(bad) == 2 and all("unreadable JSON" in b for b in bad)


# --- publishing to gh-pages (local bare repos only) ---


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    for var, val in (("NAME", "T"), ("EMAIL", "t@example.invalid")):
        monkeypatch.setenv(f"GIT_AUTHOR_{var}", val)
        monkeypatch.setenv(f"GIT_COMMITTER_{var}", val)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)


def _repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """(web_dir, bare remote, working repo containing web/)."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    work = tmp_path / "work"
    (work / "web").mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=work)
    (work / "README").write_text("r")
    _git("add", "-A", cwd=work)
    _git("commit", "-q", "-m", "init", cwd=work)
    return work / "web", remote, work


def _publish(web: Path, remote: Path, title: str = "a") -> None:
    _site(web.parent / "tmpdist", **{"index.html": f"<title>{title}</title>"})
    shutil.rmtree(web / "dist", ignore_errors=True)
    shutil.copytree(web.parent / "tmpdist" / "dist", web / "dist")


def test_deploy_creates_orphan_gh_pages_and_cleans_worktree(tmp_path: Path) -> None:
    web, remote, work = _repo(tmp_path)
    _publish(web, remote)
    assert deploy.deploy(web, str(remote)) is True
    files = set(_git("ls-tree", "-r", "--name-only", "gh-pages", cwd=remote).split())
    assert files == {
        "index.html",
        "assets/app.js",
        "data/index.json",
        "data/build-info.json",
        "data/rides/1.json",
        ".nojekyll",
    }
    assert _git("rev-list", "--count", "gh-pages", cwd=remote) == "1"
    assert _git("worktree", "list", "--porcelain", cwd=work).count("worktree ") == 1
    assert "main" in _git("branch", "--list", cwd=work)  # local branches untouched
    assert "gh-pages" not in _git("branch", "--list", cwd=work)


def test_deploy_second_run_fast_forwards_and_replaces_contents(tmp_path: Path) -> None:
    web, remote, _ = _repo(tmp_path)
    _publish(web, remote, "first")
    deploy.deploy(web, str(remote))
    first = _git("rev-parse", "gh-pages", cwd=remote)
    _publish(web, remote, "second")
    (web / "dist" / "assets" / "app.js").unlink()
    assert deploy.deploy(web, str(remote)) is True
    _git("merge-base", "--is-ancestor", first, "gh-pages", cwd=remote)
    assert "app.js" not in _git("ls-tree", "-r", "--name-only", "gh-pages", cwd=remote)


def test_deploy_unchanged_site_makes_no_commit(tmp_path: Path) -> None:
    web, remote, _ = _repo(tmp_path)
    _publish(web, remote)
    deploy.deploy(web, str(remote))
    before = _git("rev-parse", "gh-pages", cwd=remote)
    assert deploy.deploy(web, str(remote)) is False
    assert _git("rev-parse", "gh-pages", cwd=remote) == before


def test_deploy_rejected_push_is_a_clean_error_and_never_forced(tmp_path: Path) -> None:
    web, remote, work = _repo(tmp_path)
    _publish(web, remote, "mine")
    deploy.deploy(web, str(remote))
    # someone else advances gh-pages after we fetched: simulate by a racing remote hook
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'rejected: non-fast-forward' >&2\nexit 1\n")
    hook.chmod(0o755)
    tip = _git("rev-parse", "gh-pages", cwd=remote)
    _publish(web, remote, "newer")
    with pytest.raises(deploy.DeployError, match="push"):
        deploy.deploy(web, str(remote))
    assert _git("rev-parse", "gh-pages", cwd=remote) == tip
    assert _git("worktree", "list", "--porcelain", cwd=work).count("worktree ") == 1


def test_deploy_guard_failure_creates_nothing(tmp_path: Path) -> None:
    web, remote, _ = _repo(tmp_path)
    _publish(web, remote)
    (web / "dist" / "leak.fit").write_bytes(b"x")
    with pytest.raises(deploy.GuardError):
        deploy.deploy(web, str(remote))
    assert _git("for-each-ref", "refs/heads", cwd=remote) == ""


def test_deploy_does_not_include_files_outside_dist(tmp_path: Path) -> None:
    web, remote, _ = _repo(tmp_path)
    _publish(web, remote)
    (web / "secret.txt").write_text("no")
    deploy.deploy(web, str(remote))
    assert "secret.txt" not in _git("ls-tree", "-r", "--name-only", "gh-pages", cwd=remote)


def test_deploy_default_remote_is_origin(tmp_path: Path) -> None:
    web, remote, work = _repo(tmp_path)
    _git("remote", "add", "origin", str(remote), cwd=work)
    _publish(web, remote)
    deploy.deploy(web, None)
    assert "gh-pages" in _git("branch", "--list", cwd=remote)


def test_repo_redirecting_env_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    web, remote, work = _repo(tmp_path)
    _publish(web, remote)
    index_before = (work / ".git" / "index").read_bytes()
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "bogus-index"))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "bogus-dir"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "bogus-tree"))
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(tmp_path / "bogus-objects"))
    assert deploy.deploy(web, str(remote)) is True
    monkeypatch.delenv("GIT_INDEX_FILE")
    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_WORK_TREE")
    monkeypatch.delenv("GIT_OBJECT_DIRECTORY")
    assert (work / ".git" / "index").read_bytes() == index_before
    assert not (tmp_path / "bogus-index").exists()
    assert "index.html" in _git("ls-tree", "-r", "--name-only", "gh-pages", cwd=remote)


def test_other_stale_worktrees_are_not_pruned(tmp_path: Path) -> None:
    web, remote, work = _repo(tmp_path)
    stale = tmp_path / "stale-wt"
    _git("worktree", "add", "--detach", str(stale), cwd=work)
    shutil.rmtree(stale)
    _publish(web, remote)
    deploy.deploy(web, str(remote))
    assert str(stale) in _git("worktree", "list", "--porcelain", cwd=work)


def test_suffix_named_branch_is_not_taken_for_gh_pages(tmp_path: Path) -> None:
    web, remote, work = _repo(tmp_path)
    _git("push", "-q", str(remote), "main:refs/heads/x/gh-pages", cwd=work)
    _publish(web, remote)
    assert deploy.deploy(web, str(remote)) is True
    assert _git("rev-list", "--count", "refs/heads/gh-pages", cwd=remote) == "1"


def test_fallback_identity_when_git_has_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web, remote, _ = _repo(tmp_path)
    _publish(web, remote)
    for var in ("NAME", "EMAIL"):
        for role in ("AUTHOR", "COMMITTER"):
            monkeypatch.delenv(f"GIT_{role}_{var}")
    monkeypatch.setenv("EMAIL", "")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
    assert deploy.deploy(web, str(remote)) is True
    assert _git("log", "-1", "--format=%an <%ae>", "gh-pages", cwd=remote) == (
        "sdash deploy <sdash@localhost>"
    )


def test_real_non_fast_forward_race_is_a_clean_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web, remote, work = _repo(tmp_path)
    _publish(web, remote, "first")
    deploy.deploy(web, str(remote))
    subprocess.run(["git", "config", "receive.denyNonFastForwards", "true"], cwd=remote, check=True)
    other = tmp_path / "other"
    _git("clone", "-q", "-b", "gh-pages", str(remote), str(other), cwd=tmp_path)
    (other / "extra.txt").write_text("someone else")
    _git("add", "-A", cwd=other)
    _git("commit", "-q", "-m", "other", cwd=other)
    _publish(web, remote, "second")
    real_git = deploy._git

    def racing(args: list[str], cwd: Path, **kw: Any) -> Any:
        if args[0] == "push":  # the remote moves after we fetched, before we push
            _git("push", "-q", "origin", "gh-pages", cwd=other)
        return real_git(args, cwd, **kw)

    monkeypatch.setattr(deploy, "_git", racing)
    with pytest.raises(deploy.DeployError, match="rejected"):
        deploy.deploy(web, str(remote))
    assert _git("log", "-1", "--format=%s", "gh-pages", cwd=remote) == "other"
    assert _git("worktree", "list", "--porcelain", cwd=work).count("worktree ") == 1


@pytest.mark.parametrize("breakage", ["no-marker", "wrong-source", "extra-file", "changed"])
def test_deploy_refuses_unmarked_or_modified_data_before_any_git_call(
    tmp_path: Path, breakage: str
) -> None:
    web, remote, _ = _repo(tmp_path)
    _publish(web, remote)
    data = web / "dist" / "data"
    if breakage == "no-marker":
        (data / "build-info.json").unlink()
    elif breakage == "wrong-source":
        (data / "build-info.json").write_text('{"source": "x", "data_sha256": "0"}')
    elif breakage == "extra-file":
        (data / "extra.json").write_text("{}")
    else:
        (data / "index.json").write_text("{}")
    # a remote that does not exist: any git call would fail with a different message
    with pytest.raises(
        deploy.DeployError, match=r"nothing deployed: .*(build-info|changed|source)"
    ):
        deploy.deploy(web, str(tmp_path / "does-not-exist"))


def test_guard_runs_before_marker_check(tmp_path: Path) -> None:
    web, remote, _ = _repo(tmp_path)
    _publish(web, remote)
    (web / "dist" / "data" / "build-info.json").unlink()
    (web / "dist" / "leak.fit").write_bytes(b"x")
    with pytest.raises(deploy.GuardError, match=r"leak\.fit"):
        deploy.deploy(web, str(remote))
