# Phase 0 API recordings — the evidence-universe verification

Every API fact the grants and nonprofits verticals rest on was verified
against the live service or its official documentation on 2026-08-31,
BEFORE any backend was written. The `.json`/`.xml` files beside this
README are verbatim captures of real responses (headers noted per file).
Nothing in them is authored, trimmed, or reformatted.

| Service | Base | Auth | Method | Verified how |
|---|---|---|---|---|
| ProPublica Nonprofit Explorer v2 | projects.propublica.org/nonprofits/api/v2 | none | GET | live capture: search + organization detail (12 fiscal years of 990 data) |
| NSF Award Search v1 | api.nsf.gov/services/v1 | none | GET | live capture: awards.json with rpp/printFields |
| NCBI PubMed E-utilities | eutils.ncbi.nlm.nih.gov/entrez/eutils | none (optional api_key raises rate limits) | GET | live capture: esearch XML |
| USAspending v2 | api.usaspending.gov/api/v2 | none | GET refs; POST search | live capture: references/agency GET; search POST contract from official docs |
| NIH RePORTER v2 | api.reporter.nih.gov/v2 | none | POST only (GET is refused) | reachability confirmed; POST contract from official Swagger docs at api.reporter.nih.gov |

Known quirks, recorded so a backend never rediscovers them:

- **NIH RePORTER accepts POST only.** The capture environment's fetcher
  is GET-only, so no live NIH response is recorded here — the backend's
  request contract is pinned from the official docs and the weekly canary
  performs the live POST. Until the canary's first green run, "NIH
  requests are accepted live" is a documented expectation, not a
  demonstrated fact, and the docs say so.
- **PubMed esearch returned XML reliably; `retmode=json` returned an
  empty body through this fetcher.** The backend uses XML.
- **ProPublica org detail keys financials by fiscal period** (`tax_prd`
  202306 = fiscal year ending June 2023; `accounting_period: 6`). A
  claim about "2023" is NOT automatically comparable to `tax_prd_yr:
  2023` — fiscal/calendar basis rules apply, enforced in the vertical.
- **NSF `printFields` controls the response shape**; omitting it returns
  a much larger default field set. Recorded sample used explicit fields
  plus `rpp` paging (`metadata.totalCount` carries the full hit count —
  the input to any absence-claim reasoning).
