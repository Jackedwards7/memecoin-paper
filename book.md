---
title: Memecoin paper book
created: 2026-11-01
updated: 2026-11-11
area: trading
---

*Paper only: simulated fills from live DexScreener prices, 1.50% fee each side plus a size/liquidity
slippage charge. No wallet, nothing reaches the market. Written by `memepaper.py` (repo memecoin-paper); do not hand-edit.*

**Equity 9.486 SOL** (start 10.0 SOL, -5.1%) · cash 9.025 SOL ·
open 2 · closed 14 (5 won) · SOL $85.20 · marked 2026-11-11 18:44 UTC

**Benchmark (vs just holding SOL): -5.1%.** The book is counted in SOL, so its SOL
return *is* its edge over holding SOL. In dollars: $808 vs $949 at the start
(-14.8%); SOL itself moved -10.2%.
Review on 2026-11-30 or after 30 closed v2 trades (7/30), rules unchanged until then.

## v2 test (from 2026-11-03 01:30 UTC)

Does picking beat a random coin that passed the same gates, after costs? Each pick opens a same-size
control position on a random gate pass (`control.json`, same mechanical exits, no judgement exits).

| Arm | Closed | Won | P&L SOL (incl. open) | Return on SOL deployed |
|---|---|---|---|---|
| Picks | 7 | 3 | +0.331 | +14.7% |
| Control | 8 | 0 | -0.672 | -29.8% |

Costs in every fill: 1.5% fee each side, size/liquidity slippage, and a $0.50 sandwich charge per swap.
If every swap were sandwiched at the $5 median: picks -0.514 SOL, control -1.464 SOL.

**Gate value** (raw price moves, no costs; the gate earns its keep if passes beat rejects):
passes 38 tracked, median 1d -53%, 3d -92%, 7d -78% · rejects 54 tracked, median 1d -37%, 3d -59%, 7d -57%.
Legacy v1 positions (opened before v2, 1.25% fee model, sizes to 1 SOL) stay under the same exits and are left out of this table.

## Mechanical arms

Same gate, size, costs and exit code as the picks; rules in `CLAUDE.md`. Judged against the control, and only after enough closed trades.

| Arm | Closed | Won | Open | P&L SOL (incl. open) | Return on SOL deployed |
|---|---|---|---|---|---|
| mech | 5 | 2 | 2 | +0.384 | +21.9% |
| v-dip | 0 | 0 | 0 | +0.000 | +0.0% |
| v-loose | 32 | 8 | 6 | -1.426 | -15.0% |
| v-low-bundle | 37 | 9 | 5 | -1.983 | -18.9% |
| v-mature | 11 | 4 | 2 | -0.249 | -7.7% |
| v-momentum | 37 | 9 | 5 | -1.983 | -18.9% |
| v-networks | 31 | 7 | 4 | -1.143 | -13.1% |
| v-no-spike | 18 | 5 | 6 | +6771.319 | +112855.3% |
| v-swing | 40 | 9 | 4 | -1.533 | -13.9% |
| v-tight | 42 | 9 | 4 | -1.522 | -13.2% |
| v-unease | 35 | 9 | 4 | -0.557 | -5.7% |
| v-unpaid | 30 | 3 | 6 | -3.773 | -41.9% |
| v-velocity | 35 | 9 | 6 | -1.437 | -14.0% |
| v-x-exit | 0 | 0 | 0 | +0.000 | +0.0% |
| v-x-organic | 0 | 0 | 0 | +0.000 | +0.0% |

## X scout

not connected: no DESK_TOKEN. Clean files in a row: 0 of 3 needed for the X arms. Facts copied by Grok and counted by code: information only, never a gate.

## Reading the coins

Each coin against its own normal. Information only: no rule on this book reads it.

| Coin | Normal 15m swing | vs average paid | Off peak | Unease | Stop, in swings |
|---|---|---|---|---|---|
| BRUH | 4.0% | +6% | -12% | 0 of 5 | 8.8 |
| NIO | 4.4% | -11% | -34% | 2 of 5 | 8.0 |

## Dataset

Last check 2026-11-10: 90 of 96 snapshots, 14463 rows, 186 coins, 55.7 MB. No problems.

GeckoTerminal: 25765 calls, 200 refused, 15 failed, 112 waiting. Insider flag fired on 0 of 82 coins where RugCheck's graph found insiders.

Fills: a round trip on Jupiter returned -0.6% (median of 180 quotes, before priority fees); paper charged -7.7%.

Launch feed: running, 10712 launches and 675 graduations in the last day.

Learning run 2026-11-08: 2 of 14 arms have 15+ trades. Promoted: none. Proposes only until 2026-11-30. Detail: LEARNING.md on `state`. No rule on this book reads it.

## Open positions

| Coin | Mint | Opened | Cost SOL | Entry mcap | Move | Value SOL (incl. realised) | Thesis |
|---|---|---|---|---|---|---|---|
| BRUH | `PgFtGGqu…` | 2026-11-08 08:15 UTC | 0.25 | $1,080,245 | +136% | 0.534 | Gate pass; 28h pumpswap coin, mc $1.07M, liq $84k (thin), 1h +42%, 24h +84%, 5m -2.2% (no spike now), 1h buys 163 vs sells 92. Other passes COGE (24h -92%) and GIGAHUG (11.7h, +1775% 24h vertical) skipped; GATO/HELL already held. |
| NIO | `7SL2VnfY…` | 2026-11-10 20:16 UTC | 0.25 | $1,186,743 | -30% | 0.165 | Gate pass; mature pumpswap coin (484h), mc $1.2M, liq $122k, 1h +4.7%, 24h +37%, 5m +4.1% (no spike), 1h buys 64 vs sells 67 roughly even. Other passes GATO (sellers lead, 24h -14%) and BIG (24h +438% vertical) skipped; CBUCKS failed gate. |

## Closed

| Coin | Held | Cost SOL | P&L SOL | Exit |
|---|---|---|---|---|
| ANAKIN | 2026-11-02 05:44 UTC → 2026-11-02 15:45 UTC | 0.50 | -0.176 (-35%) | stop-loss at -34% |
| Anakin | 2026-11-02 05:44 UTC → 2026-11-02 17:23 UTC | 1.00 | -0.473 (-47%) | stop-loss at -47% |
| WASTED | 2026-11-03 00:14 UTC → 2026-11-03 00:28 UTC | 0.50 | -0.194 (-39%) | stop-loss at -37% |
| CHOO | 2026-11-02 05:44 UTC → 2026-11-03 04:22 UTC | 0.75 | -0.232 (-31%) | stop-loss at -31% |
| Ahsoka | 2026-11-03 16:15 UTC → 2026-11-03 19:30 UTC | 0.25 | -0.092 (-37%) | stop-loss at -35% |
| CBUCKS | 2026-11-02 08:30 UTC → 2026-11-04 08:31 UTC | 0.50 | -0.023 (-5%) | time stop: 48h held, -2%, no take-profit |
| three | 2026-11-02 17:24 UTC → 2026-11-04 20:13 UTC | 0.50 | +0.061 (+12%) | time stop: 51h held, +19%, no take-profit |
| GATO | 2026-11-02 05:44 UTC → 2026-11-05 12:55 UTC | 0.75 | +0.190 (+25%) | trailing stop: 40% off peak, -8% from entry |
| HELL | 2026-11-03 20:15 UTC → 2026-11-05 20:15 UTC | 0.25 | +0.007 (+3%) | time stop: 48h held, +6%, no take-profit |
| DESSA | 2026-11-04 16:16 UTC → 2026-11-06 04:32 UTC | 0.25 | +0.283 (+113%) | event exit: price -82% in 5 minutes, +133% from entry |
| JOB | 2026-11-05 02:48 UTC → 2026-11-07 03:30 UTC | 0.25 | +0.048 (+19%) | time stop: 49h held, +20%, no take-profit |
| three | 2026-11-06 04:15 UTC → 2026-11-07 04:15 UTC | 0.25 | -0.059 (-24%) | Volume collapsed: 53 trades in 1h vs ~1700 at entry (under 20% of recent level), 1h -4%, 24h -18%, theme fading; position -17% |
| HELL | 2026-11-06 12:16 UTC → 2026-11-08 12:16 UTC | 0.25 | -0.039 (-15%) | time stop: 48h held, -9%, no take-profit |
| GATO | 2026-11-06 20:15 UTC → 2026-11-08 20:15 UTC | 0.25 | -0.015 (-6%) | time stop: 48h held, +0%, no take-profit |

## Log

- 2026-11-02 05:44 UTC BUY Anakin 1.00 SOL @ $0.0030567179 (mc $2,905,987): Anakin narrative leader that has survived 3 days; +15% 1h, buys > sells, no wallet above ~3% of supply
- 2026-11-02 05:44 UTC BUY CHOO 0.75 SOL @ $0.0020130432 (mc $1,989,964): 11-day runner, +123% 24h with buys > sells, holders spread, 72% LP locked
- 2026-11-02 05:44 UTC BUY GATO 0.75 SOL @ $0.0087410867 (mc $8,625,571): Mature 68-day coin, $8.7M cap, deepest pool on the board, 96% LP locked; +38% 24h
- 2026-11-02 05:44 UTC BUY ANAKIN 0.50 SOL @ $0.0030809492 (mc $3,066,672): Momentum: 7h old, +5,969% 24h, 2:1 buys/sells, $138k/h volume; small size because it is vertical and has an 11-wallet bundle (~0.9% supply)
- 2026-11-02 08:30 UTC BUY CBUCKS 0.50 SOL @ $0.0019096153 (mc $1,799,967): CBUCKS: 26-day coin, $1.8M cap, liq $146k, 1h buys 28>20, 1h +2% and 24h +48%, RugCheck no risks, LP 99.99% locked; distinct theme; modest volume noted
- 2026-11-02 15:45 UTC SELL 100% ANAKIN -> 0.324 SOL @ $0.00203: stop-loss at -34%
- 2026-11-02 17:23 UTC SELL 100% Anakin -> 0.527 SOL @ $0.001619: stop-loss at -47%
- 2026-11-02 17:24 UTC BUY three 0.50 SOL @ $0.00046225308 (mc $461,979): three: 187-day coin, liq $140k, 1h buys 450>179, 1h +3% and 24h +2%, 5m flat, RugCheck no risks, LP 96% locked; distinct theme
- 2026-11-02 23:46 UTC SELL 50% GATO -> 0.610 SOL @ $0.01413: take-profit at +62%: half sold, cost recovered
- 2026-11-03 00:14 UTC BUY WASTED 0.50 SOL @ $0.0013745757 (mc $1,348,715): WASTED: 78h coin, liq 110k, 1h buys 911>683, 1h +6.8% and 24h +215%, 5m +10.9% (<25%), RugCheck no risks, LP 98.8% locked; distinct theme
- 2026-11-03 00:28 UTC SELL 100% WASTED -> 0.306 SOL @ $0.0008665: stop-loss at -37%
- 2026-11-03 04:22 UTC SELL 100% CHOO -> 0.518 SOL @ $0.001389: stop-loss at -31%
- 2026-11-03 16:15 UTC BUY Ahsoka 0.25 SOL @ $0.001045279 (mc $1,032,979): Ahsoka: 26h coin, $1.0M cap, liq $87k, gate pass; 1h +10.8%, 24h +35%, 5m +6.4% (not a spike); 1h buys 532 vs sells 641 (slightly negative); only gate pass with positive 1h/24h; thin liquidity noted
- 2026-11-03 19:30 UTC SELL 100% Ahsoka -> 0.158 SOL @ $0.0006786: stop-loss at -35%
- 2026-11-03 20:15 UTC BUY HELL 0.25 SOL @ $0.0027084573 (mc $2,583,618): Passed gate; mature pumpswap coin (511h), liq $141k, 1h +0.8%, 24h +6%, 5m +2.1%, buys~sells; not a spike. Only other passes: ANONVOYAGE (vertical +3681% 24h, rejected) and held GATO.
- 2026-11-04 08:31 UTC SELL 100% CBUCKS -> 0.477 SOL @ $0.001874: time stop: 48h held, -2%, no take-profit
- 2026-11-04 16:16 UTC BUY DESSA 0.25 SOL @ $0.013820952 (mc $13,536,760): Passed gate; mature pumpswap coin (219h), mc $13.6M, liq $353k, 1h +17.7%, 24h +59%, 5m flat (+0.2%), 1h buys 736 vs sells 758 roughly even; distinct theme
- 2026-11-04 20:13 UTC SELL 100% three -> 0.561 SOL @ $0.0005498: time stop: 51h held, +19%, no take-profit
- 2026-11-05 02:48 UTC BUY JOB 0.25 SOL @ $0.0041005003 (mc $3,994,528): Gate pass; mature pumpswap coin (200h), mc $4.0M, liq $198k, 1h +1.3%, 24h +70%, 5m +1.2% (no spike), 1h buys 175 vs sells 143. Other passes GTA (6h, vertical +5633% 24h, -29% 1h) skipped.
- 2026-11-05 12:55 UTC SELL 100% GATO -> 0.330 SOL @ $0.008052: trailing stop: 40% off peak, -8% from entry
- 2026-11-05 13:47 UTC SELL 50% DESSA -> 0.238 SOL @ $0.02787: take-profit at +102%: half sold, cost recovered
- 2026-11-05 20:15 UTC SELL 100% HELL -> 0.257 SOL @ $0.002884: time stop: 48h held, +6%, no take-profit
- 2026-11-06 04:15 UTC BUY three 0.25 SOL @ $0.00063368775 (mc $633,365): Gate pass; mature pumpswap coin (4581h), mc $641k, liq $162k, 1h +2.8%, 24h +13.2%, 5m flat, 1h buys 1236 vs sells 489; no spike. Other passes GATO (sellers lead, 1h -3%) and COGE (8h, vertical +5173%) skipped.
- 2026-11-06 04:32 UTC SELL 100% DESSA -> 0.295 SOL @ $0.0322: event exit: price -82% in 5 minutes, +133% from entry
- 2026-11-06 12:16 UTC BUY HELL 0.25 SOL @ $0.0029684887 (mc $2,831,474): Gate pass; mature pumpswap coin (575h), mc $2.9M, liq $138k, 1h +1.8%, 24h +10.6%, 5m +12.9% (<25%), 1h buys 2817 vs 2752. Other passes GATO (sellers lead), COGE (16h, +8457% 24h) and AMD (10h, +4852% 24h) skipped.
- 2026-11-06 20:15 UTC BUY GATO 0.25 SOL @ $0.011930744 (mc $11,775,041): Gate pass; mature pumpswap coin (1760h), mc $11.8M, liq $363k, 1h +5.3%, 24h +23.8%, 5m +0.5% (no spike), 1h buys 443 vs sells 421. Other passes DESSA/NIO/COGE/AMD skipped (sellers lead or vertical 24h); HELL/three already held.
- 2026-11-07 03:30 UTC SELL 100% JOB -> 0.298 SOL @ $0.004911: time stop: 49h held, +20%, no take-profit
- 2026-11-07 04:15 UTC SELL 100% three -> 0.191 SOL @ $0.0005274: Volume collapsed: 53 trades in 1h vs ~1700 at entry (under 20% of recent level), 1h -4%, 24h -18%, theme fading; position -17%
- 2026-11-08 08:15 UTC BUY BRUH 0.25 SOL @ $0.001091289 (mc $1,080,245): Gate pass; 28h pumpswap coin, mc $1.07M, liq $84k (thin), 1h +42%, 24h +84%, 5m -2.2% (no spike now), 1h buys 163 vs sells 92. Other passes COGE (24h -92%) and GIGAHUG (11.7h, +1775% 24h vertical) skipped; GATO/HELL already held.
- 2026-11-08 12:16 UTC SELL 100% HELL -> 0.211 SOL @ $0.002694: time stop: 48h held, -9%, no take-profit
- 2026-11-08 20:15 UTC SELL 100% GATO -> 0.235 SOL @ $0.01197: time stop: 48h held, +0%, no take-profit
- 2026-11-09 16:03 UTC SELL 50% BRUH -> 0.237 SOL @ $0.002204: take-profit at +102%: half sold, cost recovered
- 2026-11-10 20:16 UTC BUY NIO 0.25 SOL @ $0.0012452127 (mc $1,186,743): Gate pass; mature pumpswap coin (484h), mc $1.2M, liq $122k, 1h +4.7%, 24h +37%, 5m +4.1% (no spike), 1h buys 64 vs sells 67 roughly even. Other passes GATO (sellers lead, 24h -14%) and BIG (24h +438% vertical) skipped; CBUCKS failed gate.

## Orders (last 15)

- 2026-11-09 16:20 UTC `20261109T161931.497953Z-gate-a9b336`: recorded 7 gate results, 2 passed
- 2026-11-09 20:16 UTC `20261109T201517.260043Z-gate-46521b`: recorded 6 gate results, 2 passed
- 2026-11-10 00:15 UTC `20261110T001502.310665Z-gate-501750`: recorded 7 gate results, 2 passed
- 2026-11-10 04:16 UTC `20261110T041506.727699Z-gate-6bfbeb`: recorded 6 gate results, 3 passed
- 2026-11-10 08:17 UTC `20261110T081705.330802Z-gate-bd2077`: recorded 6 gate results, 4 passed
- 2026-11-10 12:19 UTC `20261110T121903.505537Z-gate-8c3f84`: recorded 4 gate results, 3 passed
- 2026-11-10 12:20 UTC `20261110T121924.146211Z-gate-0b3658`: recorded 4 gate results, 3 passed
- 2026-11-10 16:18 UTC `20261110T161743.473183Z-gate-cc4b89`: recorded 4 gate results, 3 passed
- 2026-11-10 20:16 UTC `20261110T201511.155663Z-gate-0fdb72`: recorded 4 gate results, 3 passed
- 2026-11-10 20:16 UTC `20261110T201517.036395Z-buy-89f992`: bought NIO 0.25 SOL @ $0.0012452127; control opened
- 2026-11-11 00:15 UTC `20261111T001444.559378Z-gate-a4b51d`: recorded 6 gate results, 3 passed
- 2026-11-11 04:15 UTC `20261111T041456.839171Z-gate-b9da11`: recorded 5 gate results, 2 passed
- 2026-11-11 08:16 UTC `20261111T081532.741490Z-gate-132085`: recorded 6 gate results, 3 passed
- 2026-11-11 12:20 UTC `20261111T122002.697073Z-gate-f4dbce`: recorded 6 gate results, 3 passed
- 2026-11-11 16:17 UTC `20261111T161645.692726Z-gate-4d880f`: recorded 5 gate results, 2 passed
