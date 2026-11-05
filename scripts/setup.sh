#!/usr/bin/env bash
# Installs everything the tests and the live run need. Safe to run more than once.
cd "$(dirname "$0")/.." || exit 1
set -e
echo "== python packages"
python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r requirements.txt
echo "== node packages"
npm install --no-audit --no-fund
echo "== done. Next:  npm run keys   then   bash scripts/run-all.sh"
