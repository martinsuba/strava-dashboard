"""Scaffolding unit tests for the CLI surface (harness)."""

from __future__ import annotations

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
