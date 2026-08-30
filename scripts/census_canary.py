"""Live canary: the Census requests this build sends must still be accepted.

The third external audit found every live Economic Census request asking for
a variable the endpoint does not expose (NAICS2017 against the 2022 EC,
which publishes NAICS2022) — invisible to the whole suite because every test
stubs the HTTP layer, correctly, for hermeticity. The parameter-level tests
now pin what is SENT; this canary is the other half: whether the real
endpoint still ACCEPTS it. Schemas drift on the server's schedule, not ours.

Deliberately NOT part of the per-commit gates: a commit gate must be
hermetic, and a Census outage is not a defect in this tree. This runs on a
weekly schedule (and on demand) from .github/workflows/canary.yml, driving
the actual census.py code path — not a hand-built request that could pass
while the shipped one fails.

Requires CENSUS_API_KEY (census.py refuses keyless requests by design —
the key is free and instant). A canary that cannot fly must say so, not
show green: a missing secret is an explicit failure with the fix named.

Exit 0: both datasets answered through the shipped code. Exit 1: a request
this build would send live was refused — the NAICS2022 class of defect.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marketreport.sources import census  # noqa: E402

#: Landscaping services — the demo's own market: national CBP count and
#: state-level EC receipts, the exact two shapes the sizing agents send.
NAICS = "561730"


def main() -> int:
    import os
    if not os.getenv("CENSUS_API_KEY"):
        print("FAIL: CENSUS_API_KEY is not set, so this canary measured "
              "nothing. Add the repository secret CENSUS_API_KEY (free, "
              "instant: https://api.census.gov/data/key_signup.html). A "
              "canary that skips silently is a green light wired to "
              "nothing — so this is a failure, not a skip.")
        return 1
    failures = []
    for label, call in (
        ("CBP establishment count (national)",
         lambda: census.establishment_count(NAICS)),
        ("EC revenue per establishment (state 04)",
         lambda: census.revenue_per_establishment(NAICS, state_fips="04")),
    ):
        try:
            term = call()
        except census.Unavailable as exc:
            # The endpoint refused or lacked the data. For these two known-
            # published series that means the request no longer matches the
            # schema — the exact drift this canary exists to catch.
            failures.append(f"{label}: refused — {exc}")
            print(f"  FAIL {label}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - a canary crash is a red canary
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
            print(f"  FAIL {label}: {type(exc).__name__}: {exc}")
            continue
        value = getattr(term, "value", None)
        if not value:
            failures.append(f"{label}: answered but empty")
            print(f"  FAIL {label}: answered but empty")
        else:
            print(f"  ok   {label}: {value}")

    if failures:
        print(f"\n{len(failures)} live request(s) this build sends were not "
              f"accepted. If the Census schema moved, fix _naics_var / the "
              f"dataset constants; if the API is down, re-run later.")
        return 1
    print("\nthe requests this build sends are accepted live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
