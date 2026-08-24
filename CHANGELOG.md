# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed (sixth audit) — the guarantees a stranger can check

Internal design held up; the externally visible surface did not. Protocol
conformance, a replayable benchmark, a model catalogue and a green build all
failed when independently exercised.

**The MCP server advertised a revision it did not speak.** DeckScope declared
`2026-07-28` while emitting the older result envelope: `server/discover` and
`tools/list` carried no `ttlMs` or `cacheScope`, and no modern result carried
`resultType`. A strict client was entitled to reject a server claiming its
protocol. The MCP CI job stayed green because it only checked that a version came
back and that a tool ran — a smoke test standing in for conformance. Results are
now stamped per revision, and the legacy `initialize` handshake deliberately is
*not* stamped, because trading one conformance break for another is not a fix.
Six tests exercise the wire directly.

**The committed benchmark could not be replayed.** This is the finding worth
internalising, because the check that existed passed the whole time.

The bundle shipped with a manifest of hashes and a test asserting the manifest
matched its own files. Both agreed. But the prompts had been path-scrubbed
*after* they were hashed, so 17 of 34 ids no longer equalled the hash of the file
beside them, and the pipeline cases — the ones whose prompts contained the deck's
path — could not replay at all. **A check that verifies a document against itself
proves nothing about the world.**

The fix is structural rather than more careful scrubbing:

- The deck agent sends the deck's *file name*, never its path. The path is
  useless to the model, leaks the operator's directory layout into a third-party
  prompt, and made every prompt machine-specific.
- The `manual` provider canonicalizes any remaining paths *before* hashing,
  writing or sending, so a spool is portable between machines.
- `scripts/replay_benchmark.py` checks `id == sha256(prompt)[:16]` directly and
  then re-scores the retained answers through the evaluator, offline.
- CI runs that replay on every push. A change that alters a prompt now fails
  loudly instead of quietly invalidating the published numbers.
- The bundle generator *refuses* to write a prompt containing a machine path, so
  the pipeline gets fixed rather than the artifact.

The whole suite was then re-run under the corrected prompts, with full generation
provenance recorded — model, date, who answered each exchange, and the explicit
note that answering was independent while authoring was not.

**The result changed, and not in the pipeline's favour.**

| mode | checks | input tokens |
|---|:--:|:--:|
| baseline (one prompt) | **95 / 95** | 20,610 |
| pipeline (three agents) | **94 / 95** | 195,310 |

The pipeline named *LangSmith* on `anchored_category` — a real product in the
category, present in neither the deck nor the frozen corpus, when every prompt
forbids inventing a company. That is world knowledge crossing the evidence
boundary, which is the failure this project exists to catch, and the baseline
reading the same corpus did not do it. On the only run where either mode failed
anything, the mode that failed cost 9.5× the tokens.

**The OpenAI catalogue was wrong in the opposite direction from last time.** The
previous cycle removed models OpenAI had retired and replaced them with
`gpt-5.2-mini` and `gpt-5.2-nano` — names produced by pattern-matching on
`gpt-5.2` rather than read from the docs, where the small variants are
`gpt-5-mini` and `gpt-5-nano`. Two of the three models the setup wizard offered
did not exist, and a retired-model message redirected users to one of them. The
catalogue is now short and verified, and `available_models()` asks the provider's
own `/v1/models` endpoint so a hard-coded list is no longer the only answer.

**Other fixes**

- Citations stopped working past `S999`. The registry mints IDs without a
  ceiling, but the prose parser and `find()` both capped at three digits, so a
  structured citation survived the audit while the inline form was ignored and
  the lookup failed — leaving the bibliography filing a cited source as uncited.
  A panel is deliberately unbounded, so a large merged registry is reachable.
- `merge_into()` copied admitted IDs but not the `_prompt_built` flag, so an
  incoming registry that built a prompt and admitted nothing widened the target's
  citable set back to everything — the widened-trust bug the flag exists to
  prevent, reintroduced through the merge.
- The Unix installer said nothing outside the folder and Desktop changed while
  creating a symlink in `~/.local/bin` or `/usr/local/bin`. It now lists
  everything it touches.
- CI was red on every Windows job and on lint. The acceptance test treated "bash
  exists on PATH" as "bash can run this script" — on Windows it is Git Bash,
  which failed before reaching the guard — and a test hard-coded POSIX `/tmp`,
  which resolves to an unwritable drive-relative path there. A test now forbids
  hard-coded `/tmp` across the suite. Lint: one duplicate import, one unused
  import.
- GitHub Actions are pinned to immutable commit SHAs rather than moving major
  tags, and packaging metadata uses the PEP 639 `license` expression instead of
  the deprecated table and classifier.

### Fixed (fifth audit) — uneven guarantees

The theme was that DeckScope's promises were real but not uniform. A citation was
checked recursively in one mode and two fields deep in another; one research path
skipped the security screen entirely; the bibliography could describe a source in
terms the report no longer supported; and the panel — the most expensive thing
here — had the weakest checking of the three modes. Uneven guarantees are worse
than weak ones, because the strong case is what gets documented and the weak case
is what ships.

**A legitimate phrase could be mistaken for a citation and silently rewritten.**
`CITE_RX` was `\bS(\d{1,3})\b`, which matches any S-token anywhere in a sentence,
and the same expression drove harvesting, renumbering, stripping and evaluation
scoring. So "Backups are stored in Amazon S3" carried a citation as far as
DeckScope was concerned: it could be attributed to an unrelated bibliography
entry, renumbered to `Amazon S8` during a panel merge, or deleted as dangling,
leaving `Backups are stored in Amazon .` Prose citations now require the bracket
the prompts already ask for — `[S3]`, or `[S1, S3]` — and `source_ids` arrays are
matched exactly. The trade is deliberate: a bare `S3` meant as a citation is now
ignored rather than acted on, because under-attributing is recoverable and
corrupting a sentence is not.

**The bibliography could claim a source was cited after its citation was removed.**
Attribution ran before the audit, so a source was marked `cited`, the audit then
stripped its only reference as invalid, and nothing revisited the ledger —
producing a status the reader cannot verify, wrong in the direction that flatters
us. The order is reversed, attribution is rebuilt from the artifact that actually
survived, and `attribute()` now refuses unadmitted sources so the two halves of
the ledger cannot disagree. Attribution and the audit also share one traversal
(`walk_citations`), because two hand-maintained walkers is how a valid citation
inside `alignment.blind_spots` stayed filed as "consulted, not cited".

**Public-listing research bypassed the evidence pipeline.** The market-data search
backend called `researcher.search_many()` directly and pasted raw titles, URLs and
snippets into a prompt. Pages therefore never passed the injection screen, the
sources never entered the bibliography, and the market caps feeding the
opportunity-cost arithmetic had no provenance. It now goes through `gather()` like
everything else — retrieved, registered, screened, quarantined if hostile, given
canonical IDs — and returns `source_ids` that are validated against the registry.
Its screening findings reach the run's security report.

**The panel had weaker guarantees than the single-model pipeline.**

- Revisions and the chair's consensus never received the recursive citation
  audit; `validate_comparison` covered `scorecard` and `claim_audit` only, so a
  fabricated citation in a revised summary, a blind spot, a risk or an inline
  reference survived. `audit_fragment()` now applies the same check to both.
- Merging panelist registries dropped the per-panelist admitted ledger, so a
  source a panelist genuinely read looked unadmitted — and the audit strips
  citations to unadmitted sources. The panel could delete its own honest evidence.
- The security report was a copy of the first panelist's. A hostile page that
  only another panelist retrieved was screened, quarantined, and then never
  disclosed. Findings are aggregated and the headline risk is the worst any
  panelist saw.
- `sources_found` reported one panelist's count for the whole panel.

**Reported panel cost excluded the panel.** The figure was the sum of each
panelist's independent pipeline and omitted review, revision, voting and the
chair — precisely the interaction being paid for. Measured on the shipped demo,
those rounds cost 133,933 input tokens against 40,248 for the three analyses: the
old number was low by a factor of four. `stats.token_usage` now reports
`independent_analyses` and `panel_rounds` separately, and the CI gate checks that
the rounds were counted rather than only that the total is large.

**The evaluator invented a panel winner.** `voting.tally` deliberately returns no
winner on a tie or a preference cycle. The evaluator sorted panelists by rank and
scored the first anyway — and on the shipped three-member demo every panelist
scores 1.5, preferences form an A > B > C > A cycle, and alphabetical order picked
Panelist A. The published panel accuracy was not the accuracy of a panel decision;
it was the accuracy of an arbitrarily chosen analyst. It now scores the **chair's
consensus**, which is the artifact the report leads with and exists regardless of
the vote. `consensus_verdict.call` and `claim_consensus[]` already carried the same
meaning as `verdict.call` and `claim_audit[]`; `claim_consensus` rows gained
`source_ids` so the panel's own claims are traceable.

**Other fixes**

- The baseline ran no citation audit at all — the cheaper mode offered the weaker
  promise, which is backwards now that it is the sensible default.
- The evaluation citation check said "the whole report" and walked `comparisons`
  and `market` only, so a dangling citation in an optional pass scored 1.000.
  Both the runtime and the scorer now read one shared `CITATION_SECTIONS` list.
- The mock's chair returned a fixed consensus about a $47B TAM whatever deck the
  panel had read — the same defect already fixed in the revise path, and the
  reason panel claim accuracy read 0.000.
- An oversized request body was refused without being drained, so the close could
  become an RST and the client saw a connection reset instead of the 413 the
  server actually sent. The drain is bounded, or it would reintroduce the
  unbounded read the size cap exists to prevent.
- The acceptance-script test invoked whatever `bash` was on PATH, which on
  Windows is another shell entirely; it failed on the first line and took all
  three Windows CI jobs red over an environment difference. It now checks the
  guard portably and executes it only where a POSIX shell exists.
- Lint: one f-string without placeholders, one unused local.
- Provider catalogues had drifted. Groq shut down `llama-3.3-70b-versatile` for
  free and developer tiers on 16 August 2026 — it was this backend's only
  catalogue entry *and* its default — replaced with `openai/gpt-oss-120b` and
  `qwen/qwen3.6-27b`. OpenAI's catalogue still offered `o4-mini`, retired in
  February 2026, and defaulted to `gpt-4o`; now GPT-5.2 and its mini/nano
  variants. Two tests that pinned specific model names were rewritten to assert
  the property, since that is what turned a catalogue refresh into a test failure.

### Added — reproducible benchmark artifacts

`benchmarks/` holds the exact prompt and answer for every exchange behind the
real-model numbers, the sha256 of each, the scores, and the per-case output
fingerprints. A benchmark with no retained artifacts is a claim rather than
evidence, and a project about traceable evidence should not ask to be taken on
trust about its own measurements. The numbers were re-scored under the tightened
citation rules before being committed, and did not move.


### Changed — the architecture claim, measured against a real model

Every number this project had ever reported about its own design came from the
`mock` provider, which is a fixture. The question the README leads with — is the
three-agent pipeline better than one prompt? — appeared to need an API key and
money to answer, so it went unanswered through four audits.

It did not need either. The `manual` provider already spooled prompts to a
directory; it just could not survive being stopped, because answers were keyed by
step number and thrown away when the process ended.

- **Answers are now cached by prompt content.** Identity is a hash of the prompt
  text, so re-running replays what has already been answered and stops at the
  first genuinely new question. Close the terminal and come back tomorrow. An
  identical prompt issued twice — which a panel does routinely — is asked once.
- **Non-interactive spool mode**, configurable from the environment because
  `deckscope eval` builds its own `ProviderConfig` and has nowhere to thread
  `extra` through. Any script or agent that can watch a directory can drive the
  whole pipeline with no API key.
- **An unanswered prompt raises instead of returning `""`.** The empty string fed
  the JSON repair loop and surfaced three retries later as a parse failure, which
  describes the wrong problem.
- **Token usage is reported and labelled `estimated`.** Reporting nothing made
  every manual run cost zero, which flatters exactly the modes that are expensive.
- **The truncated-answer guard was `min(poll, 1.0)`**, so a fast poll shrank it to
  nothing. It is now a wall-clock settle window, and it is documented as
  best-effort — renaming a finished file into place is the reliable protocol.

**The result.** Pipeline and baseline, all five cases, a real frontier model:
both passed 43 of 43 checks, every dimension at 1.000, with the pipeline spending
64,515 input tokens against the baseline's 10,709. The modes produced genuinely
different analyses, so the tie was measured rather than manufactured.

That is a finding about the suite, not a vindication of the architecture. **A
capable model saturates these five cases**, and a benchmark nothing fails cannot
rank anything — so the mock says the pipeline buys nothing and the real model says
the suite cannot tell.

### Added — anchoring cases, and a verdict on the three-agent design

Four cases were then written to attack the pipeline's one structural claim.
Isolation is the entire argument for three agents: the market pass never sees the
deck's claims as authoritative, so it should resist the deck's *framing*
contaminating how the evidence is read. The original five never tested that —
they all have the shape "deck says X, corpus says not-X, spot it", which is
reading comprehension, and any capable model passes it.

- `anchored_category` — a market figure that is accurate for a category the
  company does not serve. The corpus confirms $3.1B/38% for AI observability
  broadly; the slice this company sells into is $180-260M and decelerating.
- `anchored_denominator` — 131% NRR "among customers past their first renewal",
  phrasing that reads as precision rather than as a caveat, compared against
  all-customer benchmarks. It also contains a claim the deck gets *right*, so a
  reflexively contradicting analysis cannot pass.
- `anchored_comparison_set` — a real win rate against a competitive set that
  appears in a minority of actual buying decisions.
- `frame_holds` — the control, and the reason the set means anything: a deck whose
  framing is correct, where contradicting it is the failure.

Answers came from separate agents given only the prompt file, so the author of the
cases and the answerer were different.

**Result: both modes passed 52 of 52, with the pipeline spending 8.8× the input
tokens (87,121 against 9,901).** Neither trap caught either mode, on cases written
to favour the pipeline.

Across three evaluations the three-agent design has never separated from a single
prompt on any measured dimension. The README now says so. What the pipeline does
buy is the standalone market analysis — saturation, absorption risk, open-source
landscape — which `baseline` does not produce at all; `--mode` help now states
that trade explicitly rather than presenting three agents as simply better.

### Added — `tests/test_suite_integrity.py`

A case has to be checkable before it can check anything, and two expectations were
wrong in ways that would have read as analysis defects:

- `must_not_fabricate` contained `"Series B"`, so a correct analysis failed the
  fabrication check for asking "what would make this a Series B rather than a
  bridge?". The new guard rejects generic vocabulary — and caught the same latent
  defect in the original `inflated_tam` case, which had `"Series C"` and `"IPO"`
  sitting there waiting to fire on a correct analysis.
- The control demanded a positive verdict. Two independent analyses split between
  YES WITH CONDITIONS and a LEAN NO argued on price; competent readers can differ
  there, so pinning it scored taste rather than accuracy. Only `PASS` is excluded
  now, and the control's teeth are its claim expectations.

Both corrections were made after seeing results and are recorded as such, in the
changelog and in `docs/EVALUATION.md`, because the alternative is quietly tuning a
fixture until it agrees. The suite also now enforces that every blind spot exists
in its corpus and is absent from its deck, that claim patterns compile, and that
assessment and verdict labels are ones the scorer understands.

### Fixed (fourth audit) — the evidence ledger

This audit found the most serious defect this product can have, and it was real.
DeckScope's entire promise is that a reader can open the evidence behind any
statement. **A citation that resolves to the wrong source is worse than no
citation**: it converts an unsupported claim into an apparently evidenced one,
invisibly, with a badge the reader can click.

- **Cold discovery renumbered sources without rewriting the citations that named
  them.** Reproduced exactly: a finding about Microsoft Power Automate cited a
  market-sizing document, and a finding about ServiceNow cited the Microsoft one.
  The cold pass numbers its own sources from S1; folding them into the main
  bibliography shifted every ID while the model output still pointed at the old
  numbers. Merging now goes through `merge_into()`, which **returns the remap**
  so a caller cannot renumber without also rewriting — the obligation is in the
  signature rather than in someone's memory.
- **The admitted-source ledger was dropped on serialization.** `to_dict` /
  `from_dict` lost `_admitted`, so a round-tripped registry forgot which sources
  had ever reached a prompt and silently *widened* what counted as citable.
  Fixed, along with the state it was conflating: "no prompt built yet" and
  "a prompt was built and nothing fit" are opposite trust positions and are now
  distinguishable.
- **Validation covered only the fields somebody had listed.** Absorbers,
  absorption precedents, open-source projects and adjacent markets all carry
  `source_ids` in the schema and none were checked; invented IDs passed clean.
  There is now one recursive `audit_citations()` over the *finished* result —
  every `source_ids` field and every inline `[S#]`, whatever agent or optional
  pass produced it. Anything that does not resolve, was quarantined, or was never
  shown to a model is **stripped rather than displayed**, and the run records the
  audit in its own stats.
- **Final resolution read a stale snapshot.** It rebuilt the registry from the
  market agent's metadata — captured before the optional passes added their
  sources — so those sources were missing from the bibliography entirely. It now
  uses the live ledger.
- **Omissions had no provenance.** `blind_spots` were bare strings promoted
  straight to high-severity headline findings: "the deck omits X, and the
  evidence says X matters", with nothing to open. They are now objects carrying
  their own sources, and an unsourced omission is no longer promoted to high
  severity — the most prominent line in the report was the least checkable one.

**The demo contradicted its own corpus, and the cause was worse than it looked.**
It called the deck's inflated "$47B, 23% CAGR" *supported* by a corpus sentence
written to refute it, while calling a $6B serviceable slice *contradicted* on
evidence that never mentioned it. Three separate defects:

- Figures were matched as bare substrings, so `18%` (a growth rate) matched
  inside `$18-24B` (a market size) and was judged against unrelated evidence.
  Matching is now unit-aware and range-aware.
- A figure appearing in the evidence was read as agreement, even inside "not the
  $45-50B figures circulating in vendor reports".
- **Not finding a figure was treated as contradicting it** — manufacturing a
  finding out of silence, which is precisely the failure this product exists to
  prevent, in the sample everybody sees first.

And underneath all three: the fixture **overwrote a claim's assessment with
"contradicted"** to make panelists differ. Divergence now comes from how strictly
a panelist reads genuinely ambiguous evidence, which is a real analytical
disagreement rather than a fabricated one.

**The evaluation numbers went down as a result, and that is the point.** Panel
claim accuracy fell from 0.579 to 0.211 and both single-model modes from 0.421 to
0.368, because some of those fabricated "contradicted" assessments happened to
match the planted answers. A score that improves when you stop falsifying inputs
was never a measurement. README and `docs/PANEL.md` carry the corrected table.

Also: `E702` and an unused variable cleared, so lint is green.

### Fixed (fourth audit, remainder)

Everything below was understood and nearly deferred to "a separate cycle". That
is a judgement about commit size, not about whether the defects matter, and each
one is a place where DeckScope claimed something it did not do.

- **Remote decks got no file-level forensics at all.** A fetched PDF/PPTX/DOCX
  had its temporary download deleted the instant text was extracted, and the URL
  was passed to the scanner instead. A URL is not a file, so hidden slides,
  speaker notes, off-slide shapes, invisible PDF text and document metadata went
  unexamined — on precisely the decks most likely to be hostile, while the docs
  advertised the protection. The original now survives until forensics finish and
  is cleaned up after. A planted speaker-note injection in a fetched deck is now
  caught as CRITICAL; before, it produced nothing.
- **Opportunity research bypassed the security screen.** It called the researcher
  directly, so retrieved pages reached a model without passing the injection
  screen — a second, quieter door into the prompt. It also numbered its sources
  `[1]`, `[2]` locally while the schema asked for `S#`, so any citation it
  produced could not resolve. Both now go through the same corpus, screening and
  canonical-ID path as the main research, and its security findings are folded
  into the run report instead of being dropped.
- **PDF, PPTX and XLSX still led with the verdict and the composite score** after
  every other format had dropped them, so the product meant something different
  depending on which export button the reader pressed. All seven rendered formats
  now lead with findings and none shows a weighted total.
- **The panel produced no central artifact in PDF, DOCX or PPTX.** Those formats
  hit a bare `continue`, so asking a panel for a Word document silently returned
  only the individual panelist files. The panel's own answer now renders in every
  requested format.
- **Per-lens stopping decisions were computed and discarded.** One lens wanting
  another round re-reviewed and re-revised *all* of them, so settled conclusions
  kept changing, the panel paid for rounds nobody asked for, and the reported
  stopping metric described something that never happened.
- **Baseline, `both` and panel swallowed renderer failures**, printing the problem
  and exiting 0 — telling an automation that asked for a PDF that the run
  succeeded when no PDF existed. Only the pipeline path reported the shortfall.
- **Least-privilege workflow permissions** on both workflows, and the release now
  attests build provenance so "built by CI" is verifiable rather than asserted.
- Documentation corrected: eleven backends rather than "nine", and CLI help calls
  cold discovery claim-blind, which is what it is.

### Added — choose your models, and see which ones actually work

`deckscope providers` lists the catalogue: everything DeckScope knows how to
drive. That is a different question from what will work when you press go, and
the gap between them was most of the friction — a key never set, a CLI installed
but not signed in, an Ollama binary with no daemon, a model the vendor withdrew.

- **`deckscope models`** shows what is genuinely usable right now, grouped by
  provider, worst-first so anything needing attention is at the top rather than
  buried under working options. `--select` saves a panel, `--clear` forgets it,
  `--check` does a real round-trip and remembers the answer, `--json` for scripts.
- **A picker in `deckscope app`** with the same data: checkboxes, a status dot
  per row, per-row "test" buttons, and a footer that updates as you select.
- **Selections persist.** Chosen once, reused every run, changeable at any time.

**Availability is a ladder, not a boolean**, because "available" means something
different for every connection type. An API key is an env var. A CLI needs its
binary *and* a signed-in session. Ollama needs a binary, a running daemon, and
the specific model pulled — three independent conditions. Bedrock needs
credentials *and* per-account, per-model access granted in the AWS console, which
no local check can see. So the states are `ready` (a live probe confirmed it),
`unverified` (configured, never actually tried), `needs_setup` (something named
is missing), `failed` (probed, with the reason) and `retired`. Structural checks
are free and run every time; live probes cost money, run on demand, and are
cached against a **fingerprint of the credential**, so rotating a key invalidates
the pass it earned rather than vouching for the new one. Nothing unverified is
ever shown as ready.

**Panel size is now the user's call.** The old cap was eight, which came from a
hardcoded string of letters running out at "Panelist H" rather than from
anything true. Labels now continue A–Z, AA, AB, … and there is no ceiling; the
cost is made legible instead. A correction to something stated earlier in this
changelog's development: **API calls scale linearly** at roughly six per
panelist — a 46-model panel is about 280 calls, not thousands. It is *tokens*
that grow quadratically, because each panelist's single review call carries every
peer's full analysis inside it.

**One model runs a normal analysis instead of erroring.** Selecting a single
model is reasonable; it is simply not a panel, since one analyst cannot
cross-review itself. `deckscope panel` now says so and runs the single-model
pipeline rather than making the user retype the command with a different verb.

**Provider diversity is surfaced, never enforced.** Several models from one
vendor share training data and tend to agree for correlated reasons — the exact
failure a panel exists to catch. The picker says so plainly and then does as it
is told, because comparing models within a family is a legitimate thing to want.

Found by the new tooling on its first run: the **Claude CLI preset was passing
`--mcp-config {}`**, which the CLI rejects because it validates for an
`mcpServers` record. Every call through that preset failed before it started.

### Added — the panel can finally be measured, and the first result is unflattering

Not prompted by an audit. The panel is the most expensive thing DeckScope does —
three panelists plus review rounds — and `--mode` accepted only `pipeline` and
`baseline`, so the costliest feature was the only one nobody could evaluate.

- **`deckscope eval --mode panel`** runs the panel through the same suite as the
  other architectures and scores its vote-winning report.
- **Mode comparisons now say whether they were capable of showing a difference.**
  Identical scores across modes mean one of two very different things: the modes
  really perform alike, or the provider never produced different analyses for them
  and the delta is zero by construction. The runner fingerprints each mode's
  actual output and reports which it was. Presenting the second as the first turns
  a non-measurement into a finding — the same family of error as an evaluator
  reporting "every check passed" over zero cases.
- **Panel cost now counts every panelist.** It was reporting one member's tokens,
  which made a three-member panel look exactly as cheap as a single pipeline run.
  Any cost/benefit comparison built on that would have been worse than none.

The result, on five cases under the mock: baseline `0.421`, pipeline `0.421`,
panel `0.579` at 3.0× the pipeline's input tokens. **The three-agent pipeline ties
the single-prompt baseline exactly**, at five times the cost. That is the mock, not
a model, so it is not a verdict — but the suite separates the panel by 15 points on
the same cases, so it is demonstrably not blind to architecture. A tie here means
the modes agreed. README and `docs/PANEL.md` now carry the table rather than
"unproven".

Two defects surfaced while building this, both of which had made the panel look
worse than it is:

- The runner initially scored the chair's **consensus**, which follows a different
  schema and has no `claim_audit` or `verdict.call`. The panel scored `0.000` on
  both — a category error, not a result.
- The mock's revision path called `_compare()` with no prompt, so a panelist
  revising its analysis of one deck returned **claims about a different company**.
  Invisible in the demo, where the deck happens to be that company.

### Changed — the report now leads with findings, not a verdict

Prompted by an outside product review, and confirmed by reading the actual output
rather than the description of it. Every report opened with this:

    | Verdict         | LEAN NO      |
    | Weighted score  | 45.7 / 100   |

An oracle's answer, at the top of a tool whose architecture exists to avoid being
an oracle — isolated agents, an opportunity module that refuses to forecast,
calibration scored as a first-class dimension — and whose README warns against
relying on any figure without opening the source it cites. The machinery argued
"don't let eloquence outrun evidence"; the cover page did exactly that with its
own output. `Questions this raises` was section 8 of 11.

- **New `deckscope/findings.py`** composes the report's opening from the
  structured output, in Python, from counts. No model writes the headline — the
  same rule the evaluation scorer follows, for the same reason: a generated
  summary can overclaim and a computed one cannot.
- **Contested and unverified are now separated.** The claim audit conflated "the
  deck says X and sourced evidence says otherwise" with "nothing was found either
  way". The first is a finding; the second is a research task. Rendering them as
  rows in one table let an analysis quietly convert its own ignorance into a
  signal against the company. Unverifiable claims now appear under *What could not
  be checked* and flow into next steps, explicitly not as marks against the deck.
- **A contradiction with no citation is no longer described as sourced.**
  `evidence_quality` is the model's opinion of its own evidence; `source_ids` is
  checkable. When they disagree the checkable field wins, so a model cannot assert
  "strong" evidence, cite nothing, and have the report dress its unsupported
  disagreement up as a finding.
- **The headline never claims evidence it does not have.** Two distinct thin-evidence
  states are reported differently: no sources retrieved, versus sources retrieved
  but never cited. Announcing "no external evidence was retrieved" when three
  sources came back would itself be a false statement in the line meant to prevent
  them.
- **The composite score is gone from the report.** A weighted average of seven
  subjective 1–10 scores, shown to three significant figures, was the one number in
  the report that could not be traced to a source, and putting it above the fold
  invited exactly the use this tool should not support — thresholding decks by it.
  The per-dimension scorecard stays, each row with its reasoning. `scorecard_total`
  remains internally, because the panel ranks reports by it.
- **The verdict is demoted**, under "What this adds up to, for this lens", framed as
  one reading rather than the answer.
- **Questions and actions are no longer printed twice.** They are consolidated and
  ranked once, at the top; only the owner/priority table survives further down.
- All three renderers — markdown, HTML and DOCX — lead identically, from one shared
  `findings_for()` so they cannot drift.

### Fixed (third audit)

The theme of this audit was **gates that could not fail**. Four separate checks
reported success because nothing had actually been examined, which is worse than
having no check at all, because a green result gets trusted.

- **The evaluation suite was absent from the wheel, so the release gate passed
  vacuously.** The fixtures lived in a top-level `evals/` directory beside the
  package rather than inside it, so `pip install` did not carry them. An installed
  DeckScope loaded zero cases, and because the evaluator reports success when no
  check fails, it printed `0 run(s)` / `every check passed` and exited 0. The
  fixtures now live in `deckscope/evaluation/suite/` and are declared as package
  data; `load_suite` raises `EmptySuiteError` instead of returning `[]`;
  `--trials 0` and a `--only` filter matching no cases are both refused; and the
  CLI exits **2** for "this run was never valid" so CI can tell it apart from
  exit 1, "checks ran and failed". A new CI job builds the wheel, installs it into
  a clean environment, and runs it from a directory containing no source — the
  only configuration in which this class of defect is visible.
- **The liquidation-preference arithmetic was wrong, and overstated by 30%.** The
  required exit was computed as `(proceeds + preference) / ownership`, which
  divides the preference by ownership as though the investor had to fund the whole
  senior stack out of its own slice. A senior preference is paid off the top and
  the residual is then split, so the correct form is `preference + proceeds /
  ownership`. On the sample deck this was $192M rather than $148M. The unit test
  asserted the wrong figure too, which is how it survived; there is now a test of
  the defining property — after the stack is paid, the investor's share of what
  remains must equal exactly the proceeds it needed.
- **Every growth rate was treated as monthly.** The parser returned a bare float,
  discarding the period, so "23% CAGR" was compounded twelve times into a ~1,000%
  annual rate. Growth is now parsed into a `GrowthRate` carrying rate, period and
  the deck's own wording; an unlabelled rate extrapolates nothing and says why.
- **Citations to sources no model ever saw validated as genuine.** `citable`
  promised "sources that entered the evidence prompt" but returned everything
  unquarantined — while `prompt_block` silently truncated at a character budget.
  A citation to source 200 of 200 passed even though the block stopped at 40. The
  registry now records what it actually rendered, the prompt tells the model which
  sources were dropped, and the omission is reported in the run stats.
- **Citation integrity was only checked in one field.** The scorer looked at
  `comparison.claim_audit[].source_ids`, so a fabricated citation in the
  scorecard, a blind spot, the opportunity section or inline prose scored as
  clean. It is now collected recursively across the whole report, including bare
  `[S#]` references in text. This immediately caught the mock provider citing S2
  and S3 against a one-source corpus, which was a real defect and is also fixed.
- **HTTPS DNS pinning did not pin.** The connection was built with the validated
  IP and then had `conn.host` set back to the hostname to preserve the Host
  header — but `HTTPSConnection.connect()` resolves `self.host` itself, handing
  DNS a second chance to answer and reopening the exact time-of-check-to-time-of-use
  window the pin exists to close. The socket now connects to the checked IP and
  TLS is wrapped with `server_hostname` set to the original name, so certificate
  validation and vhost routing both still apply and DNS is never consulted twice.
- **A negative `Content-Length` bypassed the request size cap** on the local web
  server and turned `rfile.read(-1)` into an unbounded read.
- **Office files had no expansion limit**, so a few hundred KB of `.pptx` could
  expand to gigabytes inside python-pptx. Member count, total uncompressed size
  and compression ratio are now checked from the zip directory before any parser
  touches the file.
- **The Codex CLI preset never applied its sandbox.** `--sandbox` and
  `--ask-for-approval` are global flags and must precede the `exec` subcommand;
  placed after it they were parsed as arguments to `exec` and rejected.
  `--skip-git-repo-check` was also needed, since `exec` refuses to start outside a
  git repository and a user analyzing a deck in their Documents folder is not in
  one.
- **OpenAI reasoning models were sent the chat request shape**, which they reject:
  they require `max_completion_tokens` rather than `max_tokens` and a `developer`
  rather than `system` role. Retired names (`o3-mini`, `o1-mini`, `o1-preview`)
  now give an actionable error naming a working replacement, and the docs no
  longer recommend models the code itself refuses — `gemini-2.0-flash` appeared in
  the README while the provider raised on it as retired.
- **A panelist that declined to revise erased its earlier revisions.**
  `me.revised = {}` cleared every lens, so a panelist that improved in round one
  and was satisfied in round two was scored and voted on using its round-zero
  analysis. Revisions are now durable and a per-lens history is kept. Separately,
  `to_dict` keyed off `revised`, dropping any lens the panelist never changed its
  mind about from the output entirely.
- **The zero-dependency test runner had a hand-maintained module list**, so a new
  test file did not run until someone remembered to add it — the same class of
  defect as the evaluator. It now discovers `test_*.py` automatically.
- **"Deck-blind discovery" was an overstatement.** The cold pass is claim-blind:
  it never sees the deck's arguments, but the category it researches is the deck's
  own framing. A deck that calls itself "workflow automation" when the honest
  framing is "RPA" sends the pass to research the wrong market thoroughly and with
  citations. Documented accurately in the README, `docs/EVIDENCE.md` and the agent
  itself.

### Release readiness

- **The MCP integration was pinned to `2024-11-05`**, four revisions behind, on
  both the server and the client — and because it echoed one hardcoded constant
  rather than negotiating, nothing ever failed to reveal it. The current spec
  (`2026-07-28`) is a much larger change than a version bump: it replaces the
  `initialize` handshake with a stateless core where every request declares its
  own version in `_meta`, and makes `server/discover` mandatory. DeckScope is now
  **dual-era** on both sides. The server answers modern per-request traffic,
  implements `server/discover`, returns `UnsupportedProtocolVersionError`
  (`-32022`) listing what it does support, and still completes a legacy
  `initialize` — agreeing to the version the client asked for instead of
  announcing its own. The client probes `server/discover` first, treats a
  recognized modern error as a modern server and retries at a shared version,
  falls back to the handshake on anything else, and never stamps `_meta` on a
  legacy server that would not understand it.
- **A hash-pinned lockfile and a CycloneDX SBOM** are now generated on release
  (`.github/workflows/release.yml`, `scripts/generate_sbom.py`). Both are
  generated rather than committed by hand, because a lockfile has to record what
  a resolver actually chose against a real index, and an SBOM has to describe
  what was installed rather than what was requested. The generator is pure
  standard library — a bill of materials that needs its own dependencies adds to
  the surface it is meant to describe.
- **A clean-install acceptance test** (`scripts/acceptance.sh`) runs the commands
  a first-time user runs, from a directory with no source checkout, against the
  built artifact. It refuses to run inside the repository, where it would prove
  nothing.

  It immediately found another instance of the packaging defect above: **the
  sample decks were outside the package too**, so on an installed copy
  `demo --injected` fell through to the embedded deck, which contains no
  injection. The one command whose entire purpose is to show the security screen
  catching something printed a clean report and said nothing — a silently wrong
  answer, and worse than a crash because it reads as a pass. The decks now ship
  inside the package, and the injected demo refuses to run rather than
  substituting a clean deck if its fixture is ever missing again.

Test count 182 → 234, with a regression test for every finding above.

### Security — fixed (second audit)

- **The sanitizer could preserve, and in one case manufacture, an injection.**
  It scanned the original text, recorded character offsets, and only then stripped
  invisible characters and folded homoglyphs — both of which change the string, so
  the offsets no longer pointed at what they had matched. Two reproducible exploits:
  padding a document with zero-width characters shifted every later offset, so the
  redaction landed on an innocent sentence while the injection survived; and an
  injection written in Cyrillic lookalikes was folded into clean ASCII *after*
  scanning, producing a perfectly readable "ignore all previous instructions" that
  the scan had never seen. Order is now normalize → scan → redact → rescan, in one
  function, with a 300-case fuzz corpus over invisible padding, inline invisibles,
  homoglyphs and both combined.
- **Citation validation skipped entirely when no sources existed** — the strongest
  reason to check, since every citation is then fabricated. It now clears them and
  downgrades the evidence claim.
- **Quarantined sources counted as citable.** A source dropped by the screen is in
  the registry so the report can say it was dropped; it never entered the evidence
  prompt, so citing it cannot be genuine. Validation now uses `citable_ids`.
- **URL findings below `critical` did not drop a source**, despite the docs saying
  embedded credentials and punycode hosts would. Screening now asks one
  policy question (`quarantine_on`, default `medium`) instead of comparing
  severities at each call site.
- **DNS could be resolved twice** — once to validate, once to connect — leaving a
  rebinding window. Connections are now pinned to the validated address, with SNI
  and the Host header preserved. The redirect cap is enforced.
- **CLI providers now disable tools where the CLI supports it** (`--disallowedTools`
  for Claude, read-only sandbox for Codex) and **refuse to run** for presets
  DeckScope cannot verifiably restrict, unless `allow_unrestricted_cli` is set.
  Deck content reaching a tool-capable agent is a different class of problem from a
  biased report.
- **The cache moved out of the working directory.** It held cleartext deck
  extractions in a folder that gets committed, shared or cloud-synced by accident;
  it now lives in the per-user application directory with an owner-only ACL.

### Panel — fixed (second audit)

- **Revisions read the original comparison, not the previous revision**, so round
  three refined round zero and silently discarded round two.
- **Stopping used the first lens as a proxy for the whole panel.** Lenses ask
  different questions and converge at different rates; each now gets its own state,
  its own strategy instance and its own logged decision, and the panel continues
  while any lens is still moving.
- **Cross-review applied the first lens's stance to every lens** in a multi-lens
  packet. Each lens now carries its own posture.
- **Revisions and the chair's consensus were not validated**, so out-of-range
  scores and invented citations could reach the convergence metrics and the vote.

### Correctness and operations — fixed (second audit)

- **Gemini sent `temperature`** on every request. Its current generation rejects
  sampling parameters, so the default configuration could not complete a call.
  Request construction is now model-aware for both Gemini and OpenAI reasoning
  models.
- **A requested output format that could not be produced still exited zero.** It
  now exits 4, naming the formats and the missing packages.
- Two tests depended on a POSIX shell and passed in CI only because GitHub's
  Windows runner ships one. They now use the running Python.
- Lint restored to green: ambiguous `l` identifiers renamed, unused imports removed.
- `install.sh` and `install.command` carry the executable bit.
- **Documentation corrected**: `pptx` is a curated summary, not full parity with the
  other formats; and the local web token stops other *web pages* from driving
  DeckScope, not other *programs running as you* — the page is served
  unauthenticated so a browser can load it, and the token is in that page.

### Evidence and evaluation — added

- **`deckscope eval`** — the evaluation harness every audit said was missing. Scores
  DeckScope against decks whose correct answers are **known, because the deck and its
  evidence were authored together**: if the deck claims $88B and the frozen corpus says
  $6-8B, "contradicted" is correct as a matter of fact rather than taste.
  Five cases ship — inflated sizing, an omitted incumbent, evidence too thin to
  conclude from, a planted injection, and an honest control whose claims the evidence
  supports. The control is the important one: a system that calls everything
  contradicted scores well on the other four.
  Eight dimensions, all computed in Python and **never averaged**, because a system
  scores perfectly on fabrication by saying nothing and perfectly on recall by saying
  everything. `--trials` measures stability against frozen evidence; `--mode pipeline
  baseline` compares architectures on identical cases; exits non-zero so it can gate a
  release. The mock provider scores near zero on claim accuracy and 100% on the
  structural dimensions, which is the honest reading of a crude fixture — tuning it
  until it passed would have produced a suite that proves nothing.

- **Deck-blind market discovery** (`--cold-discovery`). The market analyst is given
  the deck's claims — it must be, it is checking them — which shapes its searches and
  makes it good at finding errors and bad at finding omissions. A second pass now
  receives **only the category, sub-category, geography and company name**, writes its
  own queries, and describes the market cold. The diff between the two routes is a
  blind spot no prompt could have produced.
  The isolation is **structural, not instructional**: a whitelist function builds the
  entire payload the agent may see, and tests assert on that payload — that no TAM
  figure, traction number, ask, competitor name or founder name can reach it, and that
  a newly added deck field cannot leak by default. On the sample deck the two routes
  overlap on 29% of the competitors they name; the cold pass alone surfaces ServiceNow,
  systems integrators and internal platform teams. Finding nothing is reported as a
  result rather than an empty section.
- **Frozen evidence corpora.** `--mode both` was not a valid control: each mode ran its
  own searches, so "the pipeline found more risks" might only have meant "the pipeline
  retrieved a page about risks". Research now runs once and both modes read identical
  bytes. The comparison states which case it is in, and says **"NOT SHARED — comparison
  is confounded"** rather than presenting confounded numbers as meaningful.
- **Reproducible research** via `--save-corpus` and `--corpus`. Replaying fixed evidence
  is what turns a prompt change from an anecdote into a measurement.
- **Comparison metrics no longer reward verbosity.** Counting claims, citations, risks
  and blind spots meant a mode that said more scored higher regardless of correctness.
  Replaced by citation density, uncited assertion rate, evidence-quality mix,
  unique findings **matched on content** so a rephrasing is not a discovery, and
  outright contradictions — the same claim assessed differently from the same evidence.
  It still refuses to name a winner, because that needs labelled decks or a blinded
  rubric and DeckScope ships neither.

### Analysis — added

- **Opportunity cost** (`--opportunity`). Checks which named competitors are publicly
  traded, pulls their actual historical returns, and computes what this company would
  have to reach to match holding them instead — ownership after dilution, exit value
  required, implied revenue, and the multiple of today's ARR that represents.
  **It does not forecast returns**, deliberately: a projected multiple with a confidence
  rating would be the least supportable number in a project built around refusing to
  state what it cannot cite. Every figure is arithmetic you can check by hand or an
  input that arrived with a citation, and the four assumptions behind it are printed
  with the result and settable per run.
- **Base rates**, sourced. How companies at this stage in this category have historically
  done, so the requirement has a denominator. Uncited rates are dropped rather than
  reported — a figure everyone quotes is still unsourced.
- **Absorption risk.** Whether the category survives as a standalone market at all: who
  could bundle it away, by what mechanism, what signals are *already* visible, and which
  precedents genuinely match. Antivirus, file sync and screen sharing were real markets
  with funded companies in them, and the companies were not out-competed so much as made
  redundant. "Unlikely this decade" is an accepted answer.
- **Saturation, quantified.** Funded competitor count, new-entrant trend, pricing
  direction, consolidation activity, lifecycle stage and room for a new entrant —
  because "concentrated" alone cannot distinguish an open wedge from a played-out
  category.
- **Adjacent markets**: what this converges with, what substitutes it, where it could
  expand.
- **Open-source landscape as an absorption signal.** Where a category has an
  open-source dimension it predicts bundling better than size or growth do: while OSS
  is behind, commercial products compete on capability; once it reaches parity,
  capability stops differentiating and what remains — packaging, operations,
  distribution — is exactly what a platform vendor already owns.
  Parity alone is not the test, though. DeckScope records both how close the closest
  project is AND what the commercial offering still provides, classifies each remainder
  by whether a platform could reproduce it cheaply, and derives the risk level in Python
  so the reasoning is inspectable and stable across runs. It reproduces the cases it was
  modelled on: Docker at parity with a distribution moat reads *severe*; Snowflake at
  near-parity with an operational moat reads *moderate*. A narrowing gap raises the
  reading; disagreement with the market agent's own product-or-feature verdict is
  surfaced rather than hidden.
- **Market-data backend registry**, mirroring providers and research. A search-based
  backend needs no new key; a dedicated API drops in behind the same interface. Rejects
  tickers that are really prose and returns outside a plausible band, since an
  unconverted percentage would silently corrupt every downstream figure. Keeps *listed*,
  *private* and *unknown* distinct.

### Panel — added

- **Stopping is now a strategy, not a constant.** `adaptive` (default), `convergence`,
  `confidence_floor` and `fixed`. Convergence can skip cross-review entirely when the
  panel already agreed independently; confidence_floor refuses to present a
  low-confidence result as settled and says so when it hits the cap. Every decision is
  logged, and the report shows the spread, agreement, position changes and contested
  claims after each round with the reason it continued or stopped.
- **Panelists rank each other's finished reports.** Borda count, self-votes structurally
  impossible, reasons required, and a preference cycle (A > B > C > A) reported as a
  cycle rather than broken arbitrarily. The chair's synthesis is still the headline, but
  each panelist's own report is kept intact beside it, ordered by the vote — a synthesis
  can smooth away the disagreement that is the point.
- The round sequence is driven by the strategy rather than hardcoded, so new stopping
  rules are a subclass rather than an edit to `Panel.run()`.

### Evaluation — added

- **Single-prompt baseline mode** (`--mode baseline`), and `--mode both` to run it
  alongside the pipeline on the same deck with identical screening and identical sources.
  Writes `mode_comparison.json` and prints verdict agreement, score gap, claims examined,
  claims carrying a citation, blind spots named, and cost in tokens and seconds.
  Deliberately declines to name a winner: whether the extra passes bought anything is a
  judgement about reasoning quality that a count cannot make.
- This is the control the architecture never had. The README no longer says the design is
  unmeasured; it says how to measure it.

### Security — fixed

- **Local web server could execute arbitrary files.** `GET /api/open` passed any
  path to the OS handler; on Windows that means running an executable. Any web page
  open in your browser could trigger it. Now: per-launch token, Origin validation,
  POST only, and restricted to files DeckScope itself produced. Body size, concurrent
  jobs and job retention are also capped.
- **Enforcement now follows detection.** Redaction is driven by the findings and
  their exact character spans, so a detected base64 payload is removed rather than
  reported and left in place, and `redact_on: high` redacts high-severity findings
  instead of silently only doing `critical`.
- **Dangerous-scheme URLs quarantine their source.** Previously a `javascript:` or
  `data:` result was flagged and then kept.
- **Concealment escalation is span-local.** One zero-width character no longer
  upgrades the severity of every later match in the document.
- **Unsafe URLs cannot become live links.** All hrefs pass through `safe_url`;
  anything that is not http(s)/mailto renders as inert text.
- **Remote deck fetching is SSRF-guarded.** Private, loopback and link-local
  addresses are refused, redirects are revalidated, downloads are size- and
  time-capped, and temporary files are uniquely named.
- **CLI providers are sandboxed.** Minimal environment, empty temporary working
  directory, and no-tool flags where the CLI supports them.
- **`get_settings` no longer returns secrets over MCP.**
- **API keys are genuinely owner-only on Windows**, via a real ACL rather than a
  `chmod` that does nothing there. `doctor` reports whether it worked.
- **Encoded-payload detection no longer rests on a length threshold.** It was 80
  characters, then 32, and both let real payloads through: `"ignore instructions"`
  encodes to 28 characters and `"you are now a promoter"` to 32 including padding the
  regex did not count. Length is now only a cheap pre-filter; the decode does the work,
  across both base64 alphabets and all padding lengths. Zero false positives on git
  SHAs, embedded images and tenant IDs.
- **The instruction-override pattern required a qualifier.** `"ignore all instructions"`
  matched; plain `"ignore instructions"` did not. Split into two forms so the
  unqualified case is caught without flagging "our rules engine lets admins override
  rules".

### Correctness — fixed

- **Panel citations could point at the wrong source.** Each panelist numbered its
  own bibliography from S1, and only one registry survived, so Panelist B's `S1`
  resolved against Panelist A's document. Registries are now merged into one global
  namespace before any cross-review, with every panelist's citations rewritten.
- **Claim agreement compared unrelated claims.** The matrix grouped by each
  panelist's own C-numbering. It now matches on content — quoted figures and
  significant words — and reports single-panelist claims as silence rather than
  disagreement.
- **The cache never actually hit.** Keys used `hash()`, which is randomized per
  process. Now SHA-256 over canonicalized inputs, bound to the exact sources, the
  security policy and a prompt epoch, with a TTL and owner-only permissions.
- **Token accounting was always zero**, because `complete_json` discarded the
  provider's response object. Usage is now tracked, including JSON-repair retries.
- **`--research none` fabricated a source.** It registered its own "no research was
  performed" notice as a cited bibliography entry. The registry now stays empty and
  the report says so plainly.
- **Model output is validated**, not merely coerced: enums, numeric ranges, row
  shapes, and citations to sources that were never supplied. Every repair is
  recorded in the report.

### Platform — fixed

- **Windows console output crashed all three demos.** Box-drawing characters cannot
  be encoded on a CP-1252 console. Output now goes through `deckscope.console`,
  which requests UTF-8 and transliterates when it cannot get it. A test forbids bare
  `print()` in the package.
- **Anthropic defaults returned HTTP 400.** `temperature` is rejected on Claude 4.7
  and later; it is now omitted for those models.
- **The default Gemini model was past its shutdown date.** Refreshed, with retired
  names mapped to an actionable error.
- **The test suite required optional packages**, so it failed on the minimal install
  the README recommends. It now skips formats whose dependency is absent.
- MCP client: enforced timeouts, drained stderr (a chatty server could deadlock),
  and out-of-order responses are buffered rather than discarded.

### Documentation

- Version dropped. This is unreleased software and now says so.
- Claims narrowed to what the code enforces: DeckScope screens **retrieved
  snippets**, not whole source pages; the panel is **role-separated analysis with
  model diversity**, not independent market discovery; citation resolution checks
  that a source exists, **not** that it supports the claim.
- Added a threat model, and a limitations section that states the three-agent design
  is unproven rather than merely unmeasured.

### Testing

- 163 tests, up from 42: one regression test per audit finding, plus full coverage of
  the stopping strategies, voting maths, baseline mode, opportunity-cost arithmetic
  (checked against hand calculations) and the bundling signal (checked against the real
  cases it models).
- The suite passes on a minimal install and on a legacy Windows console.

---

## Earlier

Initial implementation, before external audit.

### The pipeline

- Three isolated agents — **DeckAnalyst**, **MarketAnalyst**, **ComparisonSynthesist** —
  so the market view is never anchored on the deck's own framing. The extraction agent is
  forbidden from evaluating; the market agent researches the category without being told
  what the deck claims about it; only the third agent sees both.
- Three analytical lenses: **investor**, **founder**, **neutral**, each with its own
  stance, weighting and verdict scale.
- Deck ingestion for `.pptx` `.pdf` `.docx` `.md` `.txt` `.html` `.json` and URLs, with
  slide numbering, table and chart-category extraction, speaker notes, and detection of
  image-only PDFs.

### AI connections

- Nine backends behind one interface: `anthropic`, `openai`, `gemini`, `openrouter`,
  `groq`, `bedrock`, `openai_compatible` (Ollama, LM Studio, vLLM), `cli` (an agent CLI
  already signed in), `mcp`, `manual` (copy-and-paste, works with any chat AI), and `mock`
  for offline demos.
- Anthropic works through the official SDK when installed and plain HTTP otherwise.
- Optional `extract_provider` so a cheap model can do extraction and a strong one the
  reasoning.
- JSON self-repair with two retry rounds, and `health_check()` on every provider.

### Research

- Seven research backends: `tavily`, `serper`, `brave`, `exa`, `provider_native`, `mcp`,
  `none`, plus `auto` which picks whatever is available and degrades honestly.
- Search queries are generated from the deck's load-bearing claims and printed in the
  report.
- Running without research is supported and clearly labelled as unverified throughout.

### Security

- **Deck forensics**: re-opens the original file to recover text hidden by rendering —
  colour-matched to background, sub-point fonts, off-page and off-slide positioning,
  hidden slides, speaker notes, document metadata, PDF render mode 3.
- **Text screening**: fourteen intent patterns (instruction override, role hijack, fake
  system messages, chat-template delimiter spoofing, conceal directives, score and verdict
  manipulation, exfiltration, authority spoofing, fence-breaking) and five concealment
  signals (zero-width and bidi characters, Unicode tag-block smuggling with payload
  decoding, homoglyph evasion, base64 payloads).
- Severity escalates when intent and concealment co-occur.
- **Web source screening** with URL checks; hostile sources are dropped rather than
  sanitized, and the drop is recorded in the bibliography.
- Layered sanitization: strip → fold homoglyphs → redact visibly → fence with an in-band
  trust boundary.
- Four modes: `strict`, `balanced`, `permissive`, `off`.
- Every report carries an **Input integrity screen** section, including when clean.

### Citations

- `SourceRegistry` assigns stable IDs (`S1`, `S2`, …) at retrieval, before screening.
- Agents cite by ID; citations are resolved after the run by ID, URL or title.
- The complete bibliography is printed in every format, in three groups: cited, consulted
  but uncited, and dropped by the security screen — so absence of evidence is as visible
  as its presence.
- Quarantined sources can never be promoted to cited.

### The panel

- Several AI connections analyze the same deck independently and in parallel, then read
  each other's work **anonymized**, concede or hold each position with reasons, and revise.
- Agreement is **measured in Python** — verdict distribution, score spread and standard
  deviation, per-dimension contestedness, a claim × panelist agreement matrix, per-panelist
  movement — and handed to the chair as input.
- Consensus report leads with the disagreements, includes a minority report, and names
  blind spots the whole panel may share.
- Graceful degradation: a failed panelist is reported and the run continues; a lone
  survivor is labelled "single panelist — no cross-check was possible".

### Output

- Eight formats: `md`, `html`, `pdf`, `docx`, `pptx`, `xlsx`, `json`, `txt`, plus dedicated
  panel reports.
- Three themes: `slate`, `midnight`, `paper`.
- Self-contained HTML with no external assets; PDF via WeasyPrint, headless Chrome, or
  ReportLab.

### Interfaces

- Double-click installers for Windows, macOS and Linux that check Python, create a private
  environment, add Desktop shortcuts, and launch setup.
- Six-question guided setup wizard that tests every answer, plus `deckscope doctor`.
- A local drag-and-drop app window built on the standard library alone.
- Full CLI: `setup`, `app`, `run`, `panel`, `demo`, `doctor`, `providers`, `formats`,
  `config`.
- Python API: `analyze()` and `analyze_with_panel()`, plus `Pipeline` and `Panel`.
- An MCP server exposing `analyze_deck`, `analyze_deck_panel`, `scan_deck_security`,
  `list_capabilities`, `get_settings`.
- A portable skill for skill-aware assistants.

### Extensibility

- Thread-safe, lazily bootstrapped registries for providers, research backends and
  renderers. Adding to any of them is one call.

### Testing

- 42 tests covering the security layer, the pipeline, the registries and the panel — all
  runnable offline with no API key, via `pytest` or a zero-dependency runner.
