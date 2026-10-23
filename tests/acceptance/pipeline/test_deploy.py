"""REQ-009: deploy + output guard. `sdash deploy --web-dir <W> --remote <R>` pushes W/dist to the
gh-pages branch of R. R is a local bare repo that refuses non-fast-forward pushes (so a force-push
fails); nothing here talks to GitHub. W/dist is hand-made, so no npm build is needed."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from conftest import SdashRunner, SiteRepo, git

pytestmark = pytest.mark.req("REQ-009")
NOT_DONE = "REQ-009 deploy not implemented (T-012 deploy, T-011 guard)"


def _dist(
    web: Path, title: str = "Synthetic site", extra: dict[str, str | bytes] | None = None
) -> Path:
    dist = web / "dist"
    files: dict[str, str | bytes] = {
        "index.html": f"<!doctype html><title>{title}</title>",
        "assets/app.js": "console.log('synthetic');",
        "data/index.json": json.dumps(
            {"generated": "2026-10-20T00:00:00Z", "segments": [], "rides": []}
        ),
        **(extra or {}),
    }
    for name, content in files.items():
        p = dist / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
    return dist


@pytest.fixture
def remote(site_repo: SiteRepo) -> SiteRepo:
    subprocess.run(
        ["git", "config", "receive.denyNonFastForwards", "true"], cwd=site_repo.remote, check=True
    )
    subprocess.run(
        ["git", "config", "receive.denyDeletes", "true"], cwd=site_repo.remote, check=True
    )
    return site_repo


@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req009_deploy_pushes_dist_to_gh_pages_only(sdash: SdashRunner, remote: SiteRepo) -> None:
    main_before = git("rev-parse", "main", cwd=remote.remote)
    _dist(remote.web)
    sdash("deploy", "--web-dir", remote.web, "--remote", remote.remote).ok()
    files = remote.remote_files("gh-pages") - {".nojekyll"}
    assert files == {"index.html", "assets/app.js", "data/index.json"}, files
    assert git("rev-parse", "main", cwd=remote.remote) == main_before, "deploy touched main"


@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req009_redeploy_adds_a_commit_without_force(sdash: SdashRunner, remote: SiteRepo) -> None:
    _dist(remote.web, "first")
    sdash("deploy", "--web-dir", remote.web, "--remote", remote.remote).ok()
    first = git("rev-parse", "gh-pages", cwd=remote.remote)
    _dist(remote.web, "second")
    sdash("deploy", "--web-dir", remote.web, "--remote", remote.remote).ok()
    second = git("rev-parse", "gh-pages", cwd=remote.remote)
    assert first != second
    git("merge-base", "--is-ancestor", first, second, cwd=remote.remote)  # raises if not
    assert "second" in git("show", "gh-pages:index.html", cwd=remote.remote)


LEAKS: dict[str, str | bytes] = {
    "leak.fit": b".FIT synthetic",
    "nested/leak.fit.gz": b"\x1f\x8b synthetic",
    "leak.gpx": "<gpx/>",
    "leak.gpx.gz": b"\x1f\x8b synthetic",
    "leak.tcx": "<TrainingCenterDatabase/>",
    "leak.tcx.gz": b"\x1f\x8b synthetic",
    "data/activities.csv": "Activity ID\n1\n",
    "export.csv": "Name,Value\nsynthetic,1\n",
    "data/segments.csv": "Segment Name,Activity ID\nSynthetic,1\n",
    "data/rides/leak.csv.gz": b"\x1f\x8b synthetic",
    "data/rides/leak.json": json.dumps({"id": "1", "lat": -47.25, "lon": -134.75}),
    "data/segments/leak.json": json.dumps({"name": "x", "start": [-47.25, -134.75]}),
}


@pytest.mark.parametrize("leak", list(LEAKS))
@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req009_guard_aborts_deploy_on_raw_files_or_coordinates(
    sdash: SdashRunner, remote: SiteRepo, leak: str
) -> None:
    _dist(remote.web, extra={leak: LEAKS[leak]})
    result = sdash("deploy", "--web-dir", remote.web, "--remote", remote.remote)
    assert result.returncode != 0, f"guard let {leak} through"
    assert "not implemented" not in result.output
    assert Path(leak).name in result.output, f"guard must name the offending file:\n{result.output}"
    assert remote.remote_branches() == {"main"}, "something was pushed despite the guard"


@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req009_guard_passes_clean_site(sdash: SdashRunner, remote: SiteRepo) -> None:
    """Control for the guard tests: a clean site with ride times and names is deployed."""
    ride = {"id": "1", "date": "2026-10-20T03:45:46Z", "name": "Synthetic", "km": 25.3, "elapsed_s": 3600,
            "moving_s": 3300, "gear": "Synthetic bike", "efforts": []}  # fmt: skip
    _dist(remote.web, extra={"data/rides/1.json": json.dumps(ride)})
    sdash("deploy", "--web-dir", remote.web, "--remote", remote.remote).ok()
    assert "data/rides/1.json" in remote.remote_files("gh-pages")
