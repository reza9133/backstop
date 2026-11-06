#!/usr/bin/env bash
# Offline rehearsal of the live run: the real contract runs in the local test runner, a stub plays genlayer-js and
# the network, and scripts/e2e.mjs runs against it unchanged. It checks the script's logic, not the real AI.
# The chain clock runs TIME_SCALE times faster (default 60), so the minutes of waiting take seconds.
#   bash rehearsal/run.sh                                  all scenarios, the model finds no event (level 0)
#   READ_LEVEL=2 bash rehearsal/run.sh --only lifecycle    the model reads level 2 (a payout)
#   READ_LEVEL=1 APPEAL_LEVEL=2 bash rehearsal/run.sh --only contest   the appeal overturns the reading
#   BIND_MODE=refuse bash rehearsal/run.sh --only lifecycle   the inception check finds the event already happened
#   VET_REFUSE_PRIMARY=1 bash rehearsal/run.sh                 the model refuses the standard wording, the fallback wording is used
set -e
here="$(cd "$(dirname "$0")/.." && pwd)"
work="$here/.rehearsal-tmp"
rm -rf "$work"
mkdir -p "$work"
cp -r "$here/scripts" "$work/scripts"
ln -s "$here/contracts" "$work/contracts"
cp -r "$here/rehearsal/stub/node_modules" "$work/node_modules"
cp "$here/package.json" "$work/package.json"
export REHEARSAL_ROOT="$here"
export TIME_SCALE="${TIME_SCALE:-60}"
export INSURED_KEY=0x$(printf '1%.0s' $(seq 1 64))
export BACKER_KEY=0x$(printf '2%.0s' $(seq 1 64))
export BACKER2_KEY=0x$(printf '3%.0s' $(seq 1 64))
export BACKSTOP_ADDRESS=0x$(printf 'ab%.0s' $(seq 1 20))
export REPORT_DIR="$here/reports/rehearsal"
cd "$work"
node scripts/e2e.mjs "$@"
