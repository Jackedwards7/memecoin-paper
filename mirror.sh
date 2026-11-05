#!/usr/bin/env bash
# The Mac's read-only copy of the books into the vault (after the 2026-11 cut-over, replacing
# sync.sh). Fetches the `state` branch and copies the report and books. Never commits or pushes.
set -u
cd "$(dirname "$0")"
git pull -q --ff-only origin main || true   # keep local code current for order.sh
git fetch -q origin state || exit 1
out="${VAULT:?set VAULT to the vault folder}/output/trading"
for pair in book.md:2026-11-01-memecoin-paper-book.md \
            books/claude.json:2026-11-01-memecoin-paper-book.json \
            books/control.json:2026-11-01-memecoin-paper-control.json; do
  git show "origin/state:${pair%%:*}" > "$out/${pair##*:}.tmp" && mv "$out/${pair##*:}.tmp" "$out/${pair##*:}"
done
