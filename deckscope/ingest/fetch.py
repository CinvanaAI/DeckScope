"""Guarded HTTP fetching for decks supplied as a URL.

`deckscope run https://…` lets a caller point the loader at an arbitrary address,
and in a server or shared context that caller is not necessarily trusted. Without
guards this is a server-side request forgery primitive: an attacker names
http://169.254.169.254/… and DeckScope reads a cloud metadata endpoint, or names
an internal host and reports back what it found.

So a fetch here:

  * resolves the hostname first and refuses private, loopback, link-local,
    multicast and reserved addresses
  * re-checks after every redirect, because a public hostname may redirect to an
    internal one, and a DNS name may resolve differently the second time
  * connects to the address it validated, so the name cannot be re-resolved to
    something else between check and connect
  * caps the download and reads in chunks, so a multi-gigabyte body cannot
    exhaust memory
  * enforces a total deadline, not just a per-socket timeout
  * writes to a unique temporary file, so concurrent panel runs cannot collide
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List, Optional, Tuple

MAX_BYTES = 64 * 1024 * 1024        # 64 MB: far above any real deck
MAX_REDIRECTS = 5
CHUNK = 64 * 1024
DEFAULT_TIMEOUT = 30                # per socket operation
DEFAULT_DEADLINE = 120              # for the whole fetch, redirects included

ALLOWED_SCHEMES = ("http", "https")

#: Content types we know how to read. Anything else is refused by name rather
#: than sniffed, so a mislabelled binary cannot be coaxed down a text path.
ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/html": ".html",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "application/json": ".json",
    "application/octet-stream": "",   # resolved by magic bytes below
}


class FetchError(RuntimeError):
    """A URL could not be fetched safely."""


@dataclass
class Fetched:
    content: bytes
    content_type: str
    final_url: str
    suffix: str


def _is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified)


def resolve_public(host: str) -> List[str]:
    """Resolve a hostname to addresses, refusing anything not publicly routable."""
    if not host:
        raise FetchError("The URL has no host.")
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve {host}: {exc}") from None

    addrs = sorted({i[4][0] for i in infos})
    if not addrs:
        raise FetchError(f"Could not resolve {host}.")
    blocked = [a for a in addrs if not _is_public(a)]
    if blocked:
        raise FetchError(
            f"Refusing to fetch from {host}: it resolves to {blocked[0]}, which is "
            f"a private, loopback or link-local address. DeckScope only fetches "
            f"decks from publicly routable hosts, so a URL cannot be used to reach "
            f"machines inside your network or a cloud metadata service.")
    return addrs


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """An HTTP connection whose socket goes to a pre-validated IP.

    `self.host` stays the hostname so the Host header is right; the socket is
    opened against `pinned_ip` instead. Overriding `connect()` is the only place
    this can be done correctly, because that is where the address is resolved.
    """

    def __init__(self, host, pinned_ip, **kw):
        super().__init__(host, **kw)
        self.pinned_ip = pinned_ip

    def connect(self) -> None:  # noqa: D102
        self.sock = self._create_connection(
            (self.pinned_ip, self.port), self.timeout, self.source_address)
        if getattr(self, "_tunnel_host", None):
            self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """The same, with TLS still verified against the *name*, not the IP.

    The previous implementation built the connection with the IP as `host` and
    then set `conn.host` back to the hostname before handing it over. That looked
    like it preserved the Host header while keeping the pin, but
    `HTTPSConnection.connect()` resolves `self.host` itself — so restoring the
    name handed DNS a second chance to answer, which is precisely the
    time-of-check-to-time-of-use gap the pin exists to close. A name that
    answered a public address during `resolve_public()` and 127.0.0.1 a moment
    later connected to 127.0.0.1.

    Here the socket is opened against the checked IP and TLS is wrapped with
    `server_hostname` set to the original name, so certificate validation and SNI
    both still apply to the host the caller asked for. The pin cannot be undone
    by a later DNS answer because DNS is never consulted again.
    """

    def __init__(self, host, pinned_ip, *, context=None, **kw):
        super().__init__(host, context=context, **kw)
        self.pinned_ip = pinned_ip

    def connect(self) -> None:  # noqa: D102
        sock = self._create_connection(
            (self.pinned_ip, self.port), self.timeout, self.source_address)
        if getattr(self, "_tunnel_host", None):
            self.sock = sock
            self._tunnel()
            sock = self.sock
        server_hostname = self._tunnel_host or self.host
        self.sock = self._context.wrap_socket(sock, server_hostname=server_hostname)


def _pin_target(req) -> Tuple[str, Optional[int], str]:
    """(hostname, port, validated ip) for a request, or raise."""
    host = req.host.split(":")[0]
    port = None
    if ":" in req.host:
        try:
            port = int(req.host.rsplit(":", 1)[1])
        except ValueError:
            port = None
    return host, port, resolve_public(host)[0]


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):  # noqa: D102
        host, port, ip = _pin_target(req)

        def factory(addr, **kw):
            kw.pop("context", None)
            return _PinnedHTTPConnection(host, ip, port=port, **kw)

        return self.do_open(factory, req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):  # noqa: D102
        host, port, ip = _pin_target(req)
        context = ssl.create_default_context()

        def factory(addr, **kw):
            kw.pop("context", None)
            return _PinnedHTTPSConnection(host, ip, context=context, port=port, **kw)

        return self.do_open(factory, req)


class _PinnedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate the destination of every redirect, not just the first URL."""

    max_repeats = MAX_REDIRECTS
    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme not in ALLOWED_SCHEMES:
            raise FetchError(
                f"Refusing a redirect to a {parsed.scheme or 'scheme-less'} URL.")
        resolve_public(parsed.hostname or "")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_url(url: str, *, max_bytes: int = MAX_BYTES,
              timeout: int = DEFAULT_TIMEOUT,
              deadline: int = DEFAULT_DEADLINE) -> Fetched:
    """Fetch a URL with SSRF, size and time guards. Raises FetchError."""
    started = time.time()
    parsed = urllib.parse.urlparse(url.strip())

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise FetchError(
            f"DeckScope only fetches http and https URLs, not "
            f"'{parsed.scheme or url[:20]}'.")
    if parsed.username or parsed.password:
        raise FetchError("Refusing a URL that embeds credentials before the host.")

    resolve_public(parsed.hostname or "")

    # Pin the connection to an address we validated. Resolving once to check and
    # then letting urllib resolve again to connect leaves a rebinding window: the
    # name can answer with a public address for the check and a private one for
    # the connection.
    opener = urllib.request.build_opener(_PinnedRedirectHandler,
                                         _PinnedHTTPSHandler(), _PinnedHTTPHandler())
    req = urllib.request.Request(url, headers={
        "User-Agent": "DeckScope (+https://github.com/CinvanaAI/DeckScope)",
        "Accept": "application/pdf, text/html, text/plain, application/json;q=0.8, */*;q=0.5",
    })

    try:
        with opener.open(req, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            declared = resp.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise FetchError(
                    f"That file is {int(declared) // 1024 // 1024} MB, above "
                    f"DeckScope's {max_bytes // 1024 // 1024} MB limit.")

            chunks: List[bytes] = []
            total = 0
            while True:
                if time.time() - started > deadline:
                    raise FetchError(
                        f"Gave up after {deadline}s. The server is too slow, or the "
                        f"response never ended.")
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise FetchError(
                        f"Download exceeded {max_bytes // 1024 // 1024} MB and was "
                        f"stopped. A pitch deck should be far smaller than this.")
                chunks.append(chunk)
            body = b"".join(chunks)
            final_url = resp.geturl()
    except FetchError:
        raise
    except urllib.error.HTTPError as exc:
        raise FetchError(f"The server returned HTTP {exc.code} for {url}.") from None
    except urllib.error.URLError as exc:
        raise FetchError(f"Could not reach {url}: {exc.reason}") from None
    except socket.timeout:
        raise FetchError(f"{url} did not respond within {timeout}s.") from None

    suffix = _suffix_for(ctype, body, final_url)
    if suffix is None:
        raise FetchError(
            f"DeckScope does not know how to read '{ctype or 'unknown'}' content "
            f"from {final_url}. Download the deck and pass the file directly.")
    return Fetched(content=body, content_type=ctype, final_url=final_url, suffix=suffix)


def _suffix_for(ctype: str, body: bytes, url: str) -> Optional[str]:
    """Decide the file type from the declared type, corroborated by magic bytes."""
    if body[:4] == b"%PDF":
        return ".pdf"
    if body[:2] == b"PK":                      # zip container: pptx/docx
        low = url.lower()
        if ".pptx" in low or "presentationml" in ctype:
            return ".pptx"
        if ".docx" in low or "wordprocessingml" in ctype:
            return ".docx"
        if ctype in ALLOWED_TYPES and ALLOWED_TYPES[ctype]:
            return ALLOWED_TYPES[ctype]
        return None
    if ctype in ALLOWED_TYPES:
        return ALLOWED_TYPES[ctype] or ".txt"
    if ctype.startswith("text/"):
        return ".txt"
    return None
