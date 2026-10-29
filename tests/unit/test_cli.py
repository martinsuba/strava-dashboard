"""Scaffolding unit tests for the CLI surface (harness)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdash import __version__
from sdash.cli import build_parser, default_data_dir, main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_default_data_dir_honours_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("SDASH_DATA_DIR", str(tmp_path))
    assert default_data_dir() == tmp_path


def test_parser_knows_all_subcommands() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["segment", "add", "--name", "N", "--activity", "1", "--from-km", "1", "--to-km", "2"]
    )
    assert (args.command, args.segment_command, args.from_km) == ("segment", "add", 1.0)
    args = parser.parse_args(["refresh", "--no-deploy"])
    assert args.source is None and args.no_deploy is True


def test_import_strava_exit_codes(tmp_path: Path) -> None:
    from sdash.cli import main

    raw = tmp_path / "raw"
    raw.mkdir()
    header = "Segment Name,Activity ID,Starting Latitude,Starting Longitude,Ending Latitude,Ending Longitude\n"
    csv_path = raw / "segments.csv"
    csv_path.write_text(header + "Bad,1,95,0,1,1\n")
    assert main(["--data-dir", str(tmp_path), "segment", "import-strava"]) == 1
    csv_path.write_text(header + "Bad,1,95,0,1,1\nOk,2,0,0,1,1\n")
    assert main(["--data-dir", str(tmp_path), "segment", "import-strava"]) == 0
    csv_path.write_text(header + "Ok,2,0,0,1,1\n")  # all existing, none invalid
    assert main(["--data-dir", str(tmp_path), "segment", "import-strava"]) == 0
    csv_path.write_text(header + "Bad,1,95,0,1,1\nOk,2,0,0,1,1\n")  # invalid and nothing added
    assert main(["--data-dir", str(tmp_path), "segment", "import-strava"]) == 1


# --- T-013: exit code 2 = segment-level warnings --------------------------------------------------


def _data_with_bad_and_good_segment(tmp_path: Path) -> Path:
    from test_pipeline import _add_data, _seg_yaml

    data = _add_data(tmp_path)
    broken = '- name: "Broken"\n  ref_activity: "5"\n  start: [-47.0, -134.0]\n'
    (data / "segments.yaml").write_text(broken + _seg_yaml("Good", "5"))
    return data


def test_match_exits_2_with_warning_and_still_matches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _data_with_bad_and_good_segment(tmp_path)
    assert main(["--data-dir", str(data), "match"]) == 2
    out = capsys.readouterr().out
    assert "Good: 1 efforts" in out
    assert "warning" in out and "Broken" in out and "end" in out


def test_build_data_exits_2_and_writes_the_valid_segments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _data_with_bad_and_good_segment(tmp_path)
    out_dir = tmp_path / "site"
    assert main(["--data-dir", str(data), "build-data", "--out", str(out_dir)]) == 2
    assert [p.name for p in (out_dir / "segments").glob("*.json")] == ["good.json"]
    assert "Broken" in capsys.readouterr().out


def test_match_without_problems_exits_0(tmp_path: Path) -> None:
    from test_pipeline import _add_data, _seg_yaml

    data = _add_data(tmp_path)
    (data / "segments.yaml").write_text(_seg_yaml("Good", "5"))
    assert main(["--data-dir", str(data), "match"]) == 0


def test_unreadable_segments_yaml_exits_1(tmp_path: Path) -> None:
    from test_pipeline import _add_data

    data = _add_data(tmp_path)
    (data / "segments.yaml").write_text("- name: [unclosed\n")
    assert main(["--data-dir", str(data), "match"]) == 1


def test_refresh_and_build_data_print_warnings_after_the_wrote_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdash import cli

    data = _data_with_bad_and_good_segment(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)  # refresh stops before npm
    argv = [
        ["--data-dir", str(data), "build-data", "--out", str(tmp_path / "site")],
        ["--data-dir", str(data), "refresh", "--no-deploy", "--web-dir", str(tmp_path / "web")],
    ]
    for args in argv:
        main(args)
        out = capsys.readouterr().out
        assert "wrote " in out and "warning:" in out, (args, out)
        assert out.index("wrote ") < out.index("warning:"), (args, out)


def _fake_npm(
    monkeypatch: pytest.MonkeyPatch, web: Path, returncode: int = 0, leak: str = ""
) -> list:
    """Replace the npm subprocess: records the call, writes a tiny dist/ (plus an optional leak)."""
    import subprocess

    from sdash import cli

    calls: list = []

    def run(argv, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((argv, kwargs))
        if returncode == 0:
            (web / "dist").mkdir(parents=True, exist_ok=True)
            (web / "dist" / "index.html").write_text("<title>x</title>")
            if leak:
                (web / "dist" / leak).write_text("x")
        return subprocess.CompletedProcess(argv, returncode)

    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/fake/npm")
    monkeypatch.setattr(cli.subprocess, "run", run)
    return calls


def test_refresh_builds_with_fixed_argv_in_web_dir_and_backs_up_segments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_pipeline import _add_data

    data = _add_data(tmp_path)
    (data / "segments.yaml").write_text("[]\n")
    web = tmp_path / "web"
    web.mkdir()
    calls = _fake_npm(monkeypatch, web)
    assert main(["--data-dir", str(data), "refresh", "--no-deploy", "--web-dir", str(web)]) == 0
    assert calls == [(["/fake/npm", "run", "build"], {"cwd": web, "check": False})]
    assert len(list((data / "segments.bak").iterdir())) == 1


def test_refresh_site_build_failure_exits_1_and_skips_deploy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from test_pipeline import _add_data

    from sdash import deploy

    data = _add_data(tmp_path)
    (data / "segments.yaml").write_text("[]\n")
    web = tmp_path / "web"
    web.mkdir()
    _fake_npm(monkeypatch, web, returncode=1)
    monkeypatch.setattr(deploy, "deploy", lambda *a, **k: pytest.fail("deployed"))
    assert main(["--data-dir", str(data), "refresh", "--web-dir", str(web)]) == 1
    assert "site build failed" in capsys.readouterr().err


def test_refresh_guard_failure_exits_1_names_file_and_skips_deploy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from test_pipeline import _add_data

    from sdash import deploy

    data = _add_data(tmp_path)
    (data / "segments.yaml").write_text("[]\n")
    web = tmp_path / "web"
    web.mkdir()
    _fake_npm(monkeypatch, web, leak="leak.gpx")
    monkeypatch.setattr(deploy, "deploy", lambda *a, **k: pytest.fail("deployed"))
    assert main(["--data-dir", str(data), "refresh", "--web-dir", str(web)]) == 1
    assert "leak.gpx" in capsys.readouterr().err


def test_refresh_deploys_after_guard_and_keeps_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdash import deploy

    data = _data_with_bad_and_good_segment(tmp_path)
    web = tmp_path / "web"
    web.mkdir()
    _fake_npm(monkeypatch, web)
    deployed: list = []
    monkeypatch.setattr(deploy, "deploy", lambda w, r: deployed.append((w, r)))
    args = ["--data-dir", str(data), "refresh", "--web-dir", str(web), "--remote", "origin"]
    assert main(args) == 2
    assert deployed == [(web, "origin")]


def test_refresh_import_failure_stops_before_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "x.zip"
    bad.write_bytes(b"not a zip")
    web = tmp_path / "web"
    web.mkdir()
    calls = _fake_npm(monkeypatch, web)
    args = ["--data-dir", str(tmp_path / "d"), "refresh", str(bad), "--no-deploy"]
    assert main([*args, "--web-dir", str(web)]) == 1
    assert calls == [] and capsys.readouterr().err.startswith("sdash refresh:")


def test_deploy_command_runs_the_guard(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    web = tmp_path / "web"
    (web / "dist").mkdir(parents=True)
    (web / "dist" / "index.html").write_text("x")
    (web / "dist" / "leak.fit").write_text("x")
    assert main(["--data-dir", str(tmp_path), "deploy", "--web-dir", str(web)]) == 1
    assert "leak.fit" in capsys.readouterr().err


def test_refresh_backup_oserror_is_a_clean_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from test_pipeline import _add_data

    data = _add_data(tmp_path)
    (data / "segments.yaml").write_text("[]\n")
    (data / "segments.bak").write_text("a file, not a directory")
    web = tmp_path / "web"
    web.mkdir()
    calls = _fake_npm(monkeypatch, web)
    assert main(["--data-dir", str(data), "refresh", "--no-deploy", "--web-dir", str(web)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("sdash refresh: cannot back up segments.yaml") and calls == []


def test_refresh_flushes_stdout_before_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    from test_pipeline import _add_data

    data = _add_data(tmp_path)
    (data / "segments.yaml").write_text("[]\n")
    web = tmp_path / "web"
    web.mkdir()
    _fake_npm(monkeypatch, web)
    flushed: list[bool] = []
    monkeypatch.setattr(sys.stdout, "flush", lambda: flushed.append(True))
    main(["--data-dir", str(data), "refresh", "--no-deploy", "--web-dir", str(web)])
    assert flushed


def test_build_data_symlink_in_out_dir_is_one_line_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "link.json").symlink_to(tmp_path)
    assert main(["--data-dir", str(tmp_path / "d"), "build-data", "--out", str(out)]) == 1
    err = capsys.readouterr().err
    assert "symlink" in err and "Traceback" not in err and len(err.strip().splitlines()) == 1


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_build_data_unreadable_dir_in_out_is_one_line_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    (out / "locked").mkdir(parents=True)
    (out / "locked").chmod(0)
    try:
        assert main(["--data-dir", str(tmp_path / "d"), "build-data", "--out", str(out)]) == 1
    finally:
        (out / "locked").chmod(0o755)
    err = capsys.readouterr().err
    assert "Traceback" not in err and len(err.strip().splitlines()) == 1
