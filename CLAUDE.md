# Memecoin paper book

A **paper** (fake-money) memecoin book that Claude trades on its own judgement for Jackson
(he asked for it 2026-11-01). Start 10 SOL. No wallet, no keys, no real orders, ever: every fill
is simulated by `memepaper.py` from live public prices. Never add a private key or wallet here.

## Rules v2 (from 2026-11-03)
Jackson chose on 2026-11-03 to replace the v1 rules with the research playbook (`PLAYBOOK.md`).
v1 ended at 3 closed trades, all stop-losses. Its 4 open positions run on under the same exits as
legacy positions and are left out of the v2 test.

## Success test
Review on 2026-11-30 or after 30 closed v2 trades, whichever is first. Two questions:
1. Do picks beat the **control arm** (a random coin that passed the same gates, same size, same
   exits) after costs? If not, the picking adds nothing.
2. Is the book ahead of plain SOL holding (a positive SOL-denominated return after fees)?
The gate is judged on **losses avoided**: every coin it passes and every coin it fails is scored at
1, 3 and 7 days ("Gate value" in the report). The best published filter only halved losses, so
passes beating rejects is the bar, not passes making money.
**No rule changes before the review.** Filters stop working within weeks, so the review re-checks
every rule against the data.

## How it runs (from the 2026-11 cut-over, Tier 1 phase 2)
- **The hot loop** (GitHub Actions, `.github/workflows/hot-loop.yml`) is the only writer of the
  books. Every 60 s it applies new orders, reprices every book and applies the exit rules below.
  It alerts Jackson's phone (ntfy) on trades and failures; a separate watchdog alerts if it stops.
- **Data lives on the `state` branch**, code on `main`. `state` holds `books/claude.json` (picks),
  `books/control.json` (control arm), `book.md` (the report), `orders/` (the inbox) and
  `orders/done/` (each order with its result), plus `health.json`.
- **You trade by order, never by editing a book.** `./order.sh` runs a command in state mode and
  pushes the order it writes; the loop applies it within about a minute:
  - `./order.sh status`: the report, pending orders, the last results and the loop's health.
  - `./order.sh screen <mint...>`: live stats (read only).
  - `./order.sh gate <mint...>`: prints PASS/FAIL now; the loop records the passes.
  - `./order.sh buy <mint> <sol> "<thesis>" [--stop -0.35] [--tp1 1.0]`: the loop re-runs the
    gate when it applies the buy, refuses an order over 30 minutes old, and opens the control.
  - `./order.sh sell <mint> <fraction> "<reason>"`.
  A refused order is a normal outcome: its reason is in `status`. Never edit files on `state`.
- **Every 15 minutes the loop also snapshots the universe** (see Arms and dataset). `state` then
  holds `data/` too, plus `watch.json` and `gate.json`. Its gate results are recorded in the picks
  book like yours, so your control draws from every recent pass, not only the coins you gated.
- **Files on `main`:** `memepaper.py` (all the logic; always `python3 -I`), `order.sh`,
  `mirror.sh` (the Mac's read-only copy into Jackson's vault), `PLAYBOOK.md` (the research behind
  these rules: read it before judging a coin), `tests/` (offline; `python3 -I -m unittest discover
  -s tests -t .`). `main` is protected: changes land by pull request with the tests passing. The
  review run never edits code.

## Costs (in the script)
1.5% fee each side (PumpSwap pool fee plus terminal and priority fees), a slippage charge based on
size against liquidity, and from 2026-11-03 a $0.50 sandwich (MEV) charge per swap (a guess at
about 1 in 10 swaps hit at the $5 median; the report also shows P&L if every swap were hit).
Never trade a coin still on the bonding curve, or one that migrated in the last 2 hours.

## Exit rules (applied by the hot loop every minute, no judgement needed)
Hard stop −25% to −35% per position; sell half at the take-profit (+60% to +100%); then a 40%
trailing stop from the peak; time stop after 48h without the take-profit if under +20%.
From 2026-11-03 (Tier 1 phase 2, both books alike): an **event exit** sells everything at once when
pool liquidity is down 40%+ since entry or the price is down 20%+ in 5 minutes. A coin missing from
the price call is marked to zero only after 30 minutes missing *and* when DexScreener search finds no
pool with $1k+ and RugCheck calls it rugged or shows under $1k pooled (or after 24h missing). This
replaces "3 checks in a row", which a 60-second loop would trip on a 3-minute API blip.

## Judgement exits (the review run, picks only)
Sell (`./order.sh sell <mint> 1 "<reason>"`) if: sellers lead buys for 2+ hours while the price slides;
hourly volume under ~20% of its recent level; liquidity pulled or falling fast; the coin's theme is
clearly rotating away (see `/metas/trending/v1` below). Write the reason plainly.

## Entries
At most ONE new entry per run, and only if cash > 5 SOL and fewer than 6 open v2 positions.
Size **0.25 SOL** (the script caps it). Steps:
1. **Candidates:** Solana mints ending in `pump` from DexScreener
   `https://api.dexscreener.com/token-profiles/latest/v1` and `/token-boosts/top/v1`.
   Boosts are paid ads: a candidate list only, never a reason to buy.
2. **Universe:** keep those with pair age ≥ 6h (cloud) / ≥ 2h (local) and liquidity ≥ $75k
   (`./order.sh screen` shows both).
3. **Gate every coin in the universe**, not just your favourite, in one call:
   `./order.sh gate <mint> <mint> ...`. The script checks mint and freeze authority revoked, no risky
   Token-2022 extension, deepest pool is the graduation pool with LP ≥ 90% locked, no wallet over
   5%, insiders ≤ 15%, creator ≤ 10%, no RugCheck danger (including a creator history of rugs), and
   that it is the original, not a copycat of an earlier coin with the same name. Anything it can't
   check fails. The control arm draws at random from all passes, so gating only your pick breaks
   the test.
4. **Pick** from the passes only. Prefer coins that also show 1h buys > sells, 1h and 24h price change
   positive, and a 5m move under +25% (no buying a vertical spike). Same theme counts at most twice
   across open positions. If the theme is in DexScreener's top narratives
   (`https://api.dexscreener.com/metas/trending/v1`), say so in the thesis; it isn't required.
5. `./order.sh buy` is refused for a coin without a gate pass from the last 2 hours, and opens the control position by
   itself on a different gate pass (never the pick). If your pick is the only pass, it gets no control.
No buy is a fine outcome. Cash is a position.

## Arms and dataset (Tier 1 phase 3)
The hot loop runs ten mechanical arms beside your picks, in `books/v-*.json`, so rule sets
compete on the same coins. You never trade them. Same gate, 0.25 SOL size, costs and exit code as
the picks; each buys at most one coin per 15-minute cycle, keeps cash above 5 SOL, holds at most 6
and waits 24 hours before re-buying a coin it closed. Stop −35% and take-profit +100% unless listed.

"Momentum" means 1h buys > sells, 1h and 24h change above 0, 5m change under +25%.

| Arm | Buys | Takes the highest |
|---|---|---|
| `v-momentum` | momentum | 24h volume |
| `v-no-spike` | momentum, 24h change at most +150% | 24h volume |
| `v-mature` | pair at least 72h old, liquidity at least $150k | liquidity |
| `v-tight` | momentum; stop −20%, take-profit +40% | 24h volume |
| `v-loose` | momentum; stop −40%, take-profit +150% | 24h volume |
| `v-dip` | above its price 7 days ago, 24h change −35% to −15%, 1h buys > sells | 24h volume |
| `v-low-bundle` | momentum, flagged insiders at most 5% | 24h volume |
| `v-velocity` | momentum | average trade size |
| `v-x-organic` | momentum, X posts rising, at least half from small accounts over 30 days old | 24h volume |
| `v-x-exit` | momentum with X data; also sells when 3+ large accounts post and that's more than last run | 24h volume |

`v-dip` can't trade until the dataset is a week old. Arm trades don't alert the phone. The report's "Mechanical arms" table shows each one; no
arm is judged before the review, and none changes a rule by itself.

**Dataset:** `data/YYYY-MM-DD.jsonl` on `state` (finished days gzipped). Each cycle writes a header
line (each arm's cash and holdings, plus prices from a week ago) and one row per coin that has ever
been in the universe, kept for 10 days after it last qualified, so coins that collapse stay in the
data. A row holds what the arms saw: price, liquidity, volume, trades, price changes and the gate
result of that moment. An outage at RugCheck is not a verdict: the coin is retried in an hour and
never becomes a shadow reject.

`python3 -I memepaper.py replay <YYYY-MM-DD>` (state mode) re-runs every arm's choice on a recorded
day and lists any entry that differs from what the arm did. Entries only: exits run every minute
and the rows are 15 minutes apart, so an exit rule can't be replayed exactly from this data.

## X scout
A Grok bot, Scout, reads `grok/watchlist.txt` on `state` every 4 hours, copies facts about recent X
posts into a file on the private desk and never touches this repo. Each cycle the loop reads the
newest file. It checks the shape, checks each post's link number against its stated time, looks up 5
random posts on X (each must exist, match its account and text, and hold the mint or exact cashtag),
and keeps only counts (`scout.json`). A failed check resets trust to zero. The X
arms act only after 3 clean files in a row and on data under 5 hours old; otherwise they do nothing
and no other arm is affected. Follower counts can't be verified this way, so treat them as Scout's
reading. The report's "X scout" section is information for your judgement, never a gate: influencer
posts often mark the top, and X activity can be faked.

## What not to do (from the research)
No copy-trading wallets, no buying because an influencer called it, no fresh launches (bots win
those in milliseconds), no buying on a boost alone.
