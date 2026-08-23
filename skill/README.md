# DeckScope as a skill

`deck-market-analysis/SKILL.md` is a portable skill file. It teaches any
skill-aware AI assistant — Claude Code, Cowork, Claude Desktop — to run the same
three-pass method DeckScope automates, with or without the Python package installed.

**To install it in Claude Code or Cowork**, copy the folder into your skills
directory:

```bash
# macOS / Linux
cp -r deck-market-analysis ~/.claude/skills/

# Windows (PowerShell)
Copy-Item -Recurse deck-market-analysis "$env:USERPROFILE\.claude\skills\"
```

Then ask your assistant to analyze a deck. It will pick the skill up by description.

**With the package installed too**, the skill calls the real pipeline instead of
approximating it — you get the file forensics, the source registry, and the
multi-format reports. Install DeckScope first (see the main README), then register
the MCP server so the assistant can call it directly:

```json
{"mcpServers": {"deckscope": {"command": "python", "args": ["-m", "deckscope.mcp_server"]}}}
```
