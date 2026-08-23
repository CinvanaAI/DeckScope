"""Talk to a model through an MCP server that exposes sampling or a chat tool.

Two modes:
  * `sampling`  - the server implements `sampling/createMessage` (the MCP standard
                  way for a server to ask its host for a completion).
  * `tool`      - the server exposes a named tool (e.g. `chat`, `complete`) that
                  takes a prompt and returns text. Set extra.tool_name.

Transport is stdio: DeckScope launches the server command as a subprocess and
speaks JSON-RPC 2.0 over its pipes. No SDK required.
"""
from __future__ import annotations

import json
import subprocess
import threading
from typing import Any, Dict, List, Optional

from ..config import ProviderConfig
from .base import Completion, LLMProvider, ProviderError

PROTOCOL_VERSION = "2024-11-05"


class MCPStdioClient:
    """Minimal JSON-RPC-over-stdio MCP client."""

    def __init__(self, command: List[str], env: Optional[Dict[str, str]] = None,
                 timeout: int = 180) -> None:
        import os

        self.timeout = timeout
        self._id = 0
        self._lock = threading.Lock()
        self.proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            env={**os.environ, **(env or {})},
        )
        self.initialize()

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
            assert self.proc.stdout is not None
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    err = (self.proc.stderr.read() if self.proc.stderr else "")[:600]
                    raise ProviderError(f"MCP server closed the connection. {err}")
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                except json.JSONDecodeError:
                    continue  # servers sometimes log to stdout; skip noise
                if resp.get("id") != msg["id"]:
                    continue
                if "error" in resp:
                    raise ProviderError(f"MCP error: {resp['error']}")
                return resp.get("result")

    def initialize(self) -> Dict[str, Any]:
        result = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"sampling": {}},
            "clientInfo": {"name": "deckscope", "version": "1.0.0"},
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
