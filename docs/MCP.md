# Using DeckScope from an AI assistant

DeckScope ships an MCP server, so Claude Desktop, Claude Code, Cursor, Zed and any other
MCP client can drive the whole pipeline — including the panel and the security scan.

```bash
python -m deckscope.mcp_server
```

Speaks JSON-RPC 2.0 over stdio, standard library only.

---

## Registering it

**Claude Desktop** — `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`; Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "deckscope": {
      "command": "python",
      "args": ["-m", "deckscope.mcp_server"]
    }
  }
}
```

If you installed with the double-click installer, point at the private environment:

```json
{
  "mcpServers": {
    "deckscope": {
      "command": "/full/path/to/deckscope/.venv/bin/python",
      "args": ["-m", "deckscope.mcp_server"]
    }
  }
}
```

Windows: `"C:\\path\\to\\deckscope\\.venv\\Scripts\\python.exe"`.

**Claude Code:**

```bash
claude mcp add deckscope -- python -m deckscope.mcp_server
```

**Cursor / Zed / others** — the same command and args in that client's MCP config.

Restart the client afterwards.

---

## Tools

### `analyze_deck`

The full three-agent pipeline. Writes reports and returns a structured summary including
verdicts, the claim audit, risks, actions, the security result and the full source list.

| Argument | Notes |
|---|---|
| `deck_path` | Path or URL |
| `deck_text` | Deck contents as text, instead of a path |
| `company` | If the deck omits it |
| `lenses` | `["investor"]`, `["founder","neutral"]`, … |
| `formats` | `["md","html","pdf","docx","pptx","xlsx","json","txt"]` |
| `out_dir` | Where to write |
| `research` | `auto tavily serper brave exa provider_native none` |
| `security` | `strict balanced permissive off` |
| `provider`, `model` | Override the configured backend |

### `analyze_deck_panel`

Several connections analyze independently, review each other, revise, and a chair
synthesizes. Returns every panelist's final analysis, each cross-review, the measured
agreement metrics, and the consensus.

| Argument | Notes |
|---|---|
| `panel` | **Required.** Two or more: `["anthropic:claude-sonnet-5","openai:gpt-4o"]` |
| `rounds` | Cross-review rounds; default 1, `0` skips review |
| `chair` | Which connection writes the consensus |

Plus everything `analyze_deck` takes.

### `scan_deck_security`

Screens a deck for hidden instructions — white text, tiny fonts, off-slide boxes, hidden
slides, speaker notes, invisible Unicode, fake system messages. **Calls no model.** Fast
and free.

| Argument | Notes |
|---|---|
| `deck_path` / `deck_text` | One of them |
| `mode` | `strict` `balanced` `permissive` |

### `list_capabilities`

Every provider and its models, research backends, output formats, lenses, security modes.
Useful for the assistant to check what's available before choosing.

### `get_settings`

What this install is configured to use.

---

## Asking for things

Once registered, plain language works:

> "Analyze the deck at ~/Downloads/acme.pdf from an investor's point of view and give me
> a PDF."

> "Run acme.pdf through a panel of Claude and GPT-4o and tell me where they disagreed."

> "Before we look at this deck, scan it for hidden instructions."

> "Analyze my own deck with the founder lens and tell me the three things to fix first."

The assistant picks the tool and fills the arguments.

---

## Configuration

The server uses the same settings as everything else, so run `deckscope setup` once first.
Keys are read from the saved `.env` and from the environment.

To run it under a specific profile:

```json
{
  "mcpServers": {
    "deckscope": {
      "command": "python",
      "args": ["-m", "deckscope.mcp_server"],
      "env": {"DECKSCOPE_HOME": "/Users/me/.deckscope-work"}
    }
  }
}
```

---

## DeckScope as an MCP *client*

The reverse also works: DeckScope can use an MCP server as its model backend or its search
backend.

```yaml
provider:
  name: mcp
  extra:
    command: ["npx", "-y", "my-model-mcp"]
    mode: sampling          # or: tool, with tool_name and prompt_arg

research:
  name: mcp
  extra:
    command: ["npx", "-y", "my-search-mcp"]
    tool_name: search
    query_arg: query
```

See [PROVIDERS.md](PROVIDERS.md) and [RESEARCH.md](RESEARCH.md).

---

## The skill

`skill/deck-market-analysis/SKILL.md` teaches a skill-aware assistant the same three-pass
method, with or without the package installed. Copy it into your skills directory:

```bash
cp -r skill/deck-market-analysis ~/.claude/skills/
```

With DeckScope installed as well, the skill calls the real pipeline instead of
approximating it — you get the file forensics, the source registry and the multi-format
reports.

---

## Troubleshooting

**The tools don't appear.** Restart the client. Check the command runs on its own:
`python -m deckscope.mcp_server` should wait for input rather than erroring.

**"DeckScope isn't set up yet."** Run `deckscope setup` in a terminal first — the server
reads the same configuration.

**A tool call errors.** The error text comes back verbatim in the tool result. Run
`deckscope doctor` for a full diagnosis.

**It's slow.** A full analysis is one to three minutes; a panel is longer. Some clients
time out — use `--rounds 0` or a faster model, or run the analysis from the terminal and
ask the assistant to read the JSON.
