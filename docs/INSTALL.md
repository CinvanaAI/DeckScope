# Installing DeckScope

Pick the path that matches you. The first one needs no technical knowledge at all.

- [The double-click installer](#the-double-click-installer)
- [Installing Python first](#installing-python-first)
- [Developer install](#developer-install)
- [What "optional extras" actually do](#what-optional-extras-actually-do)
- [Corporate networks and proxies](#corporate-networks-and-proxies)
- [Offline and air-gapped machines](#offline-and-air-gapped-machines)
- [Where DeckScope puts things](#where-deckscope-puts-things)
- [Updating](#updating)
- [Uninstalling](#uninstalling)

---

## The double-click installer

1. Download this repository (the green **Code** button → **Download ZIP**) and unzip it
   somewhere you'll remember — your Documents folder is fine.
2. Open the unzipped folder.
3. Double-click the file for your system:

   | System | File | If it won't open |
   |---|---|---|
   | Windows | `install.bat` | Right-click → **Run as administrator** is *not* needed. If SmartScreen warns, click **More info** → **Run anyway**. |
   | macOS | `install.command` | If macOS refuses, right-click the file → **Open** → **Open**. That happens once. |
   | Linux | `install.sh` | Some desktops need `bash install.sh` in a terminal instead. |

The installer will:

1. **Find Python.** If it isn't installed, it opens the download page and tells you which
   checkbox matters.
2. **Create a private environment** inside the folder (`.venv/`). Nothing outside that
   folder and your Desktop is modified — DeckScope cannot interfere with other Python
   software on your machine.
3. **Install DeckScope** and the packages it needs to read PowerPoint, PDF and Word files
   and to write Excel and PDF reports. A minute or two the first time.
4. **Add Desktop shortcuts** — **DeckScope** (opens the app window) and **DeckScope
   Setup** (re-runs configuration).
5. **Run the setup wizard** — six questions in plain language.

When it finishes, double-click **DeckScope** on your Desktop any time.

---

## Installing Python first

DeckScope needs Python 3.9 or newer. Most Macs and Linux machines already have it.

**Windows.** Download from [python.org/downloads](https://www.python.org/downloads/).
On the very first screen of the installer, tick **"Add python.exe to PATH"** at the
bottom. This one checkbox is the difference between the installer working and not. Then
click *Install Now*.

**macOS.** The system Python may be too old. The simplest route:

```bash
brew install python
```

If you don't have Homebrew, download the installer from
[python.org/downloads](https://www.python.org/downloads/) instead.

**Linux.**

```bash
sudo apt install python3 python3-venv python3-pip     # Debian, Ubuntu
sudo dnf install python3 python3-pip                  # Fedora
```

The `python3-venv` package matters on Debian and Ubuntu — without it, creating the
private environment fails with a confusing message.

---

## Developer install

```bash
git clone https://github.com/CinvanaAI/DeckScope.git
cd DeckScope

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e ".[all]"            # everything
# or pick what you need:
pip install -e .                   # core only — reads .md/.txt, writes md/html/json/txt
pip install -e ".[docs]"           # + PDF, PowerPoint, Word reading and forensics
pip install -e ".[office]"         # + Excel and PDF writing
pip install -e ".[sdk]"            # + the official Anthropic SDK
pip install -e ".[dev]"            # + pytest and ruff

deckscope setup
```

Run the tests:

```bash
pytest tests/                # if you have pytest
python tests/run_tests.py    # if you don't — zero dependencies
```

---

## What "optional extras" actually do

DeckScope's core has one dependency (PyYAML). Everything else is optional, and it
degrades honestly rather than crashing.

| Package | Without it | Install |
|---|---|---|
| `pdfplumber` | Cannot read PDFs. **PDF hidden-text forensics are skipped**, and the report says so. | `pip install pdfplumber` |
| `python-pptx` | Cannot read or write PowerPoint. PPTX forensics skipped. | `pip install python-pptx` |
| `python-docx` | Cannot read or write Word. | `pip install python-docx` |
| `openpyxl` | No Excel output. | `pip install openpyxl` |
| `reportlab` | No PDF output unless a browser or WeasyPrint is available. | `pip install reportlab` |
| `anthropic` | Claude still works over plain HTTP; you lose SDK-level retries. | `pip install anthropic` |
| `boto3` | No AWS Bedrock. | `pip install boto3` |

The setup wizard checks for the ones your chosen output formats need and tells you
exactly what to install.

---

## Corporate networks and proxies

If `pip` fails behind a corporate proxy:

```bash
pip install -e ".[all]" --proxy http://user:pass@proxy.company.com:8080
```

Or set it once:

```bash
export HTTPS_PROXY=http://proxy.company.com:8080      # macOS/Linux
setx HTTPS_PROXY http://proxy.company.com:8080        # Windows
```

If your network does TLS inspection and pip complains about certificates, point it at
your organization's CA bundle:

```bash
pip install -e ".[all]" --cert /path/to/company-ca.pem
```

DeckScope itself talks only to the AI provider and search backend you configure. If
those are blocked, use a local model (`--provider openai_compatible`) or copy-paste mode
(`--provider manual`), and set `--research none`.

---

## Offline and air-gapped machines

DeckScope runs fully offline with a local model and no web research:

```bash
# On a connected machine:
pip download deckscope[all] -d ./wheels

# Move ./wheels across, then:
pip install --no-index --find-links ./wheels deckscope[all]
```

Then configure a local model and turn research off:

```yaml
provider:
  name: openai_compatible
  base_url: http://localhost:11434/v1
  model: llama3.1:8b
research:
  name: none
```

The report will state prominently that no external sources were consulted, and the
market analysis is flagged as unverified throughout. That is the correct behaviour —
DeckScope will not produce a confident-looking market view it cannot support.

---

## Where DeckScope puts things

| What | Windows | macOS / Linux |
|---|---|---|
| Settings | `%APPDATA%\DeckScope\config.yaml` | `~/.config/deckscope/config.yaml` |
| API keys | `%APPDATA%\DeckScope\.env` | `~/.config/deckscope/.env` (mode 0600) |
| Reports | `Documents\DeckScope Reports` | `~/Documents/DeckScope Reports` |
| Cache | `.deckscope_cache/` in your working folder | same |

Override the settings location with the `DECKSCOPE_HOME` environment variable — useful
for keeping several profiles.

Keys are never written into `config.yaml`, so the config file is safe to share or commit.

---

## Updating

```bash
cd DeckScope
git pull
.venv/bin/pip install -e ".[all]" --upgrade    # Windows: .venv\Scripts\pip
deckscope doctor
```

Your settings and keys survive an update; they live outside the project folder.

---

## Uninstalling

Delete the folder you unzipped, and the Desktop shortcuts. Then, if you want your
settings and saved keys gone too:

| System | Delete |
|---|---|
| Windows | `%APPDATA%\DeckScope` |
| macOS / Linux | `~/.config/deckscope` and `~/.deckscope` |

Nothing else was ever written outside those places.
