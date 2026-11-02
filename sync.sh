#!/usr/bin/env bash
# One watcher tick: pull the book, reprice it (stops, take-profits, time stop), push it back.
# Pushes only when a trade happened or the last commit is 30+ minutes old, so git isn't
# flooded with a commit every 2 minutes. If VAULT is set, copies the book into the vault.
# Paper only: public prices (DexScreener, CoinGecko), no keys, no wallet.
set -u
cd "$(dirname "$0")"
PY="${PY:-python3}"
resync() { git rebase --abort 2>/dev/null; git fetch -q origin && git reset -q --hard origin/main; }
# Save any marks made outside this script (manual trades, the old watcher) before pulling.
git add book.json book.md && git commit -qm "local mark $(date -u +%FT%H:%MZ)" 2>/dev/null || true
git pull -q --rebase origin main || resync
nlog() { "$PY" -I -c "import json;print(len(json.load(open('book.json'))['log']))"; }
before=$(nlog)
"$PY" -I memepaper.py mark --quiet || exit 1
after=$(nlog)
last=$(git log -1 --format=%ct 2>/dev/null || echo 0)
if [ "$after" != "$before" ] || [ $(( $(date +%s) - last )) -ge 1800 ]; then
  git add book.json book.md
  git commit -qm "mark $(date -u +%FT%H:%MZ)$([ "$after" != "$before" ] && echo ' (trade)')" || true
  git push -q origin main || { git pull -q --rebase origin main && git push -q origin main; } || resync
fi
if [ -n "${VAULT:-}" ]; then
  cp book.md "$VAULT/output/trading/2026-11-01-memecoin-paper-book.md"
  cp book.json "$VAULT/output/trading/2026-11-01-memecoin-paper-book.json"
fi
