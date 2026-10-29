"""D-008: build-info.json marker and digest rule."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from sdash import buildinfo
from sdash.buildinfo import BuildInfoError


def _data(root: Path) -> Path:
    data = root / "data"
    (data / "rides").mkdir(parents=True)
    (data / "index.json").write_text('{"a": 1}')
    (data / "rides" / "1.json").write_text("{}")
    return data


def test_digest_rule_is_sorted_path_nul_bytes_nul(tmp_path: Path) -> None:
    data = _data(tmp_path)
    h = hashlib.sha256()
    h.update(b"index.json\0" + b'{"a": 1}' + b"\0")
    h.update(b"rides/1.json\0" + b"{}" + b"\0")
    # sorted by relative POSIX path: "index.json" < "rides/1.json"
    assert buildinfo.compute_digest(data) == h.hexdigest()


def test_write_then_verify_ok_and_marker_content(tmp_path: Path) -> None:
    data = _data(tmp_path)
    buildinfo.write(data)
    info = json.loads((data / "build-info.json").read_text())
    assert info == {"source": "sdash build-data", "data_sha256": buildinfo.compute_digest(data)}
    buildinfo.verify(data)
    buildinfo.write(data)  # rewriting ignores the old marker
    buildinfo.verify(data)


def test_missing_marker(tmp_path: Path) -> None:
    with pytest.raises(BuildInfoError, match=r"no build-info.json: web/dist was not built from"):
        buildinfo.verify(_data(tmp_path))


def test_missing_data_dir(tmp_path: Path) -> None:
    with pytest.raises(BuildInfoError, match=r"no build-info.json"):
        buildinfo.verify(tmp_path / "data")


@pytest.mark.parametrize(
    "content",
    [b"not json", b"\xff\xfe\x00", b"[]", b"{}", b'{"source": "sdash build-data"}', b"x" * 100_000],
)
def test_garbled_marker_fails_closed(tmp_path: Path, content: bytes) -> None:
    data = _data(tmp_path)
    (data / "build-info.json").write_bytes(content)
    with pytest.raises(BuildInfoError, match=r"build-info.json"):
        buildinfo.verify(data)


def test_marker_that_is_a_directory(tmp_path: Path) -> None:
    data = _data(tmp_path)
    (data / "build-info.json").mkdir()
    with pytest.raises(BuildInfoError, match=r"build-info.json"):
        buildinfo.verify(data)


def test_changed_file_is_refused(tmp_path: Path) -> None:
    data = _data(tmp_path)
    buildinfo.write(data)
    (data / "index.json").write_text('{"a": 2}')
    with pytest.raises(BuildInfoError, match="data changed after build-data"):
        buildinfo.verify(data)


def test_extra_file_added_is_refused(tmp_path: Path) -> None:
    data = _data(tmp_path)
    buildinfo.write(data)
    (data / "extra.json").write_text("{}")
    with pytest.raises(BuildInfoError, match="data changed after build-data"):
        buildinfo.verify(data)


def test_removed_file_is_refused(tmp_path: Path) -> None:
    data = _data(tmp_path)
    buildinfo.write(data)
    (data / "rides" / "1.json").unlink()
    with pytest.raises(BuildInfoError, match="data changed after build-data"):
        buildinfo.verify(data)


def test_wrong_source_with_right_digest_is_refused(tmp_path: Path) -> None:
    data = _data(tmp_path)
    digest = buildinfo.compute_digest(data)
    (data / "build-info.json").write_text(json.dumps({"source": "other", "data_sha256": digest}))
    with pytest.raises(BuildInfoError, match="source"):
        buildinfo.verify(data)


def test_marker_in_subdirectory_counts_as_data(tmp_path: Path) -> None:
    data = _data(tmp_path)
    buildinfo.write(data)
    (data / "rides" / "build-info.json").write_text("{}")
    with pytest.raises(BuildInfoError, match="data changed after build-data"):
        buildinfo.verify(data)


def test_symlinks_are_refused(tmp_path: Path) -> None:
    data = _data(tmp_path)
    buildinfo.write(data)
    (data / "link.json").symlink_to(data / "index.json")
    with pytest.raises(BuildInfoError, match="symlink"):
        buildinfo.verify(data)


def test_digest_depends_on_sorted_order_not_walk_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    files = {"a.json": b"1", "b.json": b"2", "x/1.json": b"3", "x/2.json": b"4", "y/1.json": b"5"}
    for rel, content in files.items():
        (data / rel).parent.mkdir(parents=True, exist_ok=True)
        (data / rel).write_bytes(content)
    real_walk = os.walk

    def reversed_walk(top: Path, **kw: object):  # type: ignore[no-untyped-def]
        for root, dirs, names in real_walk(top, **kw):  # type: ignore[call-overload]
            dirs.reverse()  # os.walk honours in-place changes: subdirectories visited reversed
            yield root, dirs, list(reversed(names))

    monkeypatch.setattr(buildinfo.os, "walk", reversed_walk)
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode() + b"\0" + files[rel] + b"\0")
    assert buildinfo.compute_digest(data) == h.hexdigest()


def test_oversized_valid_json_marker_is_refused(tmp_path: Path) -> None:
    data = _data(tmp_path)
    digest = buildinfo.compute_digest(data)
    marker = {"source": buildinfo.SOURCE, "data_sha256": digest, "pad": "x" * 5000}
    (data / "build-info.json").write_text(json.dumps(marker))
    with pytest.raises(BuildInfoError, match=r"unreadable"):
        buildinfo.verify(data)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_unreadable_subdirectory_fails_closed(tmp_path: Path) -> None:
    data = _data(tmp_path)
    buildinfo.write(data)
    (data / "rides").chmod(0)
    try:
        with pytest.raises(BuildInfoError, match=r"cannot read"):
            buildinfo.verify(data)
    finally:
        (data / "rides").chmod(0o755)
