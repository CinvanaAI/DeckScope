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
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from ..config import ProviderConfig
from .base import Completion, LLMProvider, ProviderError

PROTOCOL_VERSION = "2024-11-05"


def _client_version() -> str:
    try:
        from .. import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return "0.0.0.dev0"


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
        import os
        import queue

        self.timeout = timeout
        self._id = 0
        self._lock = threading.Lock()
        self._inbox: "queue.Queue" = queue.Queue()
        self._pending: Dict[int, Any] = {}
        self._stderr: List[str] = []
        self.proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            env={**os.environ, **(env or {})},
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
             notify: bool = False) -> Any:
        with self._lock:
            msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method,
                                   "params": params or {}}
            if not notify:
                self._id += 1
                msg["id"] = self._id
            assert self.proc.stdin is not None
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
            if notify:
                return None
        resp = self._await(msg["id"])
        if "error" in resp:
            raise ProviderError(f"MCP error: {resp['error']}")
        return resp.get("result")

    def initialize(self) -> Dict[str, Any]:
        result = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"sampling": {}},
            "clientInfo": {"name": "deckscope", "version": _client_version()},
        })
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
