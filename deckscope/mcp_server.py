"""Expose DeckScope as an MCP server, so any MCP-speaking AI can drive it.

Claude Desktop, Claude Code, Cursor, Zed and others can call these tools directly.
Speaks JSON-RPC 2.0 over stdio. No dependencies beyond the standard library.

Register it (Claude Desktop's claude_desktop_config.json, for example):

    {"mcpServers": {"deckscope": {"command": "python",
                                  "args": ["-m", "deckscope.mcp_server"]}}}

Tools exposed:
    analyze_deck         run the full three-agent pipeline and write reports
    analyze_deck_panel   run it across several AI connections that then review each other
    scan_deck_security   screen a deck for hidden instructions without analyzing it
    list_capabilities    what providers, research backends and formats are available
    get_settings         what this install is currently configured to use
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List

from . import __version__, console, settings
from .config import ALL_LENSES

PROTOCOL_VERSION = "2024-11-05"

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "analyze_deck",
        "description": (
            "Analyze a pitch deck against its market. Runs three agents in sequence: "
            "deck extraction, independent market research, then a claim-by-claim "
            "comparison. Screens the deck and every web source for hidden prompt "
            "injection first, and returns a full bibliography of every source used. "
            "Writes report files and returns a structured summary."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck_path": {"type": "string",
                              "description": "Path or URL to a .pdf/.pptx/.docx/.md/.txt deck"},
                "deck_text": {"type": "string",
                              "description": "Deck contents as text, instead of a path"},
                "company": {"type": "string",
                            "description": "Company name, if the deck omits it"},
                "lenses": {"type": "array", "items": {"type": "string", "enum": ALL_LENSES},
                           "description": "Points of view to produce. Default: investor"},
                "formats": {"type": "array", "items": {"type": "string"},
                            "description": "md html pdf docx pptx xlsx json txt"},
                "out_dir": {"type": "string", "description": "Where to write reports"},
                "research": {"type": "string",
                             "description": "auto|tavily|serper|brave|exa|provider_native|none"},
                "security": {"type": "string",
                             "enum": ["strict", "balanced", "permissive", "off"],
                             "description": "Injection-screening posture. Default: balanced"},
                "provider": {"type": "string", "description": "Override the AI backend"},
                "model": {"type": "string", "description": "Override the model"},
            },
            "required": [],
        },
    },
    {
        "name": "analyze_deck_panel",
        "description": (
            "Analyze a pitch deck with a panel of AI connections. Each runs the full "
            "pipeline independently and in parallel, then reads the others' work "
            "anonymized, concedes or holds each position, and revises its own analysis. "
            "A chair reports where the panel agreed, where it split, what changed, and "
            "how much the agreement is actually worth. Use when a single model's verdict "
            "is not enough — the disagreements are the most useful output."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck_path": {"type": "string"},
                "deck_text": {"type": "string"},
                "panel": {"type": "array", "items": {"type": "string"},
                          "description": "Two or more connections as 'provider' or "
                                         "'provider:model', e.g. "
                                         "['anthropic:claude-sonnet-5','openai:gpt-4o']"},
                "rounds": {"type": "integer",
                           "description": "Cross-review rounds. Default 1; 0 skips review."},
                "chair": {"type": "string",
                          "description": "Which connection writes the consensus"},
                "company": {"type": "string"},
                "lenses": {"type": "array", "items": {"type": "string", "enum": ALL_LENSES}},
                "formats": {"type": "array", "items": {"type": "string"}},
                "out_dir": {"type": "string"},
                "research": {"type": "string"},
                "security": {"type": "string",
                             "enum": ["strict", "balanced", "permissive", "off"]},
            },
            "required": ["panel"],
        },
    },
    {
        "name": "scan_deck_security",
        "description": (
            "Screen a pitch deck for content aimed at an AI rather than a human reader "
            "— white-on-white text, sub-point fonts, off-slide text boxes, hidden "
            "slides, speaker-note payloads, invisible Unicode, fake system messages. "
            "Runs no analysis and calls no model. Fast and free."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck_path": {"type": "string"},
                "deck_text": {"type": "string"},
                "mode": {"type": "string",
                         "enum": ["strict", "balanced", "permissive"]},
            },
            "required": [],
        },
    },
    {
        "name": "list_capabilities",
        "description": "List available AI backends, research backends, output formats "
                       "and analytical lenses.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_settings",
        "description": "Show what this DeckScope install is configured to use.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


# ------------------------------------------------------------------- tools

def _analyze(args: Dict[str, Any]) -> str:
    from .orchestrator import Pipeline
    from .security.report import SecurityAbort

    if not args.get("deck_path") and not args.get("deck_text"):
        return "Provide either deck_path or deck_text."

    overrides: Dict[str, Any] = {
        "deck_path": args.get("deck_path"),
        "deck_text": args.get("deck_text"),
        "company_hint": args.get("company"),
        "lenses": args.get("lenses") or ["investor"],
        "security": args.get("security") or "balanced",
        "verbose": False,
        "output": {"formats": args.get("formats") or ["md"]},
    }
    if args.get("out_dir"):
        overrides["output"]["out_dir"] = args["out_dir"]
    if args.get("research"):
        overrides["research"] = {"name": args["research"]}
    prov = {k: args[k2] for k, k2 in (("name", "provider"), ("model", "model"))
            if args.get(k2)}
    if prov:
        overrides["provider"] = prov

    cfg = settings.settings_to_runconfig(overrides)
    pipe = Pipeline(cfg)
    try:
        result = pipe.run()
        files = pipe.render(result)
    except SecurityAbort as exc:
        return f"BLOCKED BY SECURITY SCREEN\n\n{exc}"
    finally:
        pipe.close()

    reg = result.registry
    payload = {
        "company": result.company,
        "files": files,
        "security": {"risk": (result.security or {}).get("overall_risk"),
                     "summary": (result.security or {}).get("summary")},
        "references": reg.stats() if reg else {},
        "verdicts": {lens: {
            "call": (c.get("verdict") or {}).get("call"),
            "confidence": (c.get("verdict") or {}).get("confidence"),
            "score": ((c.get("_meta") or {}).get("weighted_score") or {}).get("score"),
            "headline": c.get("headline"),
            "summary": c.get("summary"),
            "claim_audit": c.get("claim_audit"),
            "risks": c.get("risks"),
            "actions": c.get("actions"),
        } for lens, c in result.comparisons.items()},
        "sources": [s.to_dict() for s in (reg.sources if reg else [])],
    }
    return json.dumps(payload, indent=2, default=str)


def _panel(args: Dict[str, Any]) -> str:
    from .ensemble import Panel, parse_panelist
    from .security.report import SecurityAbort

    specs = args.get("panel") or []
    if len(specs) < 2:
        return ("A panel needs at least two AI connections. Pass e.g. "
                "panel: ['anthropic:claude-sonnet-5', 'openai:gpt-4o'].")
    if not args.get("deck_path") and not args.get("deck_text"):
        return "Provide either deck_path or deck_text."

    overrides: Dict[str, Any] = {
        "deck_path": args.get("deck_path"), "deck_text": args.get("deck_text"),
        "company_hint": args.get("company"),
        "lenses": args.get("lenses") or ["investor"],
        "security": args.get("security") or "balanced", "verbose": False,
        "output": {"formats": args.get("formats") or ["md"]},
    }
    if args.get("out_dir"):
        overrides["output"]["out_dir"] = args["out_dir"]
    if args.get("research"):
        overrides["research"] = {"name": args["research"]}

    cfg = settings.settings_to_runconfig(overrides)
    try:
        panel = Panel(cfg, [parse_panelist(s) for s in specs],
                      rounds=int(args.get("rounds", 1)),
                      chair=parse_panelist(args["chair"]) if args.get("chair") else None)
        result = panel.run()
        files = panel.render(result)
    except SecurityAbort as exc:
        return f"BLOCKED BY SECURITY SCREEN\n\n{exc}"

    payload = result.to_dict()
    payload["files"] = files
    return json.dumps(payload, indent=2, default=str)


def _scan(args: Dict[str, Any]) -> str:
    from .ingest.loader import load_deck
    from .security.policy import Mode, SecurityPolicy
    from .security.screening import screen_deck

    policy = SecurityPolicy(mode=Mode.parse(args.get("mode") or "permissive"))
    if args.get("deck_text"):
        doc = load_deck(args["deck_text"], is_text=True)
        path = None
    else:
        path = args.get("deck_path")
        if not path:
            return "Provide either deck_path or deck_text."
        doc = load_deck(path)
    _, report = screen_deck(doc, policy, deck_path=path)
    return json.dumps({"summary": report.summary_line(), **report.to_dict()},
                      indent=2, default=str)


def _capabilities(_: Dict[str, Any]) -> str:
    from .providers.registry import catalog, list_providers
    from .render.registry import DESCRIPTIONS, list_formats
    from .research.registry import list_researchers

    return json.dumps({
        "version": __version__,
        "lenses": ALL_LENSES,
        "providers": {p: [{"model": m, "note": d} for m, d in catalog(p)]
                      for p in list_providers()},
        "research_backends": list_researchers(),
        "formats": {f: DESCRIPTIONS.get(f, "") for f in list_formats()},
        "security_modes": ["strict", "balanced", "permissive", "off"],
    }, indent=2)


#: Any key whose name looks like this is redacted before leaving the process.
SECRET_HINTS = ("key", "token", "secret", "password", "passwd", "credential",
                "authorization", "auth", "cookie", "session")


def _redact(obj: Any, path: str = "") -> Any:
    """Deep-redact anything that looks like a secret.

    `provider.extra` is a free-form passthrough — it can legitimately hold an
    inline api_key or an Authorization header — so returning the settings object
    verbatim handed those to whatever MCP client asked. Redaction is structural
    rather than a denylist of known fields, because `extra` has no fixed shape.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lowered = str(k).lower()
            if any(h in lowered for h in SECRET_HINTS) and isinstance(v, str) and v:
                # api_key_env names an environment variable; that is not a secret
                # and is genuinely useful to see.
                out[k] = v if lowered.endswith("_env") else "<redacted>"
            else:
                out[k] = _redact(v, f"{path}.{k}")
        return out
    if isinstance(obj, list):
        return [_redact(v, path) for v in obj]
    return obj


def _get_settings(_: Dict[str, Any]) -> str:
    data = _redact(settings.load_settings())
    return json.dumps({"configured": settings.is_configured(),
                       "config_path": str(settings.config_path()),
                       "note": "Secret-looking values are redacted. DeckScope never "
                               "returns API keys through this interface.",
                       "settings": data}, indent=2, default=str)


HANDLERS = {"analyze_deck": _analyze, "analyze_deck_panel": _panel,
            "scan_deck_security": _scan,
            "list_capabilities": _capabilities, "get_settings": _get_settings}


# ------------------------------------------------------------------ server

def _write(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _result(req_id: Any, payload: Dict[str, Any]) -> None:
    _write({"jsonrpc": "2.0", "id": req_id, "result": payload})


def _error(req_id: Any, code: int, message: str) -> None:
    _write({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def main() -> int:
    console.enable()
    settings.load_env()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method, req_id = msg.get("method"), msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            _result(req_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "deckscope", "version": __version__},
            })
        elif method in ("notifications/initialized", "notifications/cancelled"):
            continue
        elif method == "tools/list":
            _result(req_id, {"tools": TOOLS})
        elif method == "tools/call":
            name = params.get("name")
            handler = HANDLERS.get(name)
            if not handler:
                _error(req_id, -32601, f"Unknown tool: {name}")
                continue
            try:
                text = handler(params.get("arguments") or {})
                _result(req_id, {"content": [{"type": "text", "text": text}]})
            except Exception as exc:  # noqa: BLE001
                _result(req_id, {
                    "content": [{"type": "text",
                                 "text": f"{type(exc).__name__}: {exc}\n\n"
                                         f"{traceback.format_exc()[-1200:]}"}],
                    "isError": True})
        elif method == "ping":
            _result(req_id, {})
        elif req_id is not None:
            _error(req_id, -32601, f"Method not found: {method}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
