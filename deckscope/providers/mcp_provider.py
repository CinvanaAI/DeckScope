"""Talk to a model through an MCP server that exposes sampling or a chat tool.

Two modes:
  * `sampling`  - DeckScope calls `sampling/createMessage` ON the server.

                  Note this inverts the MCP specification, where sampling flows
                  server -> client so the client keeps control of model access and
                  can put a human in the loop. A server DeckScope launches can of
                  course choose to implement the method in this direction, but a
                  spec-compliant one will not, and will answer "method not found".
                  Prefer `mode: tool` for anything you did not write yourself.
  * `tool`      - the server exposes a named tool (e.g. `chat`, `complete`) that
                  takes a prompt and returns text. Set extra.tool_name.

Transport is stdio: DeckScope launches the server command as a subprocess and
speaks JSON-RPC 2.0 over its pipes. No SDK required.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from ..config import ProviderConfig
from .base import Completion, LLMProvider, ProviderError

#: Protocol revisions this client speaks, newest first. Kept in step with
#: deckscope.mcp_server — see the note there on the modern/legacy split.
MODERN_VERSIONS = ("2026-07-28",)
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
SUPPORTED_VERSIONS = MODERN_VERSIONS + LEGACY_VERSIONS
PREFERRED_VERSION = MODERN_VERSIONS[0]

META_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO_KEY = "io.modelcontextprotocol/clientInfo"
META_CLIENT_CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"

UNSUPPORTED_PROTOCOL_VERSION = -32022

# Retained so anything importing the old name keeps working.
PROTOCOL_VERSION = LEGACY_VERSIONS[-1]


def _client_version() -> str:
    try:
        from .. import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return "0.0.0.dev0"



#: Environment variables an MCP server legitimately needs to start. Everything
#: else is dropped — and in particular every *_API_KEY, *_TOKEN and *_SECRET in
#: DeckScope's own environment.
#:
#: This matters more here than it looks. `settings.load_env()` loads every saved
#: credential into `os.environ` so the providers can find them, and this call
#: site passed `{**os.environ}` straight to the child. A configured MCP server —
#: which the user installs, but which they did not write — therefore received
#: the Anthropic key, the OpenAI key, the Census key and every unrelated token
#: on the machine, when all it needed was its own.
#:
#: The CLI provider already got this right; the same reasoning applies to any
#: subprocess and this one was simply missed.
ENV_ALLOWLIST = (
    "PATH", "HOME", "USERPROFILE", "SystemRoot", "COMSPEC", "TEMP", "TMP",
    "LANG", "LC_ALL", "TZ", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
    "PYTHONIOENCODING", "NODE_PATH", "NVM_DIR",
)


def child_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The environment an MCP subprocess gets: an allowlist, plus what it was told.

    `extra` comes from the server's own configuration block, so a server that
    needs a credential is given it explicitly by the person who configured it.
    That is a deliberate grant of one secret rather than an accidental grant of
    all of them.
    """
    env = {k: v for k, v in os.environ.items() if k in ENV_ALLOWLIST}
    env.update({str(k): str(v) for k, v in (extra or {}).items()})
    return env


class MCPStdioClient:
    """Minimal JSON-RPC-over-stdio MCP client.

    Three things this has to get right that a naive loop does not:

      * `stdout.readline()` blocks forever if the server hangs. The configured
        timeout has to be enforced by a reader thread, not hoped for.
      * stderr must be drained continuously. A server that logs more than the
        pipe buffer holds will block on write and deadlock, and it will look
        exactly like a hang.
      * A response whose id does not match must be kept, not discarded. Notifications
        and out-of-order replies are normal, and dropping them loses real answers.
    """

    def __init__(self, command: List[str], env: Optional[Dict[str, str]] = None,
                 timeout: int = 180) -> None:
        import queue

        self.timeout = timeout
        #: Set by `initialize()`. "legacy" until the modern probe succeeds, so a
        #: legacy server never sees per-request `_meta` it does not understand.
        self.era = "legacy"
        self.protocol_version = LEGACY_VERSIONS[0]
        self.server_info: Dict[str, Any] = {}
        self._id = 0
        self._lock = threading.Lock()
        self._inbox: "queue.Queue" = queue.Queue()
        self._pending: Dict[int, Any] = {}
        self._stderr: List[str] = []
        self.proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            env=child_env(env),
        )
        self._readers = [
            threading.Thread(target=self._pump_stdout, daemon=True),
            threading.Thread(target=self._pump_stderr, daemon=True),
        ]
        for t in self._readers:
            t.start()
        self.initialize()

    def _pump_stdout(self) -> None:
        try:
            for line in self.proc.stdout:  # type: ignore[union-attr]
                line = line.strip()
                if not line:
                    continue
                try:
                    self._inbox.put(json.loads(line))
                except json.JSONDecodeError:
                    continue     # servers sometimes log to stdout; skip the noise
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._inbox.put(None)   # sentinel: the stream closed

    def _pump_stderr(self) -> None:
        """Drain stderr so the child can never block writing to a full pipe."""
        try:
            for line in self.proc.stderr:  # type: ignore[union-attr]
                self._stderr.append(line.rstrip())
                del self._stderr[:-200]
        except Exception:  # noqa: BLE001
            pass

    def _await(self, want_id: int) -> Any:
        """Wait for one response id, keeping anything else that arrives."""
        import queue

        if want_id in self._pending:
            return self._pending.pop(want_id)
        deadline = time.time() + self.timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise ProviderError(
                    f"MCP server did not answer within {self.timeout}s. "
                    + (f"Its last output was: {self._stderr[-1][:200]}"
                       if self._stderr else "It produced no diagnostics."))
            try:
                msg = self._inbox.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise ProviderError(
                        f"MCP server exited with code {self.proc.returncode}. "
                        + ("Last stderr: " + " | ".join(self._stderr[-3:])
                           if self._stderr else "")) from None
                continue
            if msg is None:
                raise ProviderError(
                    "MCP server closed the connection. "
                    + ("Last stderr: " + " | ".join(self._stderr[-3:])
                       if self._stderr else ""))
            mid = msg.get("id")
            if mid == want_id:
                return msg
            if mid is not None:
                self._pending[mid] = msg

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None,
             notify: bool = False, raw: bool = False) -> Any:
        params = dict(params or {})
        # Modern revisions carry the protocol version on every request rather
        # than establishing it once in a handshake. Only stamp it once we know
        # the server is modern, or a legacy server sees an unexpected `_meta`.
        if not notify and self.era == "modern":
            meta = dict(params.get("_meta") or {})
            meta.setdefault(META_VERSION_KEY, self.protocol_version)
            params["_meta"] = meta
        with self._lock:
            msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method,
                                   "params": params}
            if not notify:
                self._id += 1
                msg["id"] = self._id
            if self.proc.stdin is None:
                # Was an `assert`, which `python -O` strips — so the guard
                # vanished in exactly the configuration you would deploy, and
                # the next line raised AttributeError on None instead.
                raise RuntimeError(
                    "the MCP subprocess has no stdin to write to; it exited "
                    "or was started without a pipe")
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
            if notify:
                return None
        resp = self._await(msg["id"])
        if raw:
            return resp
        if "error" in resp:
            raise ProviderError(f"MCP error: {resp['error']}")
        return resp.get("result")

    def _pick_version(self, offered: Any) -> Optional[str]:
        """The newest version both sides speak, or None if there is no overlap."""
        if not isinstance(offered, list):
            return None
        for candidate in SUPPORTED_VERSIONS:
            if candidate in offered:
                return candidate
        return None

    def initialize(self) -> Dict[str, Any]:
        """Establish what this server speaks, newest era first.

        The spec's stdio backward-compatibility probe: send `server/discover`,
        which modern servers must implement. A `DiscoverResult` or a recognized
        modern error (`UnsupportedProtocolVersionError`) both identify a modern
        server; anything else means legacy, and we fall back to the `initialize`
        handshake.

        This replaces asking every server for one hardcoded version, which meant
        the client claimed `2024-11-05` forever and could never use anything a
        newer server offered.
        """
        probe = self._rpc("server/discover", {
            "_meta": {
                META_VERSION_KEY: PREFERRED_VERSION,
                META_CLIENT_INFO_KEY: {"name": "deckscope",
                                       "version": _client_version()},
                META_CLIENT_CAPS_KEY: {"sampling": {}},
            }}, raw=True)

        error = probe.get("error") if isinstance(probe, dict) else None
        if error and error.get("code") == UNSUPPORTED_PROTOCOL_VERSION:
            # A modern server that does not speak our preferred version but told
            # us what it does speak.
            chosen = self._pick_version((error.get("data") or {}).get("supported"))
            if not chosen:
                raise ProviderError(
                    f"No mutually supported MCP protocol version. Server offers "
                    f"{(error.get('data') or {}).get('supported')}, DeckScope speaks "
                    f"{list(SUPPORTED_VERSIONS)}.")
            self.era, self.protocol_version = "modern", chosen
            return {}

        result = probe.get("result") if isinstance(probe, dict) else None
        if isinstance(result, dict) and "supportedVersions" in result:
            chosen = self._pick_version(result.get("supportedVersions"))
            if not chosen:
                raise ProviderError(
                    f"No mutually supported MCP protocol version. Server offers "
                    f"{result.get('supportedVersions')}, DeckScope speaks "
                    f"{list(SUPPORTED_VERSIONS)}.")
            self.era, self.protocol_version = "modern", chosen
            self.server_info = (result.get("_meta") or {}).get(
                "io.modelcontextprotocol/serverInfo") or {}
            return result

        # Anything else — unknown method, malformed reply — is a legacy server.
        return self._legacy_initialize()

    def _legacy_initialize(self) -> Dict[str, Any]:
        self.era = "legacy"
        result = self._rpc("initialize", {
            "protocolVersion": LEGACY_VERSIONS[0],
            "capabilities": {"sampling": {}},
            "clientInfo": {"name": "deckscope", "version": _client_version()},
        })
        agreed = (result or {}).get("protocolVersion")
        # The server names the revision it will actually speak; believe it over
        # what we asked for.
        self.protocol_version = (agreed if agreed in SUPPORTED_VERSIONS
                                 else LEGACY_VERSIONS[0])
        self.server_info = (result or {}).get("serverInfo") or {}
        self._rpc("notifications/initialized", notify=True)
        return result or {}

    def list_tools(self) -> List[Dict[str, Any]]:
        return (self._rpc("tools/list") or {}).get("tools", [])

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments}) or {}
        parts = []
        for item in result.get("content", []) or []:
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(parts)

    def sample(self, system: str, messages: List[Dict[str, Any]],
               max_tokens: int) -> str:
        result = self._rpc("sampling/createMessage", {
            "systemPrompt": system,
            "maxTokens": max_tokens,
            "messages": [{"role": m["role"],
                          "content": {"type": "text", "text": m["content"]}}
                         for m in messages],
        }) or {}
        content = result.get("content", {})
        return content.get("text", "") if isinstance(content, dict) else str(content)

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                self.proc.kill()
            except Exception:  # noqa: BLE001
                pass


class MCPProvider(LLMProvider):
    name = "mcp"
    default_model = "mcp-server"
    catalog = [("mcp-server", "Whatever model your MCP server fronts")]

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        cmd = self.config.extra.get("command")
        if not cmd:
            raise ProviderError(
                "MCP provider needs extra.command, e.g.\n"
                '  provider: {name: mcp, extra: {command: ["npx","-y","my-mcp-server"]}}'
            )
        if isinstance(cmd, str):
            import shlex
            cmd = shlex.split(cmd)
        self.mode = self.config.extra.get("mode", "sampling")
        self.tool_name = self.config.extra.get("tool_name", "chat")
        self.prompt_arg = self.config.extra.get("prompt_arg", "prompt")
        self.client = MCPStdioClient(cmd, self.config.extra.get("env"),
                                     self.config.timeout)

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        payload = [{"role": m.role, "content": m.content} for m in messages]
        if self.mode == "sampling":
            text = self.client.sample(system, payload,
                                      max_tokens or self.config.max_tokens)
        else:
            joined = f"{system}\n\n" + "\n\n".join(
                f"[{m.role}] {m.content}" for m in messages
            )
            text = self.client.call_tool(self.tool_name, {self.prompt_arg: joined})
        return Completion(text=text, model=f"mcp:{self.tool_name}")

    def close(self) -> None:
        self.client.close()
