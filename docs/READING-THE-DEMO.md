# Follow a finding back to its evidence

Use this walk through when deciding whether a report deserves further investigation. It follows the included **synthetic Acme Flow** deck through real report code, without a provider account or live research.

## Reproduce the trace

From the installed checkout:

```sh
python -m deckscope demo --out output --format html md json
python -m examples.inspect_demo output/acme_flow_full.json
```

Open `output/acme_flow_investor.html` beside the printed trace. The [captured trace](../examples/catalogue-demo/trace.json) contains only selected fixture fields, rather than the full runtime configuration. The example rejects non-mock reports and requires the selected evidence to be admitted fixture material.

## Claim, assessment, source, finding

1. The [sample deck](../deckscope/examples/sample_deck.md) supplies a market-size and growth claim. The mock comparison records it as **C1** in `comparisons.investor.claim_audit`.
2. C1 carries `assessment`, `delta` and `source_ids`. Its disagreement is supplied by the mock analysis; Python does not independently prove it.
3. C1 names **S1**. `references.sources` holds S1's title, snippet, status and `demo_fixture` backend; `references.admitted` records its admission. In the HTML report, follow the finding's source reference to the reference entry.
4. [findings.collect](../deckscope/findings.py) groups that assessment as contested and computes the counts. The supplied six claims yield two contested claims and two unknowns; two omissions come from the comparison's blind spots. Unknowns are research questions, not disproved claims.

The fixture's market figures and references are invented demonstration inputs. Nothing in this trace establishes the real market size, checks an external webpage, or grades a live model. An admitted source identifier establishes an internal evidence connection; a reader still has to assess the original evidence in a live report.

## How the pieces meet

[orchestrator.py](../deckscope/orchestrator.py) keeps the deck, market research and comparison in the full result. [sources.py](../deckscope/sources.py) maintains source identities and citation auditing. [findings.py](../deckscope/findings.py) projects questions and findings from those structured fields; [html_renderer.py](../deckscope/render/html_renderer.py) presents the result with a mock-provider label.

If a citation is absent or cannot be resolved, do not infer that the claim was verified. The findings layer retains unsourced contested rows at low severity, and the report can identify thin evidence. A populated report is not the same as a sufficiently supported decision.

## Before trying a real document

Use [QUICKSTART.md](QUICKSTART.md) to configure a provider deliberately. Hosted analysis and enabled web research can send information beyond your machine. Generated full JSON may include local paths and configuration; inspect it before sharing. The public example is a selected projection of synthetic data.

[GOALS.md](../GOALS.md) preserves the larger research direction. Testing against dated, external answer keys would be needed to support those broader claims; improving this fixture alone cannot establish them. Grant and nonprofit routes remain separately scoped and ungraded as described in the project guide.
