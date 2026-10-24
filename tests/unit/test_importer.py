"""Unit tests for sdash.importer (REQ-001): host matching, URL checks, zip safety."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from sdash import importer
from sdash.cli import main
from sdash.importer import ImportFailed, host_allowed

PROD = importer.PRODUCTION_HOSTS


@pytest.mark.parametrize(
    ("host", "allowed", "expected"),
    [
        ("strava.com", PROD, True),
        ("email.strava.com", PROD, True),
        ("s3.amazonaws.com", PROD, True),
        ("EMAIL.Strava.COM", PROD, True),
        ("strava.com.", PROD, True),
        ("evilstrava.com", PROD, False),
        ("strava.com.evil.org", PROD, False),
        ("com", PROD, False),
        ("", PROD, False),
        ("localhost", ("calhost",), False),
        ("localhost", ("localhost",), True),
        ("127.0.0.1", ("7.0.0.1",), False),
        ("127.0.0.1", ("127.0.0.1",), True),
        ("localhost", ("LocalHost.",), True),
    ],
)
def test_host_matching(host: str, allowed: tuple[str, ...], expected: bool) -> None:
    assert host_allowed(host, allowed) is expected


def test_override_env_replaces_only_hosts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SDASH_ALLOWED_HOSTS", "a.test, b.test")
    assert importer.allowed_hosts() == ("a.test", "b.test")
    assert "SDASH_ALLOWED_HOSTS" in capsys.readouterr().err
    with pytest.raises(ImportFailed, match="https"):
        importer._check_url("http://a.test/x", ("a.test",))


@pytest.mark.parametrize(
    "url", ["http://strava.com/x", "ftp://strava.com/x", "file:///etc/passwd", "strava.com://x"]
)
def test_non_https_rejected(url: str) -> None:
    with pytest.raises(ImportFailed, match="https"):
        importer._check_url(url, PROD)


def test_userinfo_and_bad_host_rejected_without_leaking() -> None:
    with pytest.raises(ImportFailed, match="user info"):
        importer._check_url("https://strava.com@evil.org/p?token=SECRETX", PROD)
    with pytest.raises(ImportFailed) as exc:
        importer._check_url("https://evil.org/p/SECRETPATH?token=SECRETX", PROD)
    assert "SECRET" not in str(exc.value)
    assert "evil.org" in str(exc.value)


def test_redirect_to_disallowed_host_and_hop_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    connections: list[str] = []

    class FakeResp:
        def __init__(self, location: str) -> None:
            self.status = 302
            self._loc = location

        def getheader(self, name: str) -> str | None:
            return self._loc if name == "Location" else None

    class FakeConn:
        def __init__(self, host: str, *a: object, **k: object) -> None:
            self.host = host
            connections.append(host)

        def request(self, *a: object, **k: object) -> None: ...
        def close(self) -> None: ...

        def getresponse(self) -> FakeResp:
            return FakeResp(NEXT[0])

    monkeypatch.setattr(importer.http.client, "HTTPSConnection", FakeConn)
    NEXT = ["https://evil.org/zip?sig=SECRETX"]
    with pytest.raises(ImportFailed, match="not in the allowed") as exc:
        importer.download("https://strava.com/a?t=SECRETX", tmp_path)
    assert connections == ["strava.com"]
    assert "SECRETX" not in str(exc.value)

    connections.clear()
    NEXT[0] = "https://s3.amazonaws.com/loop?sig=SECRETX"
    with pytest.raises(ImportFailed, match="too many redirects"):
        importer.download("https://strava.com/a?t=SECRETX", tmp_path)
    assert len(connections) == importer.MAX_REDIRECTS + 1
    assert list(tmp_path.iterdir()) == []


# ---- zip ----------------------------------------------------------------------------------
def make_zip(path: Path, files: dict[str, bytes], symlinks: tuple[str, ...] = ()) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
        for name in symlinks:
            zi = zipfile.ZipInfo(name)
            zi.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(zi, "/etc/passwd")
    return path


GOOD = {"activities.csv": b"id\n", "activities/1.gpx": b"<gpx/>"}


def tree(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "name",
    ["../x.txt", "a/../../x", "/abs.txt", "C:/x.txt", "activities\\x.fit", "a/b\\..\\c"],
)
def test_unsafe_names_rejected_and_nothing_written(tmp_path: Path, name: str) -> None:
    z = make_zip(tmp_path / "e.zip", {**GOOD, name: b"x"})
    data = tmp_path / "data"
    with pytest.raises(ImportFailed) as exc:
        importer.import_zip(z, data)
    assert name in str(exc.value) or repr(name) in str(exc.value)
    assert not data.exists()


def test_symlink_entry_rejected(tmp_path: Path) -> None:
    z = make_zip(tmp_path / "e.zip", GOOD, symlinks=("activities/link.fit",))
    with pytest.raises(ImportFailed, match=r"link\.fit"):
        importer.import_zip(z, tmp_path / "data")
    assert not (tmp_path / "data").exists()


def test_duplicate_names_rejected(tmp_path: Path) -> None:
    z = tmp_path / "e.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("activities.csv", b"a")
        with pytest.warns(UserWarning):
            zf.writestr("activities.csv", b"b")
    with pytest.raises(ImportFailed, match="duplicate"):
        importer.import_zip(z, tmp_path / "data")


def test_total_size_cap_before_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importer, "MAX_BYTES", 10)
    z = make_zip(tmp_path / "e.zip", {"activities.csv": b"123456", "activities/a.fit": b"123456"})
    with pytest.raises(ImportFailed, match="limit"):
        importer.import_zip(z, tmp_path / "data")
    assert not (tmp_path / "data").exists()


def test_lying_declared_size_fails_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    z = make_zip(tmp_path / "e.zip", {"activities.csv": b"x" * 50})
    real = zipfile.ZipFile.infolist

    def lying(self: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
        infos = real(self)
        for i in infos:
            i.file_size = 1
        return infos

    monkeypatch.setattr(zipfile.ZipFile, "infolist", lying)
    data = tmp_path / "data"
    with pytest.raises(ImportFailed, match=r"activities\.csv"):
        importer.import_zip(z, data)
    assert tree(data) == set()  # no raw/, no staging leftovers


def test_extract_counter_rejects_more_than_declared(tmp_path: Path) -> None:
    class Src:
        def __init__(self) -> None:
            self.n = 0

        def read(self, n: int) -> bytes:
            self.n += 1
            return b"x" * 10 if self.n < 5 else b""

        def __enter__(self) -> Src:
            return self

        def __exit__(self, *a: object) -> None: ...

    class FakeZip:
        def open(self, info: zipfile.ZipInfo) -> Src:
            return Src()

    info = zipfile.ZipInfo("activities.csv")
    info.file_size = 15
    staging = tmp_path / "st"
    staging.mkdir()
    with pytest.raises(ImportFailed, match="larger than declared"):
        importer._extract(FakeZip(), [info], staging)  # type: ignore[arg-type]


def test_allowlist_filtering(tmp_path: Path) -> None:
    files = {
        **GOOD,
        "segments.csv": b"s",
        "bikes.csv": b"b",
        "media/photo.jpg": b"m",
        "messages.csv": b"m",
        "contacts.csv": b"c",
        "routes/r.gpx": b"r",
        "activities/": b"",
        "activitiesX/1.fit": b"x",
    }
    data = tmp_path / "data"
    importer.import_zip(make_zip(tmp_path / "e.zip", files), data)
    assert tree(data) == {
        "raw/activities.csv",
        "raw/activities/1.gpx",
        "raw/segments.csv",
        "raw/bikes.csv",
    }
    assert [p.name for p in data.iterdir()] == ["raw"]


def test_failed_import_keeps_old_raw(tmp_path: Path) -> None:
    data = tmp_path / "data"
    importer.import_zip(make_zip(tmp_path / "old.zip", GOOD), data)
    bad = make_zip(tmp_path / "bad.zip", {**GOOD, "../evil": b"x"})
    with pytest.raises(ImportFailed):
        importer.import_zip(bad, data)
    assert tree(data) == {"raw/activities.csv", "raw/activities/1.gpx"}
    # failure during extraction (after staging exists) also keeps raw/ and leaves no staging
    z = make_zip(tmp_path / "new.zip", {"activities.csv": b"new", "activities/2.gpx": b"y"})
    real_extract = importer._extract

    def boom(*a: object, **k: object) -> int:
        real_extract(*a, **k)  # type: ignore[arg-type]
        raise ImportFailed("boom")

    importer._extract = boom  # type: ignore[assignment]
    try:
        with pytest.raises(ImportFailed):
            importer.import_zip(z, data)
    finally:
        importer._extract = real_extract
    assert tree(data) == {"raw/activities.csv", "raw/activities/1.gpx"}


def test_reimport_replaces_old_files(tmp_path: Path) -> None:
    data = tmp_path / "data"
    importer.import_zip(make_zip(tmp_path / "1.zip", GOOD), data)
    importer.import_zip(make_zip(tmp_path / "2.zip", {"activities.csv": b"n"}), data)
    assert tree(data) == {"raw/activities.csv"}


def test_missing_and_corrupt_zip(tmp_path: Path) -> None:
    with pytest.raises(ImportFailed, match="not found"):
        importer.import_source(str(tmp_path / "nope.zip"), tmp_path / "d")
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(ImportFailed, match="zip"):
        importer.import_source(str(bad), tmp_path / "d")


def test_url_never_in_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SDASH_ALLOWED_HOSTS", raising=False)
    for url in (
        "https://evil.example/ls/click?upn=SECRETX",
        "http://strava.com/ls/click?upn=SECRETX",
        "https://user:pw@strava.com/ls?upn=SECRETX",
        "https://[bad/ls?upn=SECRETX",
    ):
        assert main(["--data-dir", str(tmp_path / "d"), "import", url]) == 1
        cap = capsys.readouterr()
        assert "SECRETX" not in cap.out + cap.err
        assert "upn" not in cap.out + cap.err
