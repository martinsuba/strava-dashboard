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
