#!/usr/bin/env bash
# Trade from the 4-hour Claude review or a local session: runs a memepaper command in state mode
# and pushes the order file it writes to the `state` branch. The hot loop applies it within about
# a minute and records the result in orders/done/. Books are the loop's: this never writes them.
#   ./order.sh status                      # books, pending orders, the last results
#   ./order.sh screen <mint...>
#   ./order.sh gate <mint...>               # prints PASS/FAIL now; the loop records the passes
#   ./order.sh buy <mint> <sol> "<thesis>" [--stop -0.35] [--tp1 1.0]
#   ./order.sh sell <mint> <fraction> "<reason>"
# Paper only: no wallet, no keys, no real orders.
set -eu
cd "$(dirname "$0")"
PY="${PY:-python3}"
BR="${MEMEPAPER_BRANCH:-state}"
WT="${MEMEPAPER_WT:-$PWD/.state}"
case "${1:-}" in status|screen|gate|buy|sell) ;; *) sed -n '2,10p' "$0"; exit 2;; esac
git fetch -q origin "$BR"
[ -e "$WT/.git" ] || git worktree add -q --detach "$WT" "origin/$BR"
git -C "$WT" reset -q --hard "origin/$BR"   # a scratch copy: start from what the loop pushed
MEMEPAPER_STATE="$WT" "$PY" -I memepaper.py "$@"
case "$1" in status|screen) exit 0;; esac
git -C "$WT" add orders
git -C "$WT" commit -qm "order: $1 $(date -u +%FT%H:%MZ) by ${MEMEPAPER_BY:-local}" || exit 0
for _ in 1 2 3; do
  git -C "$WT" push -q origin "HEAD:$BR" && exit 0
  git -C "$WT" fetch -q origin "$BR" && git -C "$WT" rebase -q "origin/$BR"
done
echo "order.sh: push to $BR failed 3 times; the order was not sent" >&2
exit 1
