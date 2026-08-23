"""A small local window for people who never want to see a terminal.

Runs a server on 127.0.0.1 only — nothing is exposed to the network and nothing
is uploaded anywhere. Uses only the Python standard library, so there is no web
framework to install.

    deckscope app
"""
from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__, settings
from .config import ALL_LENSES

JOBS: Dict[str, Dict[str, Any]] = {}


# ------------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    server_version = f"DeckScope/{__version__}"

    def log_message(self, fmt: str, *a: Any) -> None:  # quieter console
        pass

    # ---- helpers
    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    # ---- routes
    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        path = route.path

        if path in ("/", "/index.html"):
            return self._send(200, PAGE.encode("utf-8"))

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
                "version": __version__,
            })

        if path.startswith("/api/job/"):
            job = JOBS.get(path.rsplit("/", 1)[-1])
            if not job:
                return self._json({"error": "no such job"}, 404)
            return self._json(job)

        if path == "/api/open":
            target = unquote(parse_qs(route.query).get("path", [""])[0])
            _reveal(target)
            return self._json({"ok": True})

        return self._send(404, b"Not found")

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/run":
            return self._send(404, b"Not found")
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:  # noqa: BLE001
            return self._json({"error": "bad request"}, 400)

        deck = (payload.get("deck") or "").strip().strip('"')
        if not deck:
            return self._json({"error": "Choose a deck file first."}, 400)
        if not deck.lower().startswith(("http://", "https://")) and not Path(deck).exists():
            return self._json({"error": f"Can't find that file:\n{deck}"}, 400)

        job_id = f"job{int(time.time() * 1000)}"
        JOBS[job_id] = {"id": job_id, "status": "running", "log": [],
                        "files": [], "result": None, "error": None}
        threading.Thread(target=_run_job, args=(job_id, payload), daemon=True).start()
        return self._json({"job": job_id})


def _run_job(job_id: str, payload: Dict[str, Any]) -> None:
    job = JOBS[job_id]

    def log(message: str, _data: Any = None) -> None:
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

        reg = getattr(result, "registry", None)
        job.update({
            "status": "done", "files": files,
            "result": {
                "company": result.company,
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
    """Open a file, or its folder, in the desktop file manager."""
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
    for attempt in range(20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port + attempt), Handler)
            break
        except OSError:
            continue
    else:
        print(f"Couldn't find a free port near {port}.")
        return
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"\n  DeckScope is running at {url}")
    print("  This window stays open while you use it. Press Ctrl+C to stop.\n")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.\n")


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
</style></head><body><div class="wrap">
<h1>DeckScope</h1>
<div class="sub">Drop a pitch deck below. DeckScope reads it, researches the market it
competes in, and tells you where the two agree — and where they don't.</div>

<div id="unconfigured" class="card hidden">
  <b>Not set up yet.</b>
  <p class="hint">Open a terminal and run <code>deckscope setup</code>, or press the
  button below to run a full sample analysis with no AI account and no cost.</p>
  <button class="ghost" onclick="demo()">Run the free demo</button>
  <button class="ghost" onclick="demoPanel()">Run the free panel demo</button>
</div>

<div class="card">
  <div id="drop" class="drop">
    <b>Drop a deck here</b>
    <p>PDF, PowerPoint, Word, Markdown or text — or click to browse</p>
    <p id="chosen" class="hint"></p>
  </div>
  <input id="file" type="file" class="hidden"
         accept=".pdf,.pptx,.docx,.md,.txt,.html,.json">

  <label>Or paste a full file path or a URL</label>
  <input id="path" type="text" placeholder="C:\Users\you\Documents\deck.pdf">

  <label>Company name <span style="text-transform:none;letter-spacing:0">(optional — helps if the deck doesn't say)</span></label>
  <input id="company" type="text" placeholder="Acme Flow">

  <label>Point of view</label>
  <div class="chips" id="lenses"></div>

  <label>Files to produce</label>
  <div class="chips" id="formats"></div>

  <label>Use a panel of AIs <span style="text-transform:none;letter-spacing:0">(optional — they analyze separately, then review each other)</span></label>
  <input id="panel" type="text"
         placeholder="anthropic:claude-sonnet-5, openai:gpt-4o, gemini">
  <p class="hint">Leave empty for a single analysis. Two or more connections, separated
  by commas, turns on cross-review: each model critiques the others, revises its own
  report, and a chair reports where they agreed and where they split.</p>

  <label>Security screen</label>
  <div class="chips" id="security"></div>
  <p class="hint">Decks and web pages can hide text meant to steer the AI. Balanced
  removes it and reports it; Strict refuses to analyze the deck at all.</p>

  <button id="go" class="go">Analyze this deck</button>
  <p class="hint" id="settings-note"></p>
</div>

<div id="progress" class="card hidden">
  <div class="row" style="justify-content:space-between">
    <b><span class="spin">◐</span> Working…</b>
    <span class="hint" id="elapsed"></span>
  </div>
  <p class="hint">Three passes: read the deck, research the market independently,
  then compare. Usually one to three minutes.</p>
  <pre class="log" id="log"></pre>
</div>

<div id="done" class="card hidden"></div>

<script>
const $ = s => document.querySelector(s);
let STATE = {}, PICK = {lenses:[], formats:[], security:'balanced'}, DECK = '', T0 = 0;

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

fetch('/api/state').then(r=>r.json()).then(s => {
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
fileInput.onchange = e => { if(e.target.files[0]) setDeck(e.target.files[0].path || e.target.files[0].name); };
['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.classList.add('over'); }));
['dragleave','drop'].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', e => {
  const f = e.dataTransfer.files[0];
  if(f) setDeck(f.path || f.name);
});
$('#path').oninput = e => { DECK = e.target.value.trim(); $('#chosen').textContent = ''; };

function setDeck(p){
  DECK = p; $('#path').value = p;
  $('#chosen').textContent = 'Selected: ' + p.split(/[\\/]/).pop();
  if(!p.includes('/') && !p.includes('\\')){
    $('#chosen').textContent += '  — your browser hid the full path; paste it below if this fails';
  }
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
  fetch('/api/run', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(Object.assign({
      deck: deck, company: $('#company').value, lenses: PICK.lenses,
      formats: PICK.formats, security: PICK.security,
      panel: $('#panel').value.split(',').map(s=>s.trim()).filter(Boolean)}, extra))})
    .then(r => r.json())
    .then(d => { if(d.error){ fail(d.error); } else poll(d.job); })
    .catch(e => fail(String(e)));
}

function poll(job){
  fetch('/api/job/' + job).then(r=>r.json()).then(j => {
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
  j.files.forEach(f => {
    html += `<div class="file"><span>${esc(f.split(/[\\/]/).pop())}</span>
      <button class="ghost" onclick="openFile('${esc(f).replace(/'/g,"\\'")}')">Open</button></div>`;
  });
  html += `<p class="hint" style="margin-top:18px">AI-generated analysis. Every figure
    is traceable to the References section of the report — check it before relying on it.</p>`;
  $('#done').innerHTML = html; $('#done').classList.remove('hidden');
}

function fail(msg){
  $('#progress').classList.add('hidden'); $('#go').disabled = false;
  $('#done').innerHTML = `<div class="err"><b>That didn't work.</b>\n\n${esc(msg)}</div>`;
  $('#done').classList.remove('hidden');
}

function openFile(p){ fetch('/api/open?path=' + encodeURIComponent(p)); }
function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
</script></div></body></html>
"""
