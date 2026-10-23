"""The synthetic activities.csv header must equal the exact header recorded in ARCHITECTURE.md."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs" / "ARCHITECTURE.md"


def _load_synth():  # type: ignore[no-untyped-def]
    path = ROOT / "tests" / "acceptance" / "pipeline" / "_synth.py"
    spec = importlib.util.spec_from_file_location("_synth_for_header_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ACTIVITIES_HEADER: list[str] = _load_synth().ACTIVITIES_HEADER


def _documented_header() -> list[str]:
    text = ARCH.read_text(encoding="utf-8")
    m = re.search(r"Exact `activities\.csv` header.*?\n\s*```\n(.*?)\n\s*```", text, re.S)
    assert m, "header block not found in ARCHITECTURE.md"
    return [c.strip() for c in m.group(1).replace("\n", " ").split(",") if c.strip()]


def test_header_block_is_103_columns() -> None:
    assert len(_documented_header()) == 103


def test_synth_header_equals_documented_header() -> None:
    assert _documented_header() == ACTIVITIES_HEADER


def test_duplicate_positions() -> None:
    h = ACTIVITIES_HEADER
    for name, first, second in [
        ("Elapsed Time", 5, 15),
        ("Distance", 6, 17),
        ("Max Heart Rate", 7, 30),
        ("Relative Effort", 8, 37),
        ("Commute", 9, 50),
    ]:
        assert h[first] == h[second] == name
        assert h.count(name) == 2
