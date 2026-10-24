"""REQ-001: import a Strava export from a local zip or an https link.

The export is untrusted input and the download link is a credential for the whole account archive.
Rules enforced here:

* URL: https only (checked before any connection), no userinfo, host allowlist on the link and on
  every redirect hop (redirects are followed by hand, capped), TLS verification always on.
* The URL (path, query) is never printed, logged or put into an exception: only the host appears.
* Zip: the central directory is validated completely and the total size capped before anything is
  written; only allowlisted entries are extracted, streamed with a byte counter, into a staging dir
  that replaces `raw/` only after success.
"""

from __future__ import annotations

import http.client
import os
import re
import shutil
import ssl
import stat
import sys
import tempfile
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath

from sdash.pipeline import PipelineError

MAX_BYTES = 3 * 1000**3  # download cap and total uncompressed cap ("3 GB")
MAX_REDIRECTS = 5
TIMEOUT_S = 30.0
CHUNK = 1 << 20
PRODUCTION_HOSTS = ("strava.com", "amazonaws.com")
ALLOWED_FILES = frozenset(
    {"activities.csv", "segments.csv", "starred_segments.csv", "bikes.csv", "components.csv"}
)
ALLOWED_DIR = "activities"
_REDIRECT_STATUS = {301, 302, 303, 307, 308}
_DRIVE = re.compile(r"^[A-Za-z]:")


class ImportFailed(PipelineError):
    """Import problem; the message is safe to print (never contains the link)."""


# ---- host allowlist -----------------------------------------------------------------------
def _norm_host(host: str) -> str:
    return host.strip().lower().rstrip(".")


def _is_ip(host: str) -> bool:
    import ipaddress

    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def host_allowed(host: str, allowed: tuple[str, ...] | list[str]) -> bool:
    """Exact match or dot-boundary suffix match (`email.strava.com` matches `strava.com`,
    `evilstrava.com` does not). Case-insensitive, trailing dot ignored. IPs match exactly only."""
    h = _norm_host(host)
    if not h:
        return False
    for entry in allowed:
        a = _norm_host(entry)
        if not a:
            continue
        if h == a:
            return True
        if not _is_ip(h) and h.endswith("." + a):
            return True
    return False


def allowed_hosts() -> tuple[str, ...]:
    """Production list, or SDASH_ALLOWED_HOSTS (test hook; replaces only this list, warns)."""
    override = os.environ.get("SDASH_ALLOWED_HOSTS")
    if override is None:
        return PRODUCTION_HOSTS
    print(
        "warning: SDASH_ALLOWED_HOSTS is set: the import host allowlist is overridden "
        "(https-only, size caps and per-redirect checks still apply)",
        file=sys.stderr,
    )
    return tuple(h for h in (x.strip() for x in override.split(",")) if h)


# ---- URL handling -------------------------------------------------------------------------
def _check_url(url: str, hosts: tuple[str, ...]) -> tuple[str, int, str]:
    """Validate one hop; returns (host, port, request target). Errors never include the URL."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname
        port = parts.port or 443
    except ValueError:
        raise ImportFailed("invalid link (only https links are supported)") from None
    if parts.scheme.lower() != "https":
        raise ImportFailed("only https links are allowed (refusing non-https link)")
    if "@" in parts.netloc:
        raise ImportFailed("links with user info are not allowed")
    if not host:
        raise ImportFailed("invalid link: no host")
    if not host_allowed(host, hosts):
        raise ImportFailed(f"host {_norm_host(host)!r} is not in the allowed host list")
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    return host, port, target


def _ssl_context() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE")
    ctx = ssl.create_default_context(cafile=cafile if cafile else None)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def download(url: str, dest_dir: Path, hosts: tuple[str, ...] | None = None) -> Path:
    """Download to a private (0600) temp file in dest_dir. The caller must delete it."""
    hosts = allowed_hosts() if hosts is None else hosts
    current = url
    ctx = _ssl_context()
    for _hop in range(MAX_REDIRECTS + 1):
        host, port, target = _check_url(current, hosts)  # before any connection
        conn = http.client.HTTPSConnection(host, port, timeout=TIMEOUT_S, context=ctx)
        try:
            try:
                conn.request("GET", target, headers={"User-Agent": "sdash"})
                resp = conn.getresponse()
            except (OSError, http.client.HTTPException) as exc:
                raise ImportFailed(
                    f"download failed for host {_norm_host(host)!r}: {type(exc).__name__}"
                ) from None
            if resp.status in _REDIRECT_STATUS:
                location = resp.getheader("Location")
                if not location:
                    raise ImportFailed("redirect without a target")
                current = urllib.parse.urljoin(current, location)
                continue
            if resp.status != 200:
                raise ImportFailed(
                    f"download failed: host {_norm_host(host)!r} answered HTTP {resp.status}"
                )
            return _stream_to_file(resp, dest_dir, host)
        finally:
            conn.close()
    raise ImportFailed(f"too many redirects (more than {MAX_REDIRECTS})")


def _stream_to_file(resp: http.client.HTTPResponse, dest_dir: Path, host: str) -> Path:
    declared = resp.getheader("Content-Length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise ImportFailed(f"download size exceeds the limit of {MAX_BYTES} bytes")
    dest_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".download-", suffix=".zip.tmp", dir=dest_dir)
    path = Path(name)
    try:
        total = 0
        with os.fdopen(fd, "wb") as out:
            while True:
                try:
                    chunk = resp.read(CHUNK)
                except (OSError, http.client.HTTPException) as exc:
                    raise ImportFailed(
                        f"download failed for host {_norm_host(host)!r}: {type(exc).__name__}"
                    ) from None
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ImportFailed(f"download size exceeds the limit of {MAX_BYTES} bytes")
                out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


# ---- zip handling -------------------------------------------------------------------------
def _validate_name(name: str) -> None:
    def bad(why: str) -> ImportFailed:
        return ImportFailed(f"unsafe zip entry {name!r}: {why}")

    if "\x00" in name:
        raise bad("NUL byte")
    if "\\" in name:
        raise bad("backslash in path")
    if name.startswith("/"):
        raise bad("absolute path")
    if _DRIVE.match(name):
        raise bad("drive letter")
    if ".." in name.split("/"):
        raise bad("'..' path component")


def _validate_entries(infos: list[zipfile.ZipInfo]) -> None:
    seen: set[str] = set()
    total = 0
    for info in infos:
        _validate_name(info.filename)
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ImportFailed(f"unsafe zip entry {info.filename!r}: symlink or special file")
        key = str(PurePosixPath(info.filename.rstrip("/")))
        if key in seen:
            raise ImportFailed(f"unsafe zip entry {info.filename!r}: duplicate name")
        seen.add(key)
        total += info.file_size
    if total > MAX_BYTES:
        raise ImportFailed(
            f"export too large: uncompressed size {total} bytes exceeds the limit of {MAX_BYTES}"
        )


def is_allowed_entry(name: str) -> bool:
    if name in ALLOWED_FILES:
        return True
    prefix = ALLOWED_DIR + "/"
    return name.startswith(prefix) and not name.endswith("/") and len(name) > len(prefix)


def _extract(zf: zipfile.ZipFile, infos: list[zipfile.ZipInfo], staging: Path) -> int:
    budget = MAX_BYTES
    count = 0
    root = staging.resolve()
    for info in infos:
        if info.is_dir() or not is_allowed_entry(info.filename):
            continue
        target = (staging / info.filename).resolve()
        if root not in target.parents:
            raise ImportFailed(f"unsafe zip entry {info.filename!r}: escapes the target")
        target.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        try:
            with zf.open(info) as src, open(target, "xb") as out:
                while chunk := src.read(CHUNK):
                    written += len(chunk)
                    budget -= len(chunk)
                    if written > info.file_size or budget < 0:
                        raise ImportFailed(
                            f"zip entry {info.filename!r} is larger than declared "
                            f"(size limit {MAX_BYTES} bytes)"
                        )
                    out.write(chunk)
        except (zipfile.BadZipFile, OSError, EOFError, RuntimeError, NotImplementedError) as exc:
            raise ImportFailed(
                f"cannot extract zip entry {info.filename!r}: {type(exc).__name__}"
            ) from None
        count += 1
    return count


def import_zip(zip_path: Path, data_dir: Path) -> int:
    """Extract the allowlisted parts of zip_path into data_dir/raw (atomic replace)."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError):
        raise ImportFailed("not a readable zip file") from None
    with zf:
        infos = zf.infolist()
        _validate_entries(infos)  # nothing is written before this passes
        if not any(i.filename == "activities.csv" for i in infos):
            raise ImportFailed("not a Strava export: activities.csv is missing")
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging = Path(tempfile.mkdtemp(prefix=".raw-staging-", dir=data_dir))
        old: Path | None = None
        try:
            count = _extract(zf, infos, staging)
            raw = data_dir / "raw"
            if raw.exists():
                old = Path(tempfile.mkdtemp(prefix=".raw-old-", dir=data_dir))
                old.rmdir()
                raw.rename(old)
            try:
                staging.rename(raw)
            except OSError:
                if old is not None:
                    old.rename(raw)
                    old = None
                raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            if old is not None:
                shutil.rmtree(old, ignore_errors=True)
    return count


def import_source(source: str, data_dir: Path) -> int:
    """`sdash import <zip|https-url>`; returns the number of extracted files."""
    if "://" in source:
        hosts = allowed_hosts()
        _check_url(source, hosts)  # https/host check before touching the disk or network
        zip_path = download(source, data_dir, hosts)
        try:
            return import_zip(zip_path, data_dir)
        finally:
            zip_path.unlink(missing_ok=True)
    path = Path(source).expanduser()
    if not path.is_file():
        shown = "" if "?" in source else f": {source}"
        raise ImportFailed(f"zip file not found{shown}")
    return import_zip(path, data_dir)
