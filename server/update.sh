#!/usr/bin/env bash
# Runs before each hot loop run: take new code from main, unless it's the commit the loop just
# rolled back (memepaper.py guard writes that to ~/memepaper.hold). A newer commit clears the hold.
cd "$(dirname "$0")/.."
git fetch -q origin main
new=$(git rev-parse origin/main)
[ "$new" = "$(cat ../memepaper.hold 2>/dev/null)" ] || git merge -q --ff-only origin/main
