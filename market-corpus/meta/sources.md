# Corpus provenance

Every file in this corpus, where it came from, and how to get it again.
Retrieved 2026-08-26 via the SEC EDGAR full-text search and archive endpoints.

Licensing: see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). These are
third-party documents included as research material. They are **not** covered
by this repository's MIT licence.

| File | Company | CIK | Accession | Form | Filed | SIC | sha256 (16) | Bytes |
|---|---|---|---|---|---|---|---|---|
| `sections/klaviyo_2023_S1_partial.txt` | Klaviyo, Inc. (KVYO) | 0001835830 | [0001628280-23-030618](https://www.sec.gov/Archives/edgar/data/1835830/000162828023030618/klaviyoincs-1.htm) | S-1 | 2023-08-25 | 7372 | `2265d4fde44b47b8` | 142,173 |
| `sections/figs_2021_S1_partial.txt` | FIGS, Inc. (FIGS) | 0001846576 | [0001193125-21-271933](https://www.sec.gov/Archives/edgar/data/1846576/000119312521271933/d213818ds1.htm) | S-1 | 2021-09-13 | 2300 | `4322b5091b06f1f4` | 120,793 |
| `sections/agilon_2021_S1_partial.txt` | agilon health, inc. (AGL) | 0001831097 | [0001193125-21-085566](https://www.sec.gov/Archives/edgar/data/1831097/000119312521085566/d10763ds1.htm) | S-1 | 2021-03-18 | 8090 | `85daf033489c7416` | 144,814 |
| `sections/privia_2021_S1_partial.txt` | Privia Health Group, Inc. (PRVA) | 0001759655 | [0001193125-21-108380](https://www.sec.gov/Archives/edgar/data/1759655/000119312521108380/d92164ds1.htm) | S-1 | 2021-04-07 | 8000 | `7272911b081e632d` | 144,759 |
| `sections/uslighting_2023_S1_full.txt` | U.S. Lighting Group, Inc. (USLG) | 0001536394 | [0001213900-23-072929](https://www.sec.gov/Archives/edgar/data/1536394/000121390023072929/ea184419-s1_uslighting.htm) | S-1 | 2023-09-01 | — | `6e8867a2ca8b7be4` | 148,731 |
| `studies/cricut_2021_EX99-1_yougov_TAM_study.txt` | Cricut, Inc. (CRCT) | 0001828962 | [0001564590-21-006015](https://www.sec.gov/Archives/edgar/data/1828962/000156459021006015/crct-ex991_713.htm) | S-1 EX-99.1 | 2021-02-16 | 3559 | `749ccf12ada61b03` | 1,680 |

## Capture extent

`web_fetch` truncates at roughly 142KB. Klaviyo's S-1 is 3,303,389 bytes in a
single .htm file, so these are byte-prefixes of the filing, not whole
documents — reliably the Prospectus Summary and the Risk Factors Summary, and
reliably not the Business section's full Industry discussion.

Verify a file still matches what EDGAR serves:

```bash
python scripts/verify_corpus.py
```

## Negative control

U.S. Lighting Group is kept deliberately. It is an S-1 that fetches complete
and contains no industry section at all — a `Competition` heading, no market
size, no methodology, no sources. Around 90% of S-1 filings look like this,
and it is the test case for whether the corpus filter works.

## Cycle 2 note

agilon health is the strongest document here: it states its base (CMS
beneficiary counts), its qualifying filter (independent PCPs, named states),
its value term ($10,000 revenue per member), its forward projection (CMS's own
growth rates, footnoted), and three concentric geographic rings sized
separately. It also cross-references its own TAM to its risk factors.

Privia is retained as a weak case: it opens at $3 trillion of national health
spend and does not narrow within the captured range.
