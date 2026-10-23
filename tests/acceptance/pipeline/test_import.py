"""REQ-001: Import a Strava export (sdash import <zip|url>).

URL tests never use the network: they run a local HTTP(S) server on 127.0.0.1 in a thread.
HTTPS uses a throwaway CA generated with the `openssl` CLI and passed to sdash via
SSL_CERT_FILE / REQUESTS_CA_BUNDLE / CURL_CA_BUNDLE, and SDASH_ALLOWED_HOSTS=localhost replaces the
production host allowlist (*.strava.com, *.amazonaws.com) for the test only. See docs/TESTS.md.
"""

from __future__ import annotations

import shutil
import socket
import ssl
import struct
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import _scenarios as sc
import pytest
from _synth import ALLOWED_EXPORT_FILES, PERSONAL_FILES, export_files, write_zip
from conftest import SdashRunner

pytestmark = pytest.mark.req("REQ-001")
NOT_DONE = "REQ-001 not implemented (T-004)"


def _export(tmp_path: Path, name: str = "export.zip", **kw) -> tuple[Path, dict[str, bytes]]:
    rides = kw.pop("rides", None) or [sc.reference_ride(), sc.normal_with_stop()]
    files = export_files(rides, **kw)
    return write_zip(tmp_path / name, files), files


def _all_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req001_local_zip_keeps_only_ride_data(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path
) -> None:
    zip_path, files = _export(tmp_path)
    sdash("import", zip_path).ok()
    raw = data_dir / "raw"
    assert (raw / "activities.csv").read_bytes() == files["activities.csv"]
    assert (raw / "segments.csv").is_file()
    ride_files = {n for n in files if n.startswith("activities/")}
    assert {f"activities/{p.name}" for p in (raw / "activities").iterdir()} == ride_files
    top_level = {p.name for p in raw.iterdir()}
    assert top_level <= ALLOWED_EXPORT_FILES | {"activities"}, f"unexpected entries: {top_level}"
    personal_names = {Path(n).name for n in PERSONAL_FILES} | {"media"}
    leaked = [p for p in data_dir.rglob("*") if p.name in personal_names]
    assert not leaked, f"personal data kept: {leaked}"


UNSAFE = ["../evil-parent.txt", "../../evil-grandparent.txt", "activities/../../../evil-sneaky.fit"]


@pytest.mark.parametrize("entry", [*UNSAFE, "ABSOLUTE"])
@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req001_unsafe_zip_entry_rejected(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path, entry: str
) -> None:
    if entry == "ABSOLUTE":
        entry = str(tmp_path / "evil-absolute.txt")
    files = export_files([sc.reference_ride()])
    files[entry] = b"must never be written"
    zip_path = write_zip(tmp_path / "export.zip", files)
    result = sdash("import", zip_path)
    assert result.returncode != 0, "zip with an escaping entry was accepted"
    assert "not implemented" not in result.output
    assert "evil" in result.output, f"error must name the offending entry:\n{result.output}"
    written = [p for p in tmp_path.rglob("evil*")]
    assert not written, f"wrote files from unsafe entries: {written}"


def _forge_uncompressed_size(zip_path: Path, entry: str, size: int) -> None:
    """Patch the central-directory 'uncompressed size' of one entry (no real 3 GB needed)."""
    data = bytearray(zip_path.read_bytes())
    pos = 0
    while (pos := data.find(b"PK\x01\x02", pos)) != -1:
        name_len = struct.unpack_from("<H", data, pos + 28)[0]
        if data[pos + 46 : pos + 46 + name_len].decode() == entry:
            struct.pack_into("<I", data, pos + 24, size)
            zip_path.write_bytes(bytes(data))
            return
        pos += 4
    raise AssertionError(f"{entry} not found in central directory")


@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req001_oversized_zip_fails_before_extracting(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path
) -> None:
    files = export_files([sc.reference_ride()])
    files["activities/huge-1.fit"] = b"x" * 100
    files["activities/huge-2.fit"] = b"y" * 100
    zip_path = write_zip(tmp_path / "export.zip", files)
    # 2 x 1.75 GB: each entry is below 3 GB, the total is above.
    _forge_uncompressed_size(zip_path, "activities/huge-1.fit", 1_750_000_000)
    _forge_uncompressed_size(zip_path, "activities/huge-2.fit", 1_750_000_000)
    result = sdash("import", zip_path)
    assert result.returncode != 0
    assert "not implemented" not in result.output
    assert any(w in result.output.lower() for w in ("size", "large", "limit", "exceed")), (
        result.output
    )
    assert not _all_files(data_dir), f"extracted before checking the size: {_all_files(data_dir)}"


class _CountingServer:
    """Accepts TCP connections on 127.0.0.1 and counts them (any scheme)."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.connections = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except TimeoutError:
                continue
            self.connections += 1
            conn.close()

    def close(self) -> None:
        self._stop.set()
        self._thread.join()
        self.sock.close()


@pytest.mark.parametrize("scheme", ["http", "ftp", "file"])
@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req001_non_https_url_rejected_without_request(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path, scheme: str
) -> None:
    zip_path, _ = _export(tmp_path)
    server = _CountingServer()
    try:
        url = (
            f"file://{zip_path}"
            if scheme == "file"
            else f"{scheme}://127.0.0.1:{server.port}/export.zip?token=x"
        )
        result = sdash("import", url)
    finally:
        server.close()
    assert result.returncode != 0, f"{scheme} URL accepted"
    assert "not implemented" not in result.output
    assert "https" in result.output.lower(), (
        f"error should say only https is allowed:\n{result.output}"
    )
    assert server.connections == 0, "a network request was made for a non-https URL"
    assert not (data_dir / "raw" / "activities.csv").exists()


# ---- local HTTPS server -------------------------------------------------------------------
SECRET = "SYNTHETIC-SECRET-TOKEN-4242"


def _make_ca_and_cert(d: Path) -> tuple[Path, Path, Path]:
    if shutil.which("openssl") is None:
        pytest.skip("openssl CLI not available")
    ca_key, ca, key, csr, cert, ext = (
        d / n for n in ("ca.key", "ca.pem", "srv.key", "srv.csr", "srv.pem", "ext.cnf")
    )
    ext.write_text(
        "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\nsubjectAltName=DNS:localhost,IP:127.0.0.1\n"
        "authorityKeyIdentifier=keyid\nsubjectKeyIdentifier=hash\n"
    )
    run = lambda *a: subprocess.run(["openssl", *a], check=True, capture_output=True)  # noqa: E731
    run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(ca_key), "-out", str(ca),
        "-days", "2", "-subj", "/CN=sdash test CA", "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign")  # fmt: skip
    run(
        "req",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(key),
        "-out",
        str(csr),
        "-subj",
        "/CN=localhost",
    )
    run("x509", "-req", "-in", str(csr), "-CA", str(ca), "-CAkey", str(ca_key), "-CAcreateserial",
        "-out", str(cert), "-days", "2", "-extfile", str(ext))  # fmt: skip
    return ca, cert, key


@contextmanager
def https_export_server(tmp_path: Path, payload: bytes) -> Iterator[tuple[str, list[str], Path]]:
    """Serves the email-link shape: /ls/click?token=... -> 302 -> /bucket/export.zip?X-Amz-Signature=..."""
    ca, cert, key = _make_ca_and_cert(tmp_path)
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append(self.path)
            if self.path.startswith("/ls/click"):
                self.send_response(302)
                self.send_header(
                    "Location",
                    f"https://localhost:{port}/bucket/export.zip?X-Amz-Signature={SECRET}",
                )
                self.end_headers()
            elif self.path.startswith("/bucket/export.zip"):
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_error(404)

        def log_message(self, *args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://localhost:{port}/ls/click?upn={SECRET}", requests, ca
    finally:
        httpd.shutdown()
        thread.join()


def _https_env(ca: Path) -> dict[str, str]:
    return {
        "SSL_CERT_FILE": str(ca),
        "REQUESTS_CA_BUNDLE": str(ca),
        "CURL_CA_BUNDLE": str(ca),
        "SDASH_ALLOWED_HOSTS": "localhost",
    }


@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req001_downloaded_zip_deleted_after_import(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path, base_env: dict[str, str]
) -> None:
    files = export_files([sc.reference_ride(), sc.normal_with_stop()])
    served = write_zip(tmp_path / "served.zip", files)
    payload = served.read_bytes()
    served.unlink()  # from here on, any zip under tmp_path was left behind by sdash
    with https_export_server(tmp_path, payload) as (url, requests, ca):
        result = sdash("import", url, env=_https_env(ca)).ok()
    assert any(r.startswith("/bucket/export.zip") for r in requests), (
        f"zip not downloaded: {requests}"
    )
    assert (data_dir / "raw" / "activities.csv").read_bytes() == files["activities.csv"]
    zips = [p for p in tmp_path.rglob("*") if p.is_file() and p.read_bytes()[:4] == b"PK\x03\x04"]
    assert not zips, f"downloaded zip not deleted: {zips}"
    reports = "".join(p.read_text(errors="replace") for p in _all_files(data_dir / "reports"))
    assert SECRET not in result.output + reports, "the export link (a credential) was logged"


@pytest.mark.xfail(strict=True, reason=NOT_DONE)
def test_req001_newer_export_replaces_old_ride_files(
    sdash: SdashRunner, data_dir: Path, tmp_path: Path
) -> None:
    old_b = sc.ride("1000000082", [(0, 0), (0, 1000)], day=2)
    new_b = sc.ride("1000000082", [(0, 0), (0, 1500)], day=2)
    a = sc.ride("1000000081", [(0, 0), (0, 800)], day=1)
    c = sc.ride("1000000083", [(0, 0), (0, 900)], day=3)
    zip1, _ = _export(tmp_path, "export-1.zip", rides=[a, old_b])
    zip2, files2 = _export(tmp_path, "export-2.zip", rides=[a, new_b, c])
    assert files2[new_b.activity.filename] != export_files([old_b])[old_b.activity.filename]
    sdash("import", zip1).ok()
    sdash("import", zip2).ok()
    raw = data_dir / "raw"
    assert (raw / "activities.csv").read_bytes() == files2["activities.csv"]
    on_disk = {f"activities/{p.name}": p.read_bytes() for p in (raw / "activities").iterdir()}
    assert on_disk == {n: b for n, b in files2.items() if n.startswith("activities/")}
