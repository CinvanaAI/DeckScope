# Corpus provenance

| File | Company | Form | Filed | SIC | Captured |
|---|---|---|---|---|---|
| sections/klaviyo_2023_S1_partial.txt | Klaviyo, Inc. (KVYO) | S-1 | 2023-08-25 | 7372 | first 142KB of 3.3MB |
| sections/figs_2021_S1_partial.txt | FIGS, Inc. (FIGS) | S-1 | 2021-09-13 | 2300 | first 120KB |
| sections/uslighting_2023_S1_full.txt | U.S. Lighting Group (USLG) | S-1 | 2023-09-01 | — | full (negative control) |
| sections/agilon_2021_S1_partial.txt | agilon health, inc. (AGL) | S-1 | 2021-03-18 | 8090 | first 144KB |
| sections/privia_2021_S1_partial.txt | Privia Health Group (PRVA) | S-1 | 2021-04-07 | 8000 | first 144KB |
| studies/cricut_2021_EX99-1_yougov_TAM_study.txt | Cricut, Inc. (CRCT) | S-1 EX-99.1 | 2021-02-16 | 3559 | full |

## Retrieval constraint

`web_fetch` truncates at ~142KB mid-word. Klaviyo's S-1 is 3,303,389 bytes in a
single .htm file — no multi-part split to exploit. We capture the cover, Select
Defined Terms, and the Prospectus Summary. The Business section's full Industry
discussion is past the ceiling.

This is survivable because the Prospectus Summary restates the market opportunity
in compressed form WITH its methodology, which is the part we need. It is not
survivable if we later want the full competitive landscape narrative.

## Negative control

U.S. Lighting Group is deliberately kept. It is an S-1 that fetches complete and
contains no industry section at all — a "Competition" heading, no market size, no
methodology, no sources. ~90%+ of S-1 filings look like this. Any corpus filter
we build must exclude it, and it is the test case for whether the filter works.

## Cycle 2 addition

agilon health and Privia Health added to test the Count x Rate x Value formula
against a regulated, non-technology, services market. The formula held for
agilon and was not visibly applied by Privia.

agilon is now the strongest single document in the corpus: it states its base
(CMS beneficiary counts), its qualifying filter (independent PCPs, named
states), its value term ($10,000 revenue per member), its forward projection
(CMS's own growth rates, footnoted), and three concentric geographic rings
sized separately. It also cross-references its own TAM to its risk factors.

Privia is retained as a weak-case example: it opens at $3 trillion of national
health spend and does not narrow within the captured range.
