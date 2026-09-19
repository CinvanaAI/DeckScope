# DeckScope synthetic report

[Open the HTML report](report.html) or inspect [the findings projection](findings.json).

These files were produced by the real offline `deckscope demo` path using the supplied sample deck and mock provider. The HTML is the actual renderer output. The JSON projects the findings layer from the generated report and excludes machine-local configuration, paths, logs, and security metadata.

The report examines six fixture claims and groups two contested claims, two omissions, and two unknowns. That demonstrates how the report is organized; it is not a result from real diligence or an evaluation of model quality.

Reproduce from the repository root:

```sh
python -m deckscope demo --out output --format html md json
```

Generated full JSON can include local input paths. Review it before sharing. The example report's source links are fixture references; the demo does not retrieve them live.
