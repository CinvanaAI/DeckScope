#!/usr/bin/env bash
#
# The first-run acceptance test: what a person who has just installed DeckScope
# does, in a directory with no source checkout.
#
# This exists because every other check in CI runs from the repository, where
# files that are missing from the built package are still on disk and still
# importable. That is exactly what hid the packaging defect where the evaluation
# fixtures shipped outside the package: the gate passed everywhere it was run,
# and failed only once someone installed the thing.
#
# Usage:  bash scripts/acceptance.sh /path/to/python
#
# Must be run from a directory containing no DeckScope source.

set -euo pipefail

PY="${1:-python3}"
FAILED=0

step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  ok   %s\n' "$*"; }
bad()  { printf '  FAIL %s\n' "$*"; FAILED=1; }

# Guard: if there is a deckscope/ directory here, we are not testing an install.
if [ -d "./deckscope" ]; then
  echo "Refusing to run: there is a deckscope/ directory in $(pwd)."
  echo "This test is only meaningful outside a source checkout."
  exit 2
fi

step "1. It is installed and reports a version"
"$PY" -m deckscope --version && ok "deckscope --version" || bad "--version"

step "2. It can list what it supports without any configuration"
"$PY" -m deckscope providers >/dev/null && ok "providers" || bad "providers"
"$PY" -m deckscope formats   >/dev/null && ok "formats"   || bad "formats"

step "3. The install check runs and reports honestly"
# `doctor` exits non-zero on a fresh install because nothing is configured yet —
# that is the correct answer, not a failure. What must not happen is a crash.
set +e
"$PY" -m deckscope doctor >/tmp/_doctor.txt 2>&1
code=$?
set -e
if [ "$code" -le 1 ] && grep -qi "health check" /tmp/_doctor.txt; then
  ok "doctor ran (exit $code — unconfigured is expected on a fresh install)"
else
  bad "doctor exited $code without producing a health check"
fi

step "4. A first-time user can see a real report with no AI account"
"$PY" -m deckscope demo --format md json --out ./_accept >/dev/null
if [ -s ./_accept/*.md ] 2>/dev/null || ls ./_accept/*.md >/dev/null 2>&1; then
  ok "demo wrote a markdown report"
else
  bad "demo produced no report"
fi
if ls ./_accept/*.json >/dev/null 2>&1; then
  ok "demo wrote structured JSON"
else
  bad "demo produced no JSON"
fi

step "5. The security screen works on an installed copy"
"$PY" -m deckscope demo --injected --format md --out ./_accept_inj >/dev/null
if grep -q "CRITICAL" ./_accept_inj/*.md; then
  ok "the planted injection was caught"
else
  bad "the injection demo did not report CRITICAL"
fi

step "6. The evaluation gate shipped with the package and can fail"
# Exit 1 means it ran and some checks failed, which is expected under the mock.
# Exit 0 with nothing run is the defect this whole script exists to catch.
set +e
# ---------------------------------------------------------------- new surfaces
#
# The clean-wheel gate previously exercised only the classic pipeline, which is
# why it passed while `marketreport` was absent from the wheel entirely and
# `research --save` crashed on every invocation. A gate is only as wide as the
# surfaces it touches, and every failure of this kind clustered in the parts it
# did not.

"$PY" -c "import marketreport, marketreport.sizing, marketreport.sources.census" \
  && ok "marketreport imports from the installed wheel" \
  || bad "marketreport is missing from the wheel"

# Exit 6 means 'ran correctly, established nothing' — expected without a Census
# key, and distinct from a crash. Anything else is a real failure.
"$PY" -m deckscope size 561730 --state 04 >/dev/null 2>&1
rc=$?
if [ "$rc" = "0" ] || [ "$rc" = "6" ]; then
  ok "size runs (exit $rc)"
else
  bad "size crashed (exit $rc)"
fi

# The sample deck must come from the INSTALLED package, not a source-tree
# path. This script runs in an empty directory by design, and the old
# checkout-relative path (deckscope/examples/sample_deck.md) existed only
# in a checkout — the one place this script refuses to run. The clean-wheel
# CI job was red on exactly this: the wheel was fine and the address wrong
# (external audit finding).
SAMPLE="$("$PY" -c "import deckscope.cli, pathlib; print(pathlib.Path(deckscope.cli.__file__).resolve().parent / 'examples' / 'sample_deck.md')")"
[ -f "$SAMPLE" ] && ok "packaged sample deck found" || bad "packaged sample deck missing: $SAMPLE"
"$PY" -m deckscope research "$SAMPLE" --demo \
  --max-iterations 4 -q --save ./_accept_research.json >/dev/null 2>&1 \
  && ok "research --demo --save" || bad "research --demo --save"
"$PY" -c "import json,sys; json.load(open('./_accept_research.json'))" \
  && ok "the saved evidence table is valid JSON" \
  || bad "research --save wrote a file that will not parse"

"$PY" -m deckscope eval --provider mock --save ./eval.json --out ./_accept_eval >/dev/null 2>&1
code=$?
set -e
if [ "$code" -eq 0 ] || [ "$code" -eq 1 ]; then
  cases=$("$PY" -c "import json;print(len(json.load(open('./eval.json'))['scores']))")
  if [ "$cases" -gt 0 ]; then
    ok "the installed evaluator scored $cases case(s)"
  else
    bad "the installed evaluator ran zero cases and did not say so"
  fi
else
  bad "eval exited $code (2 means the suite is missing from the package)"
fi

step "7. A run that checks nothing fails instead of passing"
for bad_args in "--trials 0" "--only definitely-not-a-case"; do
  set +e
  # shellcheck disable=SC2086
  "$PY" -m deckscope eval --provider mock $bad_args --out ./_accept_bad >/dev/null 2>&1
  code=$?
  set -e
  if [ "$code" -eq 0 ]; then
    bad "'eval $bad_args' exited 0 while checking nothing"
  else
    ok "'eval $bad_args' refused to run"
  fi
done

step "8. The MCP server completes a handshake in both protocol eras"
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28"}}}' \
  | "$PY" -m deckscope.mcp_server 2>/dev/null | grep -q "supportedVersions" \
  && ok "modern: server/discover" || bad "modern handshake"
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}' \
  | "$PY" -m deckscope.mcp_server 2>/dev/null | grep -q "protocolVersion" \
  && ok "legacy: initialize" || bad "legacy handshake"

printf '\n'
if [ "$FAILED" -eq 0 ]; then
  echo "Clean-install acceptance: PASSED"
  exit 0
fi
echo "Clean-install acceptance: FAILED"
exit 1
