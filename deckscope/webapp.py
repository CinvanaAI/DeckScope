"""A small local window for people who never want to see a terminal.

    deckscope app

Security model. Binding to 127.0.0.1 keeps the server off the network, but it is
NOT an authorization boundary: any process on this machine, and any web page you
visit while the app is running, can send it requests. Loopback-only was the whole
defense in an earlier version of this file, and it was not enough.

So every request must carry a per-launch token, which is generated at startup and
handed to the page in its URL. In addition:

  * State-changing routes are POST only, and their Origin must match this server.
    That blocks the classic <img src="http://127.0.0.1:8765/..."> forgery, which a
    GET route cannot defend against at all.

    What the token does NOT do is authenticate against other processes running as
    you. The page is served unauthenticated so a browser can load it, and the
    token is in that page — so anything running under your account can fetch it
    and drive the API. That is an acceptable boundary because a hostile process
    with your privileges can already read your files and your keys directly; the
    token exists to stop *web pages*, not *local programs*.
  * Opening a file is restricted to files this process actually produced. A path
    that DeckScope did not write is refused, so the endpoint cannot be turned into
    "launch an arbitrary executable".
  * Request bodies, concurrent jobs, and job retention are all capped, so a script
    cannot exhaust memory or run up an API bill in the background.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

from .console import out as _out
from . import __version__, settings
from .config import ALL_LENSES

JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()

#: Regenerated every launch. A stale bookmark cannot drive a later session.
SESSION_TOKEN = secrets.token_urlsafe(32)

#: Files this process wrote. Only these may be opened through the API.
PRODUCED_FILES: set = set()
PRODUCED_LOCK = threading.Lock()

#: Decks uploaded through the browser this session. Tracked separately from
#: PRODUCED_FILES on purpose: an upload is input the user supplied, not output
#: DeckScope created, and the "open this file" route must stay restricted to the
#: latter. Removed when the server stops.
UPLOADED_FILES: set = set()


def _forget_upload(path: str) -> None:
    """Delete one uploaded deck copy, best effort but never silent.

    The fourth external audit found the retention hole: every deck dragged
    into the app was copied into uploads/ and NEVER deleted — an
    undocumented second copy of a confidential document that outlived the
    run, the server, and the user's deletion of the original. Uploads are
    working copies: consumed by the run, removed when it ends.
    """
    resolved = str(Path(path).resolve()) if path else ""
    if resolved not in UPLOADED_FILES:
        return
    try:
        Path(resolved).unlink(missing_ok=True)
    except OSError:
        return  # locked file on Windows: swept at next server start instead
    UPLOADED_FILES.discard(resolved)


def _sweep_uploads() -> int:
    """Remove leftover uploads from crashed or killed servers, at startup."""
    upload_dir = settings.app_dir() / "uploads"
    removed = 0
    try:
        for item in upload_dir.iterdir():
            if item.is_file():
                try:
                    item.unlink()
                    removed += 1
                except OSError:
                    continue
    except OSError:
        pass
    return removed
UPLOADS_LOCK = threading.Lock()

MAX_BODY_BYTES = 256 * 1024      # a job request is a few hundred bytes
MAX_ACTIVE_JOBS = 2              # each job costs real money at a real provider

#: An uploaded deck. Larger than a job request by three orders of magnitude, so
#: it gets its own cap rather than widening the one that protects every other
#: route. Real decks with images run to a few megabytes; 32 is generous and
#: still bounded.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
#: Read in chunks so a lying Content-Length cannot make one allocation huge.
UPLOAD_CHUNK = 64 * 1024
MAX_JOBS_RETAINED = 20
JOB_TTL_SECONDS = 3600


# ------------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    server_version = f"DeckScope/{__version__}"

    def log_message(self, fmt: str, *a: Any) -> None:  # quieter console
        pass

    # ---- helpers
    def _drain(self, limit: int) -> None:
        """Read and discard at most `limit` bytes of the request body.

        Only ever called before answering a request that is being refused, so
        the data is thrown away. The limit is the point: an unbounded drain
        would reintroduce the unbounded read that the size cap exists to
        prevent, which would be a denial-of-service fix that is itself a
        denial-of-service.
        """
        remaining = max(0, int(limit))
        while remaining > 0:
            try:
                chunk = self.rfile.read(min(65536, remaining))
            except Exception:  # noqa: BLE001 - the client hung up; nothing to do
                return
            if not chunk:
                return
            remaining -= len(chunk)

    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # The page never embeds third-party content and is never framed.
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'unsafe-inline'; "
                         "style-src 'unsafe-inline'; connect-src 'self'; "
                         "frame-ancestors 'none'; form-action 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    # ---- authorization
    def _token_ok(self, query: Dict[str, List[str]]) -> bool:
        """Constant-time check of the per-launch token, from header or query."""
        supplied = (self.headers.get("X-DeckScope-Token")
                    or (query.get("token", [""])[0] if query else ""))
        return bool(supplied) and hmac.compare_digest(supplied, SESSION_TOKEN)

    def _origin_ok(self) -> bool:
        """Reject cross-site requests.

        A browser attaches Origin to every POST. If it is present it must be this
        server. If it is absent the request did not come from a page, which is
        fine for a scripted client that already holds the token.
        """
        origin = self.headers.get("Origin")
        if not origin:
            return True
        port = self.server.server_address[1]
        allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
        return origin in allowed

    def _host_ok(self) -> bool:
        """Only the loopback names this server was actually launched on.

        DNS rebinding works by pointing an attacker-controlled hostname at
        127.0.0.1 after the victim's browser has loaded the attacker's page —
        the browser then sends requests here with the attacker's hostname in
        the Host header, and the same-origin policy no longer protects
        anything. Refusing every Host that is not literally this loopback
        address closes that door (external audit finding #7).
        """
        host = (self.headers.get("Host") or "").strip().lower()
        port = self.server.server_address[1]
        return host in {f"127.0.0.1:{port}", f"localhost:{port}",
                        "127.0.0.1", "localhost"}

    # ---- routes
    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        path = route.path
        query = parse_qs(route.query)

        if not self._host_ok():
            return self._json({"error": "bad host"}, 403)

        # The page carries the session token in its JavaScript, so serving it
        # to anyone who can make a GET hands the key to whoever asks — a
        # DNS-rebinding page could read it and then hold every token-gated
        # endpoint (external audit finding #7). The launch URL printed at
        # startup already carries ?token=…, so requiring it here costs the
        # legitimate user nothing.
        if path in ("/", "/index.html"):
            if not self._token_ok(query):
                return self._send(
                    403,
                    b"DeckScope is running, but this page requires the "
                    b"launch link.\nUse the full URL printed in the "
                    b"terminal (it ends in ?token=...), or restart with: "
                    b"deckscope app\n",
                    ctype="text/plain; charset=utf-8")
            # The panel stylesheet is appended rather than duplicated, so a
            # panel drawn in the app window and the same panel saved to a file
            # cannot drift apart. The variable block maps the app's palette
            # onto the names the panel CSS uses.
            from marketreport.panel_render import PANEL_CSS

            body = PAGE.replace("__DECKSCOPE_TOKEN__", SESSION_TOKEN)
            body = body.replace(
                "/*__PANEL_CSS__*/",
                ":root{--paper:var(--panel);--surface:var(--bg);"
                "--ok:var(--good);--ok-bg:transparent;--warn-bg:transparent}"
                + PANEL_CSS)
            return self._send(200, body.encode("utf-8"))

        if not self._token_ok(query):
            return self._json({"error": "unauthorized"}, 401)

        if path == "/api/state":
            cfg = settings.load_settings()
            return self._json({
                "configured": settings.is_configured(),
                "provider": (cfg.get("provider") or {}).get("name"),
                "model": (cfg.get("provider") or {}).get("model"),
                "research": (cfg.get("research") or {}).get("name"),
                "security": (cfg.get("security") or {}).get("mode", "balanced"),
                "lenses": cfg.get("lenses") or ["investor"],
                "formats": (cfg.get("output") or {}).get("formats") or ["html"],
                "out_dir": (cfg.get("output") or {}).get("out_dir")
                           or str(settings.default_output_dir()),
                "all_lenses": ALL_LENSES,
            })

        if path == "/api/models":
            # Structural checks only — instant and free, so the picker renders
            # immediately. A live probe is a separate, explicit action.
            from . import availability as av

            settings.load_env()
            probes = av.load_probes()
            caps = av.survey(probes, include_unusable=True)
            saved = settings.load_panel()
            return self._json({
                "models": [c.to_dict() for c in caps],
                "selected": saved.get("members") or [],
                "diversity": av.diversity(saved.get("members") or []),
                "states": {
                    "ready": "Verified working",
                    "unverified": "Set up, but never actually tried",
                    "needs_setup": "Something is missing",
                    "failed": "Tried and it did not work",
                    "retired": "Withdrawn by the provider",
                },
            })

        if path.startswith("/api/job/"):
            _reap_jobs()
            with JOBS_LOCK:
                job = JOBS.get(path.rsplit("/", 1)[-1])
                job = dict(job) if job else None
            if not job:
                return self._json({"error": "no such job"}, 404)
            # The full run record stays server-side for /api/ask; polling
            # clients get a flag, not the multi-hundred-KB payload.
            job["can_ask"] = bool(job.pop("record", None))
            job.pop("chat_provider", None)
            return self._json(job)

        return self._send(404, b"Not found")

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        query = parse_qs(route.query)

        if not self._host_ok():
            return self._json({"error": "bad host"}, 403)
        if not self._token_ok(query):
            return self._json({"error": "unauthorized"}, 401)
        if not self._origin_ok():
            return self._json({"error": "cross-site request refused"}, 403)

        # Uploads are raw bytes and much larger than a job request, so they are
        # handled before the JSON body cap below. Deliberately NOT multipart:
        # the browser sends the File object as the body and the name arrives in
        # the query string, which removes a whole parser from the attack
        # surface for no loss of function.
        if route.path == "/api/upload":
            return self._upload(query)

        # A header is attacker-controlled text, not an integer. `int()` happily
        # returns a negative number, and a negative length slipped past the size
        # check above and then made `rfile.read(-1)` read until EOF — the exact
        # unbounded read the cap exists to prevent. A non-numeric value raised
        # ValueError out of the handler instead of answering 400.
        raw = self.headers.get("Content-Length")
        try:
            length = int(raw) if raw not in (None, "") else 0
        except (TypeError, ValueError):
            return self._json({"error": "bad request"}, 400)
        if length < 0:
            return self._json({"error": "bad request"}, 400)
        if length > MAX_BODY_BYTES:
            # Answer, but drain first — up to a bounded amount.
            #
            # Replying without reading the body leaves unread bytes in the
            # socket. On some platforms the close that follows becomes an
            # RST, and the client sees a connection reset instead of the 413
            # that was actually sent: the server behaves correctly and the
            # caller cannot tell. Draining a bounded prefix lets the response
            # be delivered, and the bound is what stops this from becoming the
            # unbounded read the cap exists to prevent.
            self._drain(min(length, MAX_BODY_BYTES * 4))
            return self._json({"error": "request too large"}, 413)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:  # noqa: BLE001
            return self._json({"error": "bad request"}, 400)
        if not isinstance(payload, dict):
            return self._json({"error": "bad request"}, 400)

        if route.path == "/api/open":
            return self._open(payload)
        if route.path == "/api/market":
            return self._market(payload)

        if route.path == "/api/panels":
            return self._panels(payload)

        if route.path == "/api/panel":
            return self._panel(payload)

        if route.path == "/api/run":
            return self._run(payload)
        if route.path == "/api/ask":
            return self._ask_report(payload)
        if route.path == "/api/models/select":
            return self._select_models(payload)
        if route.path == "/api/models/check":
            return self._check_model(payload)
        return self._send(404, b"Not found")

    def _select_models(self, payload: Dict[str, Any]) -> None:
        """Persist the chosen panel. Changeable at any time, which is the point."""
        from . import availability as av

        members = payload.get("members")
        if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
            return self._json({"error": "members must be a list of strings"}, 400)
        # Bound the write so a malformed request cannot fill the config file.
        if len(members) > 200:
            return self._json({"error": "too many models"}, 400)
        settings.save_panel(members)
        return self._json({"saved": members,
                           "diversity": av.diversity(members)})

    def _check_model(self, payload: Dict[str, Any]) -> None:
        """Probe one connection for real, on request.

        One at a time and only when asked: a picker that live-probed everything
        on load would spend the user's money to render a list.
        """
        from . import availability as av

        provider = str(payload.get("provider") or "")
        model = str(payload.get("model") or "")
        if not provider:
            return self._json({"error": "provider is required"}, 400)
        settings.load_env()
        record = av.probe(provider, model)
        av.save_probe(record)
        cap = av.inspect(provider, model, av.load_probes())
        return self._json({"record": {k: v for k, v in record.items()
                                      if k != "fingerprint"},
                           "capability": cap.to_dict()})

    # ---- actions
    def _open(self, payload: Dict[str, Any]) -> None:
        """Open a report. Only files this process produced are eligible.

        Without that restriction this endpoint is "run any program on this
        machine", because the OS handler for an .exe is to execute it.
        """
        target = str(payload.get("path") or "")
        try:
            resolved = str(Path(target).resolve(strict=True))
        except (OSError, ValueError):
            return self._json({"error": "no such file"}, 404)
        with PRODUCED_LOCK:
            allowed = resolved in PRODUCED_FILES
        if not allowed:
            return self._json(
                {"error": "DeckScope will only open reports it created."}, 403)
        _reveal(resolved)
        return self._json({"ok": True})

    def _upload(self, query: Dict[str, Any]) -> None:
        """Accept a deck the user picked in their browser.

        Replaces reading `File.path`, which does not exist. Browsers
        deliberately do not expose the local filesystem path of a selected
        file — the standard gives a filename and, for legacy reasons, a fake
        path of `C:\fakepath\name`. The old code sent the bare filename to the
        server and called `Path(...).exists()` on it, which only worked when the
        deck happened to sit in the server's working directory. The UI knew, and
        told the user their browser had "hidden" the path — defeating the
        non-technical flow the window exists to provide.

        So the bytes come across instead. Bounded, extension-checked, written to
        an owner-only directory under a name this server chose.
        """
        import tempfile

        from .ingest.loader import SUPPORTED_EXTENSIONS

        raw_name = (query.get("name", [""])[0] or "").strip()
        # The client's filename is untrusted text. Only its suffix is used, and
        # the stored name is generated here — so "../../.ssh/authorized_keys"
        # and "deck.pdf\x00.exe" are both simply a suffix that fails the check.
        suffix = Path(raw_name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            return self._json(
                {"error": f"DeckScope cannot read {suffix or 'that file type'}. "
                          f"Supported: "
                          f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}"}, 415)

        header = self.headers.get("Content-Length")
        try:
            declared = int(header) if header not in (None, "") else -1
        except (TypeError, ValueError):
            return self._json({"error": "bad request"}, 400)
        if declared < 0:
            return self._json({"error": "Content-Length is required"}, 411)
        if declared > MAX_UPLOAD_BYTES:
            self._drain(min(declared, UPLOAD_CHUNK * 16))
            return self._json(
                {"error": f"That file is "
                          f"{declared / 1_048_576:.1f}MB. The limit is "
                          f"{MAX_UPLOAD_BYTES // 1_048_576}MB."}, 413)

        upload_dir = settings.app_dir() / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        settings.restrict_dir_to_owner(upload_dir)

        handle, temp_path = tempfile.mkstemp(dir=str(upload_dir), suffix=suffix)
        written = 0
        try:
            with os.fdopen(handle, "wb") as fh:
                while written < declared:
                    chunk = self.rfile.read(
                        min(UPLOAD_CHUNK, declared - written))
                    if not chunk:
                        break
                    written += len(chunk)
                    # Trust the bytes, not the header. A Content-Length that
                    # understates the body would otherwise walk straight past
                    # the cap checked above.
                    if written > MAX_UPLOAD_BYTES:
                        raise ValueError("upload exceeded the size limit")
                    fh.write(chunk)
        except Exception:  # noqa: BLE001
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            return self._json({"error": "That upload could not be saved."}, 400)

        if written == 0:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            return self._json({"error": "That file is empty."}, 400)

        settings.restrict_to_owner(Path(temp_path))
        with UPLOADS_LOCK:
            UPLOADED_FILES.add(str(Path(temp_path).resolve()))
        return self._json({"path": temp_path,
                           "name": Path(raw_name).name or Path(temp_path).name,
                           "bytes": written})

    def _market(self, payload: Dict[str, Any]) -> None:
        """Produce a market report for a market the user named.

        Synchronous rather than a background job: with no model calls this is
        arithmetic over a handful of HTTP requests, and a progress bar for
        something that finishes in a second is theatre.
        """
        import marketreport.agents  # noqa: F401 - registers the agents
        from marketreport.render import summary
        from marketreport.report import MarketDefinition, build
        from marketreport.request import interpret

        demo = bool(payload.get("demo"))
        asked = str(payload.get("market") or payload.get("naics") or "").strip()
        state = str(payload.get("state") or "").strip()
        county = str(payload.get("county") or "").strip()

        if not asked:
            return self._json({"error": "Name a market."}, 400)

        # A sector code is checked before either branch, and answered as an
        # error rather than a question. The difference is whether an option
        # list would help: an ambiguous phrase has candidates to choose from, a
        # sector code has none — nothing the server can offer resolves it, so
        # it is a malformed request and not a decision the user has to make.
        from marketreport.naics import too_broad

        if asked.isdigit():
            broad = too_broad(asked)
            if broad:
                return self._json({"error": broad}, 400)

        if state or county:
            from marketreport.naics import resolve as resolve_naics
            from marketreport.naics import too_broad

            found = resolve_naics(asked, offline=demo)
            if not found.certain:
                # 200, not 400. An ambiguous request is not a malformed one —
                # the user did nothing wrong and the server understood them
                # fine. It has a question, and an error banner is the wrong
                # shape for a question.
                return self._json(
                    {"question": found.problem or
                     f"'{asked}' matches several industries. Which one?",
                     "options": [str(c) for c in found.candidates]})
            broad = too_broad(found.code or "")
            if broad:
                return self._json({"error": broad}, 400)
            naics = found.code or ""
            title = found.title
        else:
            read = interpret(asked, place=str(payload.get("place") or ""),
                             offline=demo)
            if not read.ready:
                return self._json({"question": read.question,
                                   "options": read.options})
            naics, title = read.naics, read.naics_title
            state, county = read.state_fips, read.county_fips
            title = f"{title} in {read.geography_label}"

        definition = MarketDefinition(
            label=(payload.get("label") or title or f"NAICS {naics}").strip(),
            naics=naics, state_fips=state, county_fips=county,
            customer=str(payload.get("customer") or "").strip(), demo=demo)
        try:
            answers = build(definition)
        except Exception as exc:  # noqa: BLE001
            return self._json({"error": f"The report failed: {exc}"}, 500)

        # The document goes back with the summary rather than behind a second
        # endpoint. It is the same run — fetching it again would re-query the
        # Census and could return a different report under the same heading.
        from marketreport.document import as_html, markdown

        payload = summary(answers)
        payload["documents"] = {"html": as_html(answers),
                                "md": markdown(answers)}
        return self._json(payload)

    def _panels(self, payload: Dict[str, Any]) -> None:
        """The library listing.

        Reads short headers rather than whole records, so a gallery of two
        hundred panels does not load two hundred full documents to draw a list.
        """
        from marketreport.library import Library

        try:
            refs = Library().list(limit=int(payload.get("limit") or 60),
                                  market=str(payload.get("market") or ""),
                                  measure=str(payload.get("measure") or ""))
        except Exception as exc:  # noqa: BLE001
            return self._json({"error": f"Could not read the library: {exc}"},
                              500)
        return self._json({"panels": [r.to_dict() for r in refs]})

    def _panel(self, payload: Dict[str, Any]) -> None:
        """One stored panel, rendered. Re-runs nothing."""
        from marketreport.library import Library
        from marketreport.panel_render import panel_html

        panel_id = str(payload.get("id") or "")
        shelf = Library()
        panel = shelf.load(panel_id)
        if panel is None:
            return self._json({"error": "No panel with that id. It may have "
                                        "been deleted."}, 404)
        return self._json({
            "id": panel_id,
            "html": panel_html(panel),
            "panel": panel.to_dict(),
            "related": [r.to_dict() for r in shelf.related(panel_id)],
        })

    def _ask_report(self, payload: Dict[str, Any]) -> None:
        """Grounded Q&A about a finished run — the record, nothing else.

        The grounding contract lives in deckscope/interrogate.py: answers
        come from the run record, cite its source IDs, and say plainly when
        the record does not contain the answer. The chat reuses the same
        provider configuration the run used, so a demo run chats against
        the mock and a real run chats against the real model.
        """
        from .interrogate import answer as _answer
        from .providers.base import Message, ProviderError, WaitingForAnswer
        from .providers.registry import get_provider

        job_id = str(payload.get("job") or "")
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            record = job.get("record") if job else None
            chat_provider = job.get("chat_provider") if job else None
            status = job.get("status") if job else None
        if job is None or status != "done":
            return self._json({"error": "That analysis is not available to "
                                        "ask about."}, 404)
        if not record:
            return self._json({"error": "This run kept no record to ask "
                                        "about (panel runs are not "
                                        "chat-enabled yet)."}, 400)
        question = str(payload.get("question") or "").strip()[:4000]
        if not question:
            return self._json({"error": "Ask a question."}, 400)
        history = []
        for turn in (payload.get("history") or [])[-12:]:
            if isinstance(turn, dict) and turn.get("role") in ("user",
                                                               "assistant"):
                history.append(Message(str(turn["role"]),
                                       str(turn.get("content") or "")[:8000]))
        try:
            overrides = ({"provider": chat_provider} if chat_provider else {})
            cfg = settings.settings_to_runconfig(overrides)
            provider = get_provider(cfg.provider)
            with JOBS_LOCK:
                addenda = job.setdefault("addenda", [])
                addenda_view = list(addenda)
            if payload.get("research"):
                # The reader sent the agent out mid-chat. Same screened
                # retrieval path as the pipeline; results become A-numbered
                # addenda kept on the job, never written into the record.
                from .interrogate import research_addendum
                from .research.registry import get_researcher

                researcher = get_researcher(cfg.research, provider)
                if getattr(researcher, "name", "") == "none":
                    return self._json(
                        {"error": "No search backend is configured, so "
                                  "there is nothing to research with. Run "
                                  "deckscope setup and pick one."}, 400)
                start = 1 + sum(len(a.get("cards") or [])
                                for a in addenda_view)
                addendum = research_addendum(question, provider=provider,
                                             researcher=researcher,
                                             aid_start=start)
                with JOBS_LOCK:
                    job.setdefault("addenda", []).append(addendum)
                    addenda_view = list(job["addenda"])
            reply = _answer(record, question, provider=provider,
                            history=history, addenda=addenda_view)
        except WaitingForAnswer as exc:
            return self._json({"error": f"Waiting on a spooled answer: "
                                        f"{exc}"}, 409)
        except ProviderError as exc:
            return self._json({"error": f"The AI provider failed: {exc}"}, 502)
        out: Dict[str, Any] = {"answer": reply}
        if payload.get("research"):
            out["researched"] = {"queries": addendum.get("queries", []),
                                 "sources": len(addendum.get("cards", [])),
                                 "quarantined": addendum.get("quarantined", 0)}
        return self._json(out)

    def _run(self, payload: Dict[str, Any]) -> None:
        deck = (payload.get("deck") or "").strip().strip('"')
        if not deck and not payload.get("demo"):
            return self._json({"error": "Choose a deck file first."}, 400)
        if deck and not deck.lower().startswith(("http://", "https://")) \
                and not Path(deck).exists():
            return self._json({"error": f"Can't find that file:\n{deck}"}, 400)

        _reap_jobs()
        with JOBS_LOCK:
            active = sum(1 for j in JOBS.values() if j["status"] == "running")
            if active >= MAX_ACTIVE_JOBS:
                return self._json(
                    {"error": f"{active} analyses are already running. Each one "
                              f"costs real API usage, so DeckScope runs at most "
                              f"{MAX_ACTIVE_JOBS} at a time. Wait for one to finish."},
                    429)
            job_id = secrets.token_urlsafe(12)
            JOBS[job_id] = {"id": job_id, "status": "running", "log": [],
                            "files": [], "result": None, "error": None,
                            "started": time.time()}
        threading.Thread(target=_run_job, args=(job_id, payload), daemon=True).start()
        return self._json({"job": job_id})


def _reap_jobs() -> None:
    """Drop finished jobs once they age out, so memory cannot grow unbounded."""
    now = time.time()
    with JOBS_LOCK:
        stale = [k for k, j in JOBS.items()
                 if j["status"] != "running" and now - j.get("started", now) > JOB_TTL_SECONDS]
        for k in stale:
            JOBS.pop(k, None)
        if len(JOBS) > MAX_JOBS_RETAINED:
            done = sorted((j for j in JOBS.values() if j["status"] != "running"),
                          key=lambda j: j.get("started", 0))
            for j in done[: len(JOBS) - MAX_JOBS_RETAINED]:
                JOBS.pop(j["id"], None)


def _remember(paths: List[str]) -> None:
    """Record files we produced, so /api/open can be restricted to them."""
    with PRODUCED_LOCK:
        for f in paths:
            try:
                PRODUCED_FILES.add(str(Path(f).resolve()))
            except (OSError, ValueError):
                continue


def _run_job(job_id: str, payload: Dict[str, Any]) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
    try:
        _run_job_inner(job_id, payload, job)
    finally:
        # The uploaded working copy dies with its run, whatever happened in
        # between — success, crash, or security abort.
        _forget_upload(str(payload.get("deck") or ""))


def _run_job_inner(job_id: str, payload: Dict[str, Any], job) -> None:

    def log(message: str, _data: Any = None) -> None:
        with JOBS_LOCK:
            job["log"].append(message)
            del job["log"][:-400]

    try:
        from .orchestrator import Pipeline
        from .security.report import SecurityAbort

        overrides: Dict[str, Any] = {
            "deck_path": payload["deck"],
            "company_hint": (payload.get("company") or "").strip() or None,
            "lenses": payload.get("lenses") or ["investor"],
            "verbose": False,
            "security": payload.get("security") or "balanced",
            "output": {"formats": payload.get("formats") or ["html"]},
        }
        if payload.get("out_dir"):
            overrides["output"]["out_dir"] = payload["out_dir"]
        if payload.get("opportunity"):
            # Defaults for dilution / exit multiple / horizon live in
            # OpportunityConfig; the CLI exposes flags to change them and the
            # app deliberately does not — a guest tuning exit multiples in a
            # form they do not understand is worse than a stated default.
            overrides["opportunity"] = {"enabled": True}
        if payload.get("market_reports") and not (payload.get("panel")
                                                  and len([s for s in
                                                           payload.get("panel")
                                                           or [] if s]) >= 2):
            # Integrated: the pipeline runs the reports BEFORE the comparison
            # and merges their evidence into the run's registry — same flag,
            # same engine as the CLI's --with-market-reports.
            overrides["market_reports"] = True
        if payload.get("research"):
            overrides["research"] = {"name": payload["research"]}
        if payload.get("demo"):
            overrides["provider"] = {"name": "mock"}
            overrides["research"] = {"name": "none"}

        cfg = settings.settings_to_runconfig(overrides)

        specs = [s for s in (payload.get("panel") or []) if s]
        if payload.get("demo") and payload.get("use_panel"):
            specs = ["mock:mock-a", "mock:mock-b", "mock:mock-c"]
        if len(specs) >= 2:
            from .ensemble import Panel, parse_panelist

            panel = Panel(cfg, [parse_panelist(s) for s in specs],
                          rounds=int(payload.get("rounds", 1)), on_event=log)
            result = panel.run()
            files = panel.render(result)
            _remember(files)
            if payload.get("market_reports"):
                # Saying so beats silently dropping the request — the
                # six-of-seven-arrived lesson, again.
                log("Market reports are not produced on panel runs yet — "
                    "run the deck with a single model to get them.")
            job.update({
                "status": "done", "files": files,
                "result": {
                    "company": result.company,
                    "panel": True,
                    "security": (result.security or {}).get("overall_risk", "clean"),
                    "sources": result.registry.stats() if result.registry else {},
                    "panelists": [{"label": p.label, "name": p.name, "ok": p.ok,
                                   "error": p.error} for p in result.panelists],
                    "verdicts": {
                        lens: {
                            "call": ((c.get("consensus_verdict") or {}).get("call")),
                            "confidence": ((c.get("consensus_verdict") or {}).get("confidence")),
                            "score": (result.metrics.get(lens, {}).get("score") or {}).get("mean"),
                            "agreement": ((c.get("consensus_verdict") or {}).get("agreement")),
                            "spread": (result.metrics.get(lens, {}).get("score") or {}).get("spread"),
                            "headline": c.get("headline"),
                        } for lens, c in result.consensus.items()},
                }})
            return

        pipe = Pipeline(cfg, on_event=log)
        try:
            result = pipe.run()
            files = pipe.render(result)
        finally:
            pipe.close()

        _remember(files)

        # The reports ran INSIDE the pipeline (cfg.market_reports), before
        # the comparison — the verdict above already used their evidence.
        # Here we only write the reconciliation document and surface what
        # the run produced.
        reports: Dict[str, Any] = {}
        outcome = getattr(result, "market_reports", None)
        if outcome is not None:
            try:
                from marketreport.scoping import write_reconciliation

                reports = {"stored": outcome.get("stored") or [],
                           "notes": outcome.get("notes") or [],
                           "document": None,
                           "entries": outcome.get("entries") or []}
                if reports["entries"]:
                    company = str(((getattr(result, "deck", None) or {})
                                   .get("company") or {}).get("name") or "")
                    path, lines = write_reconciliation(
                        reports["entries"],
                        market=outcome.get("market", ""),
                        definition=outcome.get("definition", ""),
                        company=company, cfg=cfg)
                    for line in lines:
                        log(line.strip())
                    reports["document"] = path
                    if path:
                        # A deliverable like the deck report — listed with
                        # the files, openable from the page.
                        files.append(path)
                        _remember([path])
            except Exception as exc:  # noqa: BLE001 - reports must not sink the deck
                reports = {"stored": [], "notes": [f"market reports failed: {exc}"]}
                log(f"Market reports failed: {exc}")

        reg = getattr(result, "registry", None)
        # Kept server-side for /api/ask — the reader's follow-up questions
        # ("where did S3 come from?", "go deeper on competition") are
        # answered from this record and nothing else.
        try:
            job["record"] = result.to_dict()
            job["chat_provider"] = overrides.get("provider")
        except Exception:  # noqa: BLE001 - chat is optional, the report is not
            job["record"] = None
        job.update({
            "status": "done", "files": files,
            "result": {
                "company": result.company,
                "market_reports": reports,
                "security": (result.security or {}).get("overall_risk", "clean"),
                "sources": reg.stats() if reg else {},
                "verdicts": {
                    lens: {
                        "call": (c.get("verdict") or {}).get("call"),
                        "confidence": (c.get("verdict") or {}).get("confidence"),
                        "score": ((c.get("_meta") or {}).get("weighted_score") or {}).get("score"),
                        "headline": c.get("headline"),
                    } for lens, c in result.comparisons.items()},
            }})
    except SecurityAbort as exc:
        job.update({"status": "blocked", "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        job.update({"status": "error", "error": f"{exc}",
                    "trace": traceback.format_exc()[-1500:]})


def _reveal(path: str) -> None:
    """Hand a file to the desktop.

    The caller MUST have verified that this path is one DeckScope produced.
    On Windows `os.startfile` runs the file's registered handler, which for an
    executable means executing it — so an unvetted path here is remote code
    execution, not a convenience.
    """
    p = Path(path)
    if not p.exists():
        return
    try:
        if os.name == "nt":
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif os.uname().sysname == "Darwin":
            import subprocess
            subprocess.Popen(["open", str(p)])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(p)])
    except Exception:  # noqa: BLE001
        pass


def serve(port: int = 8765, open_browser: bool = True) -> None:
    settings.load_env()
    swept = _sweep_uploads()
    if swept:
        _out(f"Removed {swept} leftover uploaded deck cop"
             f"{'y' if swept == 1 else 'ies'} from a previous session.")
    for attempt in range(20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port + attempt), Handler)
            break
        except OSError:
            continue
    else:
        _out(f"Couldn't find a free port near {port}.")
        return
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/?token={SESSION_TOKEN}"
    _out("\n  DeckScope is running at:")
    _out(f"    {url}")
    _out("\n  That link carries a one-time key for this session. Requests without it")
    _out("  are refused, which stops other web pages you visit from driving DeckScope.")
    _out("  It does not defend against other programs running under your own account.")
    _out("  Keep this window open while you use it. Press Ctrl+C to stop.\n")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _out("\n  Stopped.\n")


# --------------------------------------------------------------------- page

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>DeckScope</title>
<style>
:root{--accent:#2E5C8A;--ink:#1A1D21;--muted:#5C6570;--bg:#F7F9FB;--panel:#fff;
--line:#DCE1E7;--good:#2E7D5B;--warn:#B07A2B;--bad:#B3402F}
@media(prefers-color-scheme:dark){:root{--accent:#7AA2F7;--ink:#E6EAF2;--muted:#9AA5B8;
--bg:#12151C;--panel:#1B202B;--line:#2A3140;--good:#6FCF97;--warn:#E0B25C;--bad:#E57373}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:36px 22px 80px}
/*__PANEL_CSS__*/
h1{font-size:27px;margin:0 0 4px;letter-spacing:-.02em}
.sub{color:var(--muted);margin-bottom:26px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:22px 24px;margin-bottom:16px}
.drop{border:2px dashed var(--line);border-radius:12px;padding:38px 20px;text-align:center;
cursor:pointer;transition:.15s;background:var(--panel)}
.drop.over{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 8%,transparent)}
.drop b{font-size:17px}.drop p{color:var(--muted);margin:6px 0 0;font-size:13.5px}
label{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.07em;
color:var(--muted);font-weight:650;margin:16px 0 7px}
input[type=text]{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;
background:var(--bg);color:var(--ink);font-size:14px;font-family:inherit}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:20px;
padding:7px 15px;cursor:pointer;font-size:13.5px;user-select:none}
.chip.on{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
button.go{width:100%;padding:15px;border:0;border-radius:10px;background:var(--accent);
color:#fff;font-size:16px;font-weight:650;cursor:pointer;margin-top:22px;font-family:inherit}
button.go:disabled{opacity:.5;cursor:default}
.ghost{background:none;border:1px solid var(--line);color:var(--muted);border-radius:8px;
padding:8px 14px;cursor:pointer;font-size:13px;font-family:inherit}
pre.log{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:14px;
max-height:270px;overflow:auto;font-size:12.5px;line-height:1.55;white-space:pre-wrap;margin:0}
.file{display:flex;justify-content:space-between;align-items:center;gap:12px;
padding:11px 14px;border:1px solid var(--line);border-radius:8px;margin-top:8px;
background:var(--bg);font-size:13.5px}
.file span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11.5px;
font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#fff}
.b-clean{background:var(--good)}.b-low{background:var(--good)}.b-medium{background:var(--warn)}
.b-high{background:var(--bad)}.b-critical{background:var(--bad)}
.err{border-left:4px solid var(--bad);padding-left:14px;white-space:pre-wrap;font-size:14px}
.hint{color:var(--muted);font-size:13px;margin-top:6px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.hidden{display:none}.spin{display:inline-block;animation:s 1s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
/* ---- model picker ------------------------------------------------------
   The list has to answer "what can I actually use right now", which is a
   different question from "what does DeckScope support". So state is shown per
   row rather than implied by presence in the list: a green dot means something
   confirmed it works, a hollow one means it is configured but unproven, and
   anything needing setup says what is missing instead of being silently absent. */
.picker{border:1px solid var(--line);border-radius:10px;overflow:hidden;margin:6px 0 4px}
.pickhead{display:flex;align-items:center;justify-content:space-between;gap:12px;
padding:10px 14px;background:var(--panel);border-bottom:1px solid var(--line)}
.provgroup{padding:4px 0}
.provname{font-size:11px;text-transform:uppercase;letter-spacing:.09em;
color:var(--muted);font-weight:700;padding:9px 14px 3px}
.mrow{display:flex;align-items:center;gap:11px;padding:8px 14px;cursor:pointer;
border-top:1px solid transparent}
.mrow:hover{background:var(--panel)}
.mrow.disabled{cursor:default;opacity:.62}
.mrow.disabled:hover{background:none}
.mrow input{margin:0;flex:none;width:16px;height:16px;accent-color:var(--accent)}
.dot{width:9px;height:9px;border-radius:50%;flex:none}
.dot.ready{background:var(--good)}
.dot.unverified{background:none;border:1.5px solid var(--muted)}
.dot.needs_setup{background:none;border:1.5px dashed var(--warn)}
.dot.failed{background:var(--bad)}
.dot.retired{background:var(--muted);opacity:.5}
.mname{font-weight:600;font-size:14px}
.mwhy{font-size:12px;color:var(--muted)}
.mfix{font-size:12px;color:var(--accent)}
.mtest{margin-left:auto;font-size:11.5px;padding:3px 9px;border-radius:20px;
border:1px solid var(--line);background:none;color:var(--muted);cursor:pointer}
.mtest:hover{border-color:var(--accent);color:var(--accent)}
.pickfoot{padding:11px 14px;border-top:1px solid var(--line);background:var(--panel)}
.note{font-size:13px;line-height:1.5}
.note.warn{color:var(--warn)}
.opt{display:flex;gap:10px;align-items:flex-start;margin:9px 0;cursor:pointer;
font-size:14px;text-transform:none;letter-spacing:0;font-weight:400;color:var(--ink)}
.opt input{margin-top:3px;flex:none;width:16px;height:16px;accent-color:var(--accent)}
button.small{padding:5px 10px;font-size:12px}
</style></head><body><div class="wrap">
<h1>DeckScope</h1>
<div class="sub"><b>Check a pitch deck</b> against independent evidence — what the
deck claims that the market data doesn't support, what it leaves out, and what
could not be checked either way. Or skip the deck and <b>report a market</b>
directly, further down the page.</div>


<div id="unconfigured" class="card hidden">
  <b>Not connected to an AI yet.</b>
  <p class="hint">DeckScope needs two things: an AI service you already use, and a
  web-search key. Connecting them happens in a terminal &mdash; open one and run
  <code>deckscope setup</code> (seven questions, each answer tested as you go) &mdash;
  because pasting secret keys into web pages is a habit this tool refuses to
  teach. Meanwhile, both demos below run the full machinery at no cost, so you
  can see exactly what you'd be setting up.</p>
  <button class="ghost" onclick="demo()">Run the free demo</button>
  <button class="ghost" onclick="demoPanel()">Run the free panel demo</button>
</div>

<div class="card">
  <h2 style="margin-top:0">Check a deck</h2>
  <div id="drop" class="drop">
    <b>Drop a deck here</b>
    <p>PDF, PowerPoint, Word, Markdown or text — or click to browse</p>
    <p id="chosen" class="hint"></p>
  </div>
  <p class="hint">The deck never leaves this machine except as text sent to
  the AI service you configured — and, when web research is enabled, short
  search queries derived from the deck's category and claims go to your
  configured search service. Disable research (or use a local model) to keep
  everything home. Nothing else is uploaded anywhere, and this page
  itself runs locally.</p>
  <input id="file" type="file" class="hidden"
         accept=".pdf,.pptx,.docx,.md,.txt,.html,.json">

  <label>Or paste a full file path or a URL</label>
  <input id="path" type="text" placeholder="C:\Users\you\Documents\deck.pdf">

  <label>Company name <span style="text-transform:none;letter-spacing:0">(optional — helps if the deck doesn't say)</span></label>
  <input id="company" type="text" placeholder="Acme Flow">

  <label>Which AIs should analyze it
    <span style="text-transform:none;letter-spacing:0">— pick one, or several to have them review each other</span>
  </label>
  <div id="modelpicker" class="picker">
    <div class="pickhead">
      <span id="picksummary" class="hint">Loading connections…</span>
      <button type="button" class="ghost small" onclick="toggleUnavailable()"
              id="showall">Show ones that need setup</button>
    </div>
    <div id="modellist"></div>
    <div id="pickfoot" class="pickfoot hidden">
      <div id="diversity" class="note"></div>
      <div id="pickcost" class="hint"></div>
    </div>
  </div>

  <label>Point of view</label>
  <div class="chips" id="lenses"></div>

  <label>Files to produce</label>
  <div class="chips" id="formats"></div>

  <label>Use a panel of AIs <span style="text-transform:none;letter-spacing:0">(optional — they analyze separately, then review each other)</span></label>
  <input id="panel" type="text"
         placeholder="anthropic:claude-sonnet-5, openai:gpt-5.2, gemini">
  <p class="hint">Leave empty for a single analysis. Two or more connections, separated
  by commas, turns on cross-review: each model critiques the others, revises its own
  report, and a chair reports where they agreed and where they split.</p>

  <label>Security screen</label>
  <div class="chips" id="security"></div>
  <p class="hint">Decks and web pages can hide text meant to steer the AI. Balanced
  removes it and reports it; Strict refuses to analyze the deck at all.</p>

  <label>Go deeper <span style="text-transform:none;letter-spacing:0">(optional — both cost extra API usage)</span></label>
  <label class="opt"><input id="opt-reports" type="checkbox">
    <span>Also build the market reports this deck's claims depend on.
    <span class="hint" style="display:block">The AI reads the analysis, decides which
    market this really is and which yardsticks matter, then researches each one
    independently — market share, size, growth, whatever the claims lean on. Several
    extra research runs; the reports land in &ldquo;Reports you have made&rdquo; below.</span></span></label>
  <label class="opt"><input id="opt-opp" type="checkbox">
    <span>Estimate the opportunity cost of this investment.
    <span class="hint" style="display:block">What the round must return to beat an
    index fund, using stated defaults (50% future dilution, 6&times; exit revenue
    multiple, 5-year horizon). The arithmetic appears in the report so you can
    disagree with any step of it.</span></span></label>

  <button id="go" class="go">Analyze this deck</button>
  <p class="hint" id="settings-note"></p>
</div>

<div id="progress" class="card hidden">
  <div class="row" style="justify-content:space-between">
    <b><span class="spin">◐</span> Working…</b>
    <span class="hint" id="elapsed"></span>
  </div>
  <p class="hint">Three passes: read the deck, research the market independently,
  then compare. Usually one to three minutes. Market reports, if you asked for
  them, run afterwards and add a few minutes each — the log below narrates.</p>
  <pre class="log" id="log"></pre>
</div>

<div id="done" class="card hidden"></div>

<div class="card">
  <h2 style="margin-top:0">Report a market</h2>
  <p class="hint">Twelve questions, each answered or explained. Every figure
  shows its arithmetic and its source, and the report says at the top how much
  of itself it could establish.</p>

  <label>What market?</label>
  <input id="m-naics" type="text" placeholder="landscaping in Phoenix">
  <p class="hint" style="margin-top:4px">Say it the way you would out loud. A
  NAICS code works too. If the words match more than one industry it will ask
  rather than pick one &mdash; a report about the wrong market looks exactly
  like a report about the right one.</p>

  <details style="margin:10px 0">
    <summary class="hint" style="cursor:pointer">Be exact instead</summary>
    <label>What to call it <span style="text-transform:none;letter-spacing:0">(optional)</span></label>
    <input id="m-label" type="text" placeholder="Landscaping services">

    <label>State FIPS <span style="text-transform:none;letter-spacing:0">(optional &mdash; 04 is Arizona)</span></label>
    <input id="m-state" type="text" placeholder="04" maxlength="2">

    <label>County FIPS <span style="text-transform:none;letter-spacing:0">(optional &mdash; 013 is Maricopa)</span></label>
    <input id="m-county" type="text" placeholder="013" maxlength="3">
  </details>

  <button id="m-go" onclick="runMarket(false)">Produce the report</button>
  <button class="ghost" onclick="runMarket(true)">Run the free demo</button>
  <button class="ghost hidden" id="m-open">Open as a document</button>
  <button class="ghost hidden" id="m-md">Save as Markdown</button>
  <p id="m-note" class="hint"></p>
  <div id="m-out"></div>
</div>

<div class="card" id="panels-card">
  <h2 style="margin-top:0">Reports you have made</h2>
  <p class="hint">Everything produced is kept &mdash; market reports asked for
  directly, and the ones built from a deck's claims. A question answered once
  does not have to be paid for twice. Re-asking stores a new answer beside the
  old rather than replacing it: two runs of the same question differ because
  the market moved, and keeping both is what makes the change readable.</p>
  <button class="ghost" onclick="loadPanels()">Show my panels</button>
  <p id="p-note" class="hint"></p>
  <div id="p-list"></div>
  <div id="p-view"></div>
</div>


<script>
const $ = s => document.querySelector(s);
let STATE = {}, PICK = {lenses:[], formats:[], security:'balanced'}, DECK = '', T0 = 0;

// Per-launch key, injected by the server. Every API call carries it; without it
// the server refuses, so no other page or program can drive this session.
const TOKEN = "__DECKSCOPE_TOKEN__";
// ---- market report ------------------------------------------------------
// Renders the answer set, not prose. Every row is a standing question, and an
// unanswered one shows its reason in place — a section that simply vanished
// would read as an oversight rather than as a limit of the evidence.
async function runMarket(demo){
  const naics = ($('#m-naics').value || '').trim();
  const out = $('#m-out'), note = $('#m-note');
  out.textContent = ''; note.textContent = 'Working…';
  $('#m-go').disabled = true;
  try {
    const res = await api('/api/market', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        market: naics || (demo ? 'landscaping in Phoenix' : ''),
        label: $('#m-label').value, state: $('#m-state').value,
        county: $('#m-county').value, demo: !!demo})});
    const data = await res.json();
    if(!res.ok){ note.textContent = data.error || 'Failed.'; return; }
    if(data.question){ askMarket(data, out, note); return; }
    renderMarket(data, out, note);
  } catch (err) {
    note.textContent = 'Failed: ' + err;
  } finally {
    $('#m-go').disabled = false;
  }
}

// The library. A stored panel is re-rendered, never re-researched — which is
// the difference between a record and a rendering, and the thing that lets two
// people looking at the same panel see the same panel.
async function loadPanels(){
  const note = $('#p-note'), list = $('#p-list'), view = $('#p-view');
  note.textContent = 'Reading…'; list.textContent = ''; view.textContent = '';
  try {
    const res = await api('/api/panels', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({limit: 60})});
    const data = await res.json();
    if(!res.ok){ note.textContent = data.error || 'Failed.'; return; }
    if(!data.panels.length){
      note.textContent = 'Nothing stored yet. Ask for a market above.';
      return;
    }
    note.textContent = data.panels.length + ' stored';
    data.panels.forEach(p => {
      const row = document.createElement('div');
      row.className = 'card';
      row.style.cssText = 'margin:8px 0;cursor:pointer';
      row.onclick = () => openPanel(p.id);
      // The measure goes ABOVE the headline, not into the metadata line.
      // It is what the report is a report OF: two reports on one market on
      // two bases have different answers, and a gallery that shows only the
      // headline makes them look like near-duplicates of each other — which
      // is the confusion the whole per-measure split exists to remove. A
      // report with no measure says so, because unlabelled is a real state
      // and it should not look like the tidy default.
      const basis = document.createElement('p');
      basis.style.cssText = 'margin:0 0 3px;font-size:11px;letter-spacing:.06em;'
        + 'text-transform:uppercase;opacity:.75';
      basis.textContent = p.measure_label || p.measure || 'basis not named';
      if(!p.measure) basis.style.opacity = '.5';
      row.appendChild(basis);

      const head = document.createElement('b');
      head.textContent = p.headline || p.question;
      row.appendChild(head);
      const meta = document.createElement('p');
      meta.className = 'hint';
      meta.style.margin = '4px 0 0';
      meta.textContent = (p.generated || '').slice(0,10) + ' · ' + p.form
        + ' · ' + p.checkable + '/' + p.figures + ' figures checkable'
        + (p.answered ? '' : ' · not established');
      row.appendChild(meta);
      list.appendChild(row);
    });
  } catch (err) { note.textContent = 'Failed: ' + err; }
}

async function openPanel(id){
  const view = $('#p-view');
  view.textContent = 'Opening…';
  try {
    const res = await api('/api/panel', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id: id})});
    const data = await res.json();
    if(!res.ok){ view.textContent = data.error || 'Failed.'; return; }
    view.innerHTML = data.html;
    if(data.related && data.related.length){
      const p = document.createElement('p');
      p.className = 'hint';
      p.textContent = data.related.length
        + ' earlier answer(s) to this same question are stored. '
        + 'Compare them to see what moved.';
      view.appendChild(p);
    }
  } catch (err) { view.textContent = 'Failed: ' + err; }
}

// The document is handed over from what the run already produced, held in
// memory as a blob. Re-fetching it would re-query the Census and could return
// a different report under the same heading — two artifacts, one label, and no
// way to tell which one somebody is holding.
let DOCS = null;
function wireDocuments(docs){
  DOCS = docs || null;
  const open = $('#m-open'), md = $('#m-md');
  if(!DOCS){ open.classList.add('hidden'); md.classList.add('hidden'); return; }
  open.classList.remove('hidden'); md.classList.remove('hidden');
  open.onclick = () => {
    const url = URL.createObjectURL(
      new Blob([DOCS.html], {type:'text/html'}));
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  };
  md.onclick = () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([DOCS.md], {type:'text/markdown'}));
    a.download = 'market-report.md';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 60000);
  };
}

// An ambiguous request gets a question, not an error banner. The user did
// nothing wrong; there are simply two industries and only they know which one.
// Each option is a button that answers by filling in the code, so the answer
// costs one click rather than a trip to a NAICS lookup.
function askMarket(data, out, note){
  wireDocuments(null);
  note.textContent = data.question;
  note.style.color = '#b45309';
  out.textContent = '';
  (data.options || []).forEach(option => {
    const b = document.createElement('button');
    b.className = 'ghost';
    b.style.display = 'block';
    b.style.width = '100%';
    b.style.textAlign = 'left';
    b.textContent = option;
    b.onclick = () => {
      $('#m-naics').value = (option.split(/\s+/)[0] || '').trim();
      runMarket($('#m-demo-was') ? $('#m-demo-was').value === '1' : false);
    };
    out.appendChild(b);
  });
}

function renderMarket(data, out, note){
  const c = data.coverage, k = data.closure;
  wireDocuments(data.documents);
  note.textContent = k.complete
    ? `All ${c.questions} questions answered.`
    : `INCOMPLETE — ${c.answered} of ${c.questions} answered. ${k.note}`;
  note.style.color = k.complete ? '' : '#b45309';

  out.textContent = '';
  data.sections.forEach(sec => {
    const box = document.createElement('div');
    box.className = 'card';
    box.style.margin = '10px 0';

    const head = document.createElement('b');
    head.textContent = sec.heading;
    box.appendChild(head);

    const q = document.createElement('p');
    q.className = 'hint';
    q.textContent = sec.question;
    box.appendChild(q);

    const body = document.createElement('p');
    if(sec.answered){
      body.textContent = sec.statement;
      if(!sec.checkable){
        const flag = document.createElement('span');
        flag.className = 'hint';
        flag.textContent = '  (not independently checkable)';
        body.appendChild(flag);
      }
    } else {
      body.style.color = '#b45309';
      body.textContent = 'NOT ESTABLISHED — ' + sec.because;
    }
    box.appendChild(body);
    out.appendChild(box);
  });
}

const api = (path, opts = {}) => fetch(path, Object.assign({}, opts, {
  headers: Object.assign({'X-DeckScope-Token': TOKEN}, opts.headers || {})
}));

// ---- model picker --------------------------------------------------------
// Renders instantly from structural checks, because a picker that live-probed
// every provider on load would spend money to draw a list. Probing is a per-row
// action the user asks for.
let MODELS = [], CHOSEN = [], SHOW_ALL = false;

function loadModels(){
  api('/api/models').then(r=>r.json()).then(d => {
    MODELS = d.models || [];
    CHOSEN = d.selected || [];
    renderModels();
  }).catch(() => { $('#picksummary').textContent = 'Could not read connections.'; });
}

function renderModels(){
  const list = $('#modellist');
  list.innerHTML = '';
  const usable = MODELS.filter(m => m.usable);
  const shown = SHOW_ALL ? MODELS : usable;
  const hidden = MODELS.length - usable.length;

  const groups = {};
  shown.forEach(m => { (groups[m.provider] = groups[m.provider] || []).push(m); });

  Object.keys(groups).sort().forEach(provider => {
    const wrap = document.createElement('div');
    wrap.className = 'provgroup';
    const head = document.createElement('div');
    head.className = 'provname';
    head.textContent = provider;
    wrap.appendChild(head);

    groups[provider].forEach(m => {
      const row = document.createElement('label');
      row.className = 'mrow' + (m.usable ? '' : ' disabled');

      const box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = CHOSEN.includes(m.key);
      box.disabled = !m.usable;
      box.onchange = () => {
        const i = CHOSEN.indexOf(m.key);
        if(box.checked && i < 0) CHOSEN.push(m.key);
        if(!box.checked && i >= 0) CHOSEN.splice(i,1);
        saveModels();
      };
      row.appendChild(box);

      const dot = document.createElement('span');
      dot.className = 'dot ' + m.state;
      dot.title = m.state.replace('_',' ');
      row.appendChild(dot);

      const text = document.createElement('div');
      const name = document.createElement('div');
      name.className = 'mname';
      name.textContent = m.model || '(default)';
      text.appendChild(name);
      if(m.description){
        const why = document.createElement('div');
        why.className = 'mwhy'; why.textContent = m.description;
        text.appendChild(why);
      }
      if(m.state !== 'ready' && m.reasons && m.reasons.length){
        const why = document.createElement('div');
        why.className = 'mwhy'; why.textContent = m.reasons[0];
        text.appendChild(why);
      }
      if(!m.usable && m.fix){
        const fix = document.createElement('div');
        fix.className = 'mfix'; fix.textContent = m.fix;
        text.appendChild(fix);
      }
      row.appendChild(text);

      if(m.usable && m.state !== 'ready'){
        const test = document.createElement('button');
        test.type = 'button'; test.className = 'mtest'; test.textContent = 'test';
        test.onclick = (e) => { e.preventDefault(); checkOne(m, test); };
        row.appendChild(test);
      }
      wrap.appendChild(row);
    });
    list.appendChild(wrap);
  });

  $('#showall').textContent = SHOW_ALL
    ? 'Hide ones that need setup'
    : (hidden ? 'Show ' + hidden + ' that need setup' : 'Nothing hidden');
  $('#showall').style.display = hidden ? '' : 'none';
  updatePickSummary();
}

function checkOne(m, button){
  button.textContent = 'testing…'; button.disabled = true;
  api('/api/models/check', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({provider: m.provider, model: m.model})})
    .then(r=>r.json()).then(d => {
      const cap = d.capability || {};
      Object.assign(m, cap);
      renderModels();
    }).catch(() => { button.textContent = 'test failed'; button.disabled = false; });
}

function updatePickSummary(){
  const n = CHOSEN.length;
  const summary = $('#picksummary');
  const foot = $('#pickfoot');
  if(n === 0){
    summary.textContent = 'No AI chosen — pick at least one.';
    foot.classList.add('hidden');
    return;
  }
  summary.textContent = n === 1
    ? '1 AI chosen — a single analysis'
    : n + ' AIs chosen — they will review each other';
  foot.classList.remove('hidden');

  // Provider diversity is the thing that actually matters for a panel, so it is
  // stated rather than left for the user to infer from the list.
  const providers = Array.from(new Set(CHOSEN.map(k => k.split(':')[0])));
  const div = $('#diversity');
  if(n === 1){
    div.className = 'note';
    div.textContent = 'One model runs the normal analysis — no cross-review, no extra cost.';
  } else if(providers.length === 1){
    div.className = 'note warn';
    div.textContent = 'All ' + n + ' are from ' + providers[0] +
      '. They share training data and tend to agree for correlated reasons, which is ' +
      'the failure a panel is meant to catch. One model from a different provider ' +
      'buys more independence than three more from this one.';
  } else {
    div.className = 'note';
    div.textContent = providers.length + ' providers across ' + n +
      ' analysts — they can disagree for independent reasons.';
  }

  // Cost, before committing rather than after.
  if(n > 1){
    $('#pickcost').textContent = 'About ' + (n * 6) + ' API calls (~6 each). ' +
      'Each review call also carries the other ' + (n - 1) +
      ' analyses inside it, so token cost grows faster than the panel does.';
  } else {
    $('#pickcost').textContent = 'About 6 API calls.';
  }
}

function toggleUnavailable(){ SHOW_ALL = !SHOW_ALL; renderModels(); }

function saveModels(){
  api('/api/models/select', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({members: CHOSEN})}).catch(()=>{});
  updatePickSummary();
}

function chips(el, items, key, multi){
  el.innerHTML = '';
  items.forEach(([val,label]) => {
    const d = document.createElement('div');
    d.className = 'chip' + ((multi ? PICK[key].includes(val) : PICK[key]===val) ? ' on' : '');
    d.textContent = label;
    d.onclick = () => {
      if(multi){
        const i = PICK[key].indexOf(val);
        if(i>=0){ if(PICK[key].length>1) PICK[key].splice(i,1); } else PICK[key].push(val);
      } else PICK[key] = val;
      chips(el, items, key, multi);
    };
    el.appendChild(d);
  });
}

loadModels();

api('/api/state').then(r=>r.json()).then(s => {
  STATE = s;
  PICK.lenses = s.lenses.slice();
  PICK.formats = s.formats.slice();
  PICK.security = s.security;
  chips($('#lenses'), [['investor','Investor'],['founder','Founder'],['neutral','Neutral analyst']], 'lenses', true);
  chips($('#formats'), [['html','Web page'],['pdf','PDF'],['docx','Word'],['md','Markdown'],
                        ['pptx','Slides'],['xlsx','Spreadsheet'],['json','Raw data']], 'formats', true);
  chips($('#security'), [['balanced','Balanced'],['strict','Strict'],['permissive','Report only']], 'security', false);
  $('#settings-note').textContent =
    s.configured ? `Using ${s.provider}${s.model ? ' · ' + s.model : ''} · research: ${s.research} · saving to ${s.out_dir}`
                 : 'No AI configured yet.';
  if(!s.configured) $('#unconfigured').classList.remove('hidden');
});

const drop = $('#drop'), fileInput = $('#file');
drop.onclick = () => fileInput.click();
fileInput.onchange = e => { if(e.target.files[0]) upload(e.target.files[0]); };
['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.classList.add('over'); }));
['dragleave','drop'].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', e => {
  const f = e.dataTransfer.files[0];
  if(f) upload(f);
});

// Browsers do not expose a selected file's path on disk — the standard gives a
// name and a fake path. The old code read `.path`, got undefined, fell back to
// the bare filename, and the server could only find it if the deck happened to
// sit in its working directory. So send the bytes.
async function upload(file){
  $('#chosen').textContent = 'Uploading ' + file.name + '…';
  try {
    const res = await api('/api/upload?name=' + encodeURIComponent(file.name), {
      method: 'POST', body: file,
      headers: {'Content-Type': 'application/octet-stream'}});
    const data = await res.json();
    if(!res.ok){ $('#chosen').textContent = data.error || 'Upload failed.'; return; }
    DECK = data.path;
    $('#path').value = '';
    $('#chosen').textContent = 'Ready: ' + data.name +
      ' (' + (data.bytes/1048576).toFixed(1) + 'MB)';
  } catch (err) {
    $('#chosen').textContent = 'Upload failed: ' + err;
  }
}
$('#path').oninput = e => { DECK = e.target.value.trim(); $('#chosen').textContent = ''; };

function setDeck(p){
  DECK = p; $('#path').value = p;
  $('#chosen').textContent = 'Selected: ' + p.split(/[\\/]/).pop();
}

$('#go').onclick = () => start({});
function demo(){ start({demo:true}); }
function demoPanel(){ start({demo:true, use_panel:true}); }

function start(extra){
  const deck = DECK || $('#path').value.trim();
  if(!deck && !extra.demo){ alert('Choose a deck file first.'); return; }
  $('#go').disabled = true; $('#done').classList.add('hidden');
  $('#progress').classList.remove('hidden'); $('#log').textContent = '';
  T0 = Date.now();
  api('/api/run', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(Object.assign({
      deck: deck, company: $('#company').value, lenses: PICK.lenses,
      formats: PICK.formats, security: PICK.security,
      market_reports: $('#opt-reports').checked,
      opportunity: $('#opt-opp').checked,
      panel: $('#panel').value.split(',').map(s=>s.trim()).filter(Boolean)}, extra))})
    .then(r => r.json())
    .then(d => { if(d.error){ fail(d.error); } else poll(d.job); })
    .catch(e => fail(String(e)));
}

function poll(job){
  api('/api/job/' + job).then(r=>r.json()).then(j => {
    $('#log').textContent = j.log.join('\n');
    $('#log').scrollTop = 1e9;
    $('#elapsed').textContent = Math.round((Date.now()-T0)/1000) + 's';
    if(j.status === 'running'){ setTimeout(() => poll(job), 700); return; }
    $('#progress').classList.add('hidden'); $('#go').disabled = false;
    if(j.status === 'done') finish(j); else fail(j.error || 'Something went wrong.');
  }).catch(e => fail(String(e)));
}

function finish(j){
  const r = j.result, risk = r.security || 'clean';
  let html = `<h2 style="margin-top:0">${esc(r.company)}</h2>`;
  for(const [lens, v] of Object.entries(r.verdicts)){
    const extra = r.panel
      ? ` · <b>${esc(v.agreement||'—')}</b> agreement · ${esc(String(v.spread))} pt spread`
      : '';
    html += `<p><b>${esc(lens)}:</b> ${esc(v.call||'—')} ·
      ${esc(v.confidence||'—')} confidence · ${esc(String(v.score||'—'))}/100${extra}<br>
      <span class="hint">${esc(v.headline||'')}</span></p>`;
  }
  if(r.panel && r.panelists){
    html += `<label>Panel</label><p class="hint">` + r.panelists.map(p =>
      `${esc(p.label)} = ${esc(p.name)}${p.ok ? '' : ' (failed: ' + esc(p.error) + ')'}`
      ).join('<br>') + `</p>`;
  }
  html += `<p>Input integrity: <span class="badge b-${esc(risk)}">${esc(risk)}</span>`;
  if(r.sources && r.sources.total !== undefined){
    html += ` &nbsp; References: <b>${r.sources.cited}</b> cited of ${r.sources.total} retrieved`;
    if(r.sources.quarantined) html += `, ${r.sources.quarantined} dropped as untrustworthy`;
  }
  html += `</p><label>Your reports</label>`;
  html += '<div id="filelist"></div>';

  const mr = r.market_reports || {};
  if((mr.entries || []).length){
    // The loop, visible: each report was dispatched to check one claim, and
    // the reading of one against the other is the deliverable — not the
    // stored id. The full reconciliation document is in the file list above.
    html += `<label>What the market reports say about this deck's claims</label>`;
    mr.entries.forEach(en => {
      html += `<div class="file" style="display:block">
        <p style="margin:0 0 4px"><b>${esc(en.claim)}</b></p>
        <p class="hint" style="margin:0 0 6px">${esc(en.specialist)} report
          ${en.measure_label ? '(' + esc(en.measure_label) + ')' : ''} ·
          ${esc(en.headline)}</p>
        <p style="margin:0;font-size:13.5px">${esc(en.reading)}</p>
        <p class="hint" style="margin:6px 0 0">stored as ${esc(en.stored_id)}
          <button class="ghost" style="padding:3px 9px;font-size:12px"
                  onclick="jumpPanels()">open</button></p>
      </div>`;
    });
  } else if((mr.stored || []).length){
    html += `<label>Market reports built from this deck's claims</label>
      <p class="hint">${mr.stored.length} report(s) were researched independently and
      stored — find them under &ldquo;Reports you have made&rdquo; below.
      <button class="ghost" onclick="jumpPanels()">Show them</button></p>`;
  } else if(mr.notes && mr.notes.length){
    html += `<label>Market reports</label>
      <p class="hint">None were produced. The scoper's own account:</p>
      <pre class="log">${esc(mr.notes.join('\n'))}</pre>`;
  }

  html += `<details style="margin-top:16px"><summary class="hint"
      style="cursor:pointer">How to read the report</summary>
    <p class="hint" style="margin-top:10px">Three marks matter more than anything
    else on the page. A <b>source ID</b> after a figure (like S3) means the
    bibliography has a link you can open and check — do that for anything you
    intend to rely on. <b>&ldquo;no source&rdquo;</b> after a statement means the
    analysis asserted it without evidence; it is printed precisely so you discount
    it. <b>&ldquo;Could not be checked&rdquo;</b> is a research task, not a red
    flag — the report will not convert its own gaps into a verdict against the
    company. The headline is assembled by code from what was and wasn't
    established; a model does not get to write it.</p></details>`;

  html += `<p class="hint" style="margin-top:18px">AI-generated analysis, not investment
    advice. Every figure is traceable to the References section of the report — check it
    before relying on it.</p>`;
  if(j.can_ask){
    html += `<label style="margin-top:18px">Ask about this report</label>
      <p class="hint" style="margin:2px 0 8px">Answers come only from this run's
      record — sources are cited by their [S#] IDs, and &ldquo;the run didn't
      establish that&rdquo; is a real answer. Try &ldquo;where is S1
      from?&rdquo; or &ldquo;go deeper on the competition section&rdquo;.</p>
      <div id="chatlog" style="max-height:340px;overflow:auto"></div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <input id="chatq" style="flex:1" placeholder="Ask a question about the report…">
        <button id="chatgo" class="ghost" onclick="askSend()">Ask</button>
        <button id="chatresearch" class="ghost" onclick="askSend(true)"
                title="Send the agent to the web for this question; results join the chat as new A-numbered sources. The report itself is never modified.">Ask + research</button>
      </div>`;
  }
  $('#done').innerHTML = html; $('#done').classList.remove('hidden');
  CHAT = {job: j.id, history: []};
  const q = $('#chatq');
  if(q) q.addEventListener('keydown', e => { if(e.key === 'Enter') askSend(); });

  // Build the file rows in the DOM rather than by string concatenation, so a
  // filename containing quotes or markup can never become executable markup.
  const list = $('#filelist');
  (j.files || []).forEach(f => {
    const row = document.createElement('div');
    row.className = 'file';
    const name = document.createElement('span');
    name.textContent = f.split(/[\\/]/).pop();
    const btn = document.createElement('button');
    btn.className = 'ghost';
    btn.textContent = 'Open';
    btn.addEventListener('click', () => openFile(f));
    row.appendChild(name); row.appendChild(btn);
    list.appendChild(row);
  });
}

function fail(msg){
  $('#progress').classList.add('hidden'); $('#go').disabled = false;
  $('#done').innerHTML = `<div class="err"><b>That didn't work.</b>\n\n${esc(msg)}</div>`;
  $('#done').classList.remove('hidden');
}

function jumpPanels(){
  loadPanels();
  const card = document.getElementById('panels-card');
  if(card) card.scrollIntoView({behavior:'smooth'});
}

let CHAT = {job: null, history: []};

function chatBubble(role, text){
  // DOM nodes, not string concatenation — an answer quoting deck content
  // must never become markup (the same rule as the file list above).
  const log = $('#chatlog');
  const row = document.createElement('div');
  row.className = 'file';
  row.style.display = 'block';
  const who = document.createElement('p');
  who.className = 'hint'; who.style.margin = '0 0 4px';
  who.textContent = role === 'user' ? 'You' : 'DeckScope';
  const body = document.createElement('p');
  body.style.margin = '0'; body.style.whiteSpace = 'pre-wrap';
  body.style.fontSize = '13.5px';
  body.textContent = text;
  row.appendChild(who); row.appendChild(body);
  log.appendChild(row); log.scrollTop = 1e9;
  return body;
}

async function askSend(research){
  const input = $('#chatq'), btn = $('#chatgo'), rbtn = $('#chatresearch');
  const question = (input.value || '').trim();
  if(!question || !CHAT.job) return;
  input.value = ''; btn.disabled = true; input.disabled = true;
  if(rbtn) rbtn.disabled = true;
  chatBubble('user', question + (research ? '  (+ research)' : ''));
  const pending = chatBubble('assistant',
                             research ? 'Researching, then answering…' : 'Thinking…');
  try{
    const res = await api('/api/ask', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({job: CHAT.job, question, research: !!research,
                            history: CHAT.history.slice(-12)})});
    const d = await res.json();
    if(d.error){ pending.textContent = d.error; }
    else{
      let text = d.answer;
      if(d.researched){
        text += '\n\n[researched now: ' + d.researched.sources + ' new source(s)'
              + (d.researched.quarantined ? ', ' + d.researched.quarantined + ' quarantined' : '')
              + ' — cited above as A#]';
      }
      pending.textContent = text;
      CHAT.history.push({role:'user', content: question});
      CHAT.history.push({role:'assistant', content: d.answer});
    }
  }catch(e){ pending.textContent = 'That did not work: ' + e; }
  btn.disabled = false; input.disabled = false;
  if(rbtn) rbtn.disabled = false; input.focus();
}

function openFile(p){
  api('/api/open', {method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({path: p})})
    .then(r => r.json())
    .then(d => { if(d.error) alert(d.error); });
}
function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
</script></div></body></html>
"""
