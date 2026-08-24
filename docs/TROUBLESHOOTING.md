# Troubleshooting

Start here:

```bash
deckscope doctor
```

It makes a real call to your AI provider, a real search against your research backend,
checks the packages your output formats need, and checks the reports folder is writable —
then names the specific fix for whatever failed.

---

## Installing

**"Python was not found" (Windows)**
Python isn't installed, or the PATH box wasn't ticked. Reinstall from
[python.org/downloads](https://www.python.org/downloads/) and tick **"Add python.exe to
PATH"** on the first screen. Then run `install.bat` again.

**"install.command can't be opened because it is from an unidentified developer" (macOS)**
Right-click the file → **Open** → **Open**. Once only.

**"Could not create the environment" (Linux)**
`sudo apt install python3-venv`, then run the installer again.

**pip fails behind a corporate firewall**
```bash
pip install -e ".[all]" --proxy http://proxy.company.com:8080
pip install -e ".[all]" --cert /path/to/company-ca.pem     # TLS inspection
```

**`deckscope: command not found` after installing**
The virtual environment isn't active. Either activate it
(`source .venv/bin/activate`, or `.venv\Scripts\activate` on Windows) or call it
directly: `.venv/bin/python -m deckscope run deck.pdf`.

---

## Connecting to an AI

**"No Anthropic API key found. Set ANTHROPIC_API_KEY, or run `deckscope setup`."**
Run `deckscope setup` and paste your key, or export the variable in your shell. An
existing environment variable always beats the saved one — so if you set a stale value
in `.bashrc`, that's what will be used.

**HTTP 401 / "invalid x-api-key"**
The key is wrong, revoked, or from a different provider. Check `deckscope config` to see
which key name is in use, then create a fresh key on the provider's site.

**HTTP 429 / rate limited**
You're over your quota or hitting a burst limit. Wait, use a smaller model, or reduce
`research.max_queries`. Panels multiply request volume — try `--sequential`.

**HTTP 400 "model not found"**
The model name is wrong or unavailable on your account. `deckscope providers` lists valid
names.

**"did not return parseable JSON after 3 attempts"**
The model couldn't hold the output format. Almost always a small local model. Use a
larger one, lower `temperature` to 0.1, or raise `max_tokens` — truncation mid-JSON looks
identical to malformed JSON.

**"`claude` is not installed or not on your PATH"** (cli provider)
Install the CLI you selected and make sure it runs in a plain terminal, or run
`deckscope setup` and pick a different connection.

**Connection timeouts**
Raise `provider.timeout` to 300. Behind a proxy, set `HTTPS_PROXY`. For a local model,
confirm the server is up: `curl http://localhost:11434/v1/models`.

---

## Reading decks

**"Cannot read .pdf" / "Reading PDFs needs pdfplumber"**
```bash
pip install pdfplumber python-pptx python-docx
```

**"This PDF appears to be scanned or image-only"**
There's no selectable text. Either export the original deck to PDF rather than printing
it to images, or OCR it first (`ocrmypdf in.pdf out.pdf`).

**"Deck contains very little readable text"**
The deck is mostly graphics. DeckScope cannot see numbers that exist only inside a chart
image. Add a text appendix, or export the slides with the figures as text.

**"Legacy .ppt isn't supported"**
Save as `.pptx` or export to PDF.

**Right file, still "No file at …"**
Quote the path if it has spaces, and use the full path:
`deckscope run "C:\Users\you\My Decks\deck.pdf"`. In the app window, dragging a file may
give the browser only the filename — paste the full path into the box below instead.

---

## Research

**"tavily needs an API key"**
Free key at [tavily.com](https://tavily.com), then `deckscope setup`, or export
`TAVILY_API_KEY`.

**The report says "No external sources were retrieved"**
No research backend was available, so the market analysis came from training data only.
That message is correct and deliberate. Set up a search backend and re-run.

**"The configured AI provider has no built-in web search"**
`provider_native` only works with providers that support it. Use `--research tavily`.

**Search results look irrelevant**
Check the search queries in the collapsed block under References. If they're too generic,
the deck extraction probably didn't identify the category well — try `--company "Name"`
to anchor it, or raise `--max-queries`.

---

## Output

**"Excel output needs openpyxl" / "Word output needs python-docx"**
```bash
pip install openpyxl python-docx python-pptx reportlab
```

**PDF output fails**
DeckScope tries WeasyPrint, then headless Chrome or Edge, then ReportLab.
`pip install reportlab` guarantees the fallback. Or produce `--format html` and print to
PDF from your browser — the HTML is designed for that.

**One format failed but the others worked**
That's by design. The error names the missing package; install it and re-run.

**Reports aren't where I expected**
`deckscope config` shows `out_dir`. Override per run with `--out ./somewhere`.

---

## Security screen

**"Analysis stopped: pitch deck contains content that appears to be targeting the AI"**
Strict mode found hidden instructions. Either investigate the deck, or run
`--security balanced` to neutralize and continue with everything reported. **This finding
is itself information about the company.**

**A clean deck is being flagged**
Most likely a deck that genuinely discusses prompt injection or AI instructions. The
report shows the excerpt so you can judge. Use `--security permissive` for that run, and
please open an issue with the phrasing that tripped it.

**"forensics_unavailable"**
`pdfplumber` or `python-pptx` isn't installed, so hidden-text forensics were skipped for
that file. Install them — this is the check that catches white-on-white text.

**Sources were dropped**
A retrieved page contained text addressed to the AI. Dropping is correct: a page behaving
that way isn't trustworthy evidence. The bibliography lists which and why.

---

## Panel

**"A panel needs at least two AI connections"**
Pass two or more: `--panel anthropic:claude-sonnet-5 openai:gpt-5.2`, or save a default
with `deckscope setup`.

**One panelist failed**
The run continues and the failure is reported with its error. Fix that connection
(`deckscope doctor`) and re-run.

**The consensus says "single panelist — no cross-check was possible"**
Only one panelist survived. Treat the result as a single-model report, because that's
what it is.

**The panel agrees on everything and it feels too easy**
Check the reliability section. Models from the same family reading the same bibliography
agree for correlated reasons. Diversify: `anthropic openai gemini` disagrees more usefully
than three Claude variants.

**Panels are slow or expensive**
The independent round runs in parallel, so wall-clock is roughly one run plus the review
rounds. Use `--rounds 0` for parallel independent analyses plus measured agreement with no
review calls, or mix in cheaper models.

---

## The app window

**It doesn't open**
Go to the URL printed in the terminal, usually `http://127.0.0.1:8765/`. If the port is
busy DeckScope tries the next twenty; the real one is in the message.

**"Not set up yet"**
Run `deckscope setup`, or press **Run the free demo** to see it work without any
configuration.

**Dragging a file doesn't work**
Browsers hide the full path for security. Paste the full path into the box below the drop
area.

---

## Quality

**The analysis feels shallow**
Usually the model. Move up a tier. Then raise `--max-queries` — the market half is only as
good as the evidence it found.

**Numbers seem wrong**
Check the References section: a figure is either traceable to a numbered source or marked unsourced. If the
source is labelled `vendor-marketing`, that's the report telling you to discount it. If a
claim shows *"none cited"*, no source supported it.

**Two runs give different answers**
Expected — these are language models. Lower `temperature` to 0.1 for more consistency, or
run a panel: disagreement between models on a point tells you that point is genuinely
uncertain.

**It missed something obvious**
If it's in an image, DeckScope can't see it. If it's in the text, please open an issue
with the deck excerpt — that's a prompt bug worth fixing.

---

## Still stuck

Open an issue with: `deckscope doctor` output, the exact command you ran, the full error,
your OS and Python version, and — if you can share it — a redacted deck that reproduces it.
