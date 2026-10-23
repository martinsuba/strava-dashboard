#!/usr/bin/env python3
"""REQ-010 guard: fail if raw ride/export data is tracked in Git outside tests/fixtures/.

Checks every path in the index (`git ls-files`), so it also catches files added with `git add -f`.
Run from the repository root: python3 scripts/check_raw_data.py
"""

from __future__ import annotations

import subprocess
import sys

RAW_SUFFIXES = (".fit", ".fit.gz", ".gpx", ".gpx.gz", ".tcx", ".tcx.gz", ".zip")
RAW_NAMES = ("activities.csv",)
ALLOWED_PREFIX = "tests/fixtures/"


def offending(paths: list[str]) -> list[str]:
    bad = []
    for path in paths:
        if path.startswith(ALLOWED_PREFIX):
            continue
        lower = path.lower()
        name = lower.rsplit("/", 1)[-1]
        if lower.endswith(RAW_SUFFIXES) or name in RAW_NAMES:
            bad.append(path)
    return bad


def main() -> int:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout.decode(
        "utf-8", errors="replace"
    )
    bad = offending([p for p in out.split("\0") if p])
    if bad:
        print("Raw ride/export data is tracked outside tests/fixtures/ (REQ-010):", file=sys.stderr)
        for path in bad:
            print(f"  {path}", file=sys.stderr)
        return 1
    print("raw-data check: OK (no raw ride/export files outside tests/fixtures/)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
