"""Unit tests for sdash.importer (REQ-001): host matching, URL checks, zip safety."""

from __future__ import annotations

import os
import shutil
import socket
import ssl
import stat
import subprocess
import threading
import time
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


# --- T-014: hardening -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "order", [("activities/a", "activities/a/b"), ("activities/a/b", "activities/a")]
)
def test_file_directory_clash_names_the_entry(tmp_path: Path, order: tuple[str, str]) -> None:
    zpath = make_zip(
        tmp_path / "z.zip", {"activities.csv": b"id\n", order[0]: b"1", order[1]: b"2"}
    )
    with pytest.raises(ImportFailed, match=r"activities/a"):
        importer.import_zip(zpath, tmp_path / "data")
    assert not (tmp_path / "data" / "raw").exists()


def test_entry_count_is_capped_before_anything_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(importer, "MAX_ENTRIES", 2)
    zpath = make_zip(tmp_path / "z.zip", {**GOOD, "activities/2.gpx": b"x"})
    with pytest.raises(ImportFailed, match=r"too many entries"):
        importer.import_zip(zpath, tmp_path / "data")
    assert not (tmp_path / "data").exists()
    zpath = make_zip(tmp_path / "ok.zip", GOOD)
    assert importer.import_zip(zpath, tmp_path / "data") == 2


def test_existing_data_dir_is_made_private(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir(mode=0o755)
    data.chmod(0o755)
    importer.import_zip(make_zip(tmp_path / "z.zip", GOOD), data)
    assert stat.S_IMODE(data.stat().st_mode) == 0o700


def test_stale_importer_leftovers_are_removed_on_start_and_nothing_else(tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / ".raw-staging-abc" / "activities").mkdir(parents=True)
    (data / ".raw-staging-abc" / "activities" / "x").write_bytes(b"x")
    (data / ".raw-old-xyz").mkdir()
    (data / ".download-q1.zip.tmp").write_bytes(b"partial")
    keep = [".download-other.txt", ".raw-staging", "raw-old-x", "segments.yaml", "cache", ".rawx"]
    for name in keep:
        (data / name).write_bytes(b"k")
    (data / "other").mkdir()
    (data / "other" / ".raw-old-inner").mkdir()
    importer.import_source(str(make_zip(tmp_path / "z.zip", GOOD)), data)
    left = sorted(p.name for p in data.iterdir())
    assert left == sorted([*keep, "other", "raw"])
    assert (data / "other" / ".raw-old-inner").is_dir()


class _SlowResp:
    status = 200

    def __init__(self, clock: list[float]) -> None:
        self.clock = clock

    def getheader(self, name: str) -> str | None:
        return None

    def read1(self, n: int) -> bytes:
        self.clock[0] += 10.0  # every chunk "takes" ten seconds
        return b"x" * 16


def test_download_deadline_aborts_and_deletes_the_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(importer.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(importer, "DEADLINE_S", 35.0)
    with pytest.raises(ImportFailed, match=r"time limit"):
        importer._stream_to_file(_SlowResp(clock), tmp_path, "strava.com", clock[0] + 35.0)  # type: ignore[arg-type]
    assert list(tmp_path.iterdir()) == []


def test_download_computes_the_deadline_from_the_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [0.0]
    monkeypatch.setattr(importer.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(importer, "DEADLINE_S", 25.0)

    class Conn:
        def __init__(self, *a: object, **k: object) -> None: ...
        def request(self, *a: object, **k: object) -> None: ...
        def close(self) -> None: ...
        def getresponse(self) -> _SlowResp:
            return _SlowResp(clock)

    monkeypatch.setattr(importer.http.client, "HTTPSConnection", Conn)
    with pytest.raises(ImportFailed, match=r"time limit"):
        importer.download("https://strava.com/a?t=SECRETX", tmp_path)
    assert list(tmp_path.iterdir()) == []


# --- T-014 review round 1: real HTTPS server, slow-drip bounds, import lock ----------------------


@pytest.fixture
def tls_cert(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    if shutil.which("openssl") is None:
        pytest.skip("openssl CLI not available")
    d = tmp_path_factory.mktemp("tls")
    cert, key = d / "cert.pem", d / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
         "-out", str(cert), "-days", "2", "-subj", "/CN=localhost",
         "-addext", "subjectAltName=IP:127.0.0.1"],
        check=True, capture_output=True,
    )  # fmt: skip
    return cert, key


def _drip_server(cert: Path, key: Path, mode: str) -> int:
    """HTTPS server on 127.0.0.1 that sends 1 byte per 0.2 s for 8 s (body or header)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)

    def serve() -> None:
        try:
            conn, _ = srv.accept()
            tls = ctx.wrap_socket(conn, server_side=True)
            tls.recv(4096)
            if mode == "body":
                tls.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000000\r\n\r\n")
                payload = b"x" * 40
            else:
                payload = b"HTTP/1.1 200 OK\r\nX-Pad: " + b"a" * 30
            for ch in payload:
                tls.sendall(bytes([ch]))
                time.sleep(0.2)
            tls.close()
        except OSError:
            pass  # the client gave up: expected
        finally:
            srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return int(srv.getsockname()[1])


@pytest.mark.parametrize("mode", ["body", "header"])
def test_slow_drip_server_is_cut_off_at_the_deadline(
    tmp_path: Path, tls_cert: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    port = _drip_server(*tls_cert, mode)
    monkeypatch.setenv("SSL_CERT_FILE", str(tls_cert[0]))
    monkeypatch.setattr(importer, "DEADLINE_S", 1.0)
    out = tmp_path / "out"
    started = time.monotonic()
    with pytest.raises(ImportFailed, match=r"time limit"):
        importer.download(f"https://127.0.0.1:{port}/x", out, ("127.0.0.1",))
    assert time.monotonic() - started < 3.0, "the deadline must bound the whole download"
    assert not out.exists() or list(out.iterdir()) == []


def test_handshake_stall_is_cut_off_at_the_deadline(
    tmp_path: Path, tls_cert: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    held: list[socket.socket] = []
    threading.Thread(target=lambda: held.append(srv.accept()[0]), daemon=True).start()
    monkeypatch.setenv("SSL_CERT_FILE", str(tls_cert[0]))
    monkeypatch.setattr(importer, "DEADLINE_S", 1.0)
    started = time.monotonic()
    with pytest.raises(ImportFailed, match=r"time limit"):
        importer.download(
            f"https://127.0.0.1:{srv.getsockname()[1]}/x", tmp_path / "o", ("127.0.0.1",)
        )
    assert time.monotonic() - started < 3.0
    srv.close()
    for h in held:
        h.close()


def test_duration_text_uses_seconds_below_a_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    assert importer._duration_text(1.0) == "1 second"
    assert importer._duration_text(45.0) == "45 seconds"
    assert importer._duration_text(1800.0) == "30 minutes"


def test_a_held_import_lock_refuses_a_second_import_and_keeps_its_files(tmp_path: Path) -> None:
    import fcntl

    data = tmp_path / "data"
    data.mkdir(mode=0o700)
    (data / ".download-live.zip.tmp").write_bytes(b"in progress")
    (data / ".raw-staging-live").mkdir()
    fd = os.open(data, os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        zpath = make_zip(tmp_path / "z.zip", GOOD)
        with pytest.raises(ImportFailed, match="another import is running"):
            importer.import_source(str(zpath), data)
        assert (data / ".download-live.zip.tmp").exists()
        assert (data / ".raw-staging-live").is_dir()
    finally:
        os.close(fd)
    importer.import_source(str(zpath), data)  # lock released: works, and cleans the leftovers
    assert not (data / ".download-live.zip.tmp").exists()
    assert not (data / ".import.lock").exists()
