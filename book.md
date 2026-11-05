---
title: Memecoin paper book
created: 2026-11-01
updated: 2026-11-05
area: trading
---

*Paper only: simulated fills from live DexScreener prices, 1.50% fee each side plus a size/liquidity
slippage charge. No wallet, nothing reaches the market. Written by `memepaper.py` (repo memecoin-paper); do not hand-edit.*

**Equity 9.456 SOL** (start 10.0 SOL, -5.4%) · cash 8.807 SOL ·
open 2 · closed 9 (3 won) · SOL $89.48 · marked 2026-11-05 21:26 UTC

**Benchmark (vs just holding SOL): -5.4%.** The book is counted in SOL, so its SOL
return *is* its edge over holding SOL. In dollars: $846 vs $949 at the start
(-10.8%); SOL itself moved -5.7%.
Review on 2026-11-30 or after 30 closed v2 trades (2/30), rules unchanged until then.

## v2 test (from 2026-11-03 01:30 UTC)

Does picking beat a random coin that passed the same gates, after costs? Each pick opens a same-size
control position on a random gate pass (`control.json`, same mechanical exits, no judgement exits).

| Arm | Closed | Won | P&L SOL (incl. open) | Return on SOL deployed |
|---|---|---|---|---|
| Picks | 2 | 1 | +0.301 | +30.1% |
| Control | 3 | 0 | -0.269 | -26.9% |

Costs in every fill: 1.5% fee each side, size/liquidity slippage, and a $0.50 sandwich charge per swap.
If every swap were sandwiched at the $5 median: picks +0.050 SOL, control -0.521 SOL.

**Gate value** (raw price moves, no costs; the gate earns its keep if passes beat rejects):
passes 14 tracked, median 1d -8%, 3d n/a, 7d n/a · rejects 13 tracked, median 1d -17%, 3d n/a, 7d n/a.
Legacy v1 positions (opened before v2, 1.25% fee model, sizes to 1 SOL) stay under the same exits and are left out of this table.

## Mechanical arms

Same gate, size, costs and exit code as the picks; rules in `CLAUDE.md`. Judged against the control, and only after enough closed trades.

| Arm | Closed | Won | Open | P&L SOL (incl. open) | Return on SOL deployed |
|---|---|---|---|---|---|
| v-dip | 0 | 0 | 0 | +0.000 | +0.0% |
| v-loose | 5 | 1 | 4 | -0.287 | -12.7% |
| v-low-bundle | 5 | 1 | 4 | -0.206 | -9.2% |
| v-mature | 0 | 0 | 4 | +0.233 | +23.3% |
| v-momentum | 5 | 1 | 4 | -0.206 | -9.2% |
| v-networks | 4 | 0 | 4 | -0.219 | -10.9% |
| v-no-spike | 0 | 0 | 3 | +0.253 | +33.7% |
| v-swing | 4 | 1 | 4 | -0.114 | -5.7% |
| v-tight | 8 | 0 | 1 | -0.387 | -17.2% |
| v-unease | 5 | 1 | 3 | -0.209 | -10.5% |
| v-unpaid | 2 | 0 | 4 | -0.160 | -10.6% |
| v-velocity | 5 | 1 | 4 | -0.206 | -9.2% |
| v-x-exit | 0 | 0 | 0 | +0.000 | +0.0% |
| v-x-organic | 0 | 0 | 0 | +0.000 | +0.0% |

## X scout

not connected: no DESK_TOKEN. Clean files in a row: 0 of 3 needed for the X arms. Facts copied by Grok and counted by code: information only, never a gate.

## Reading the coins

Each coin against its own normal. Information only: no rule on this book reads it.

| Coin | Normal 15m swing | vs average paid | Off peak | Unease | Stop, in swings |
|---|---|---|---|---|---|
| DESSA | 2.5% | -5% | -30% | 3 of 5 | 13.8 |
| JOB | 5.0% | +13% | -4% | 0 of 5 | 7.0 |

## Dataset

Last check 2026-11-04: 0 of 96 snapshots, 0 rows, 0 coins, 0.0 MB. No problems.

GeckoTerminal: 1967 calls, 0 refused, 1 failed, 0 waiting. Insider flag fired on 0 of 2 coins where RugCheck's graph found insiders.

Launch feed: running, 9138 launches and 559 graduations in the last day.

## Open positions

| Coin | Mint | Opened | Cost SOL | Entry mcap | Move | Value SOL (incl. realised) | Thesis |
|---|---|---|---|---|---|---|---|
| DESSA | `npz2Fhou…` | 2026-11-04 16:16 UTC | 0.25 | $13,536,760 | +158% | 0.575 | Passed gate; mature pumpswap coin (219h), mc $13.6M, liq $353k, 1h +17.7%, 24h +59%, 5m flat (+0.2%), 1h buys 736 vs sells 758 roughly even; distinct theme |
| JOB | `9Pq7aLAb…` | 2026-11-05 02:48 UTC | 0.25 | $3,994,528 | +20% | 0.312 | Gate pass; mature pumpswap coin (200h), mc $4.0M, liq $198k, 1h +1.3%, 24h +70%, 5m +1.2% (no spike), 1h buys 175 vs sells 143. Other passes GTA (6h, vertical +5633% 24h, -29% 1h) skipped. |

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

## Orders (last 15)

- 2026-11-05 02:48 UTC `20261105T024730.157445Z-gate-fb4573`: recorded 4 gate results, 4 passed
- 2026-11-05 02:48 UTC `20261105T024736.523366Z-buy-8a0336`: bought JOB 0.25 SOL @ $0.0041005003; control opened
- 2026-11-05 04:15 UTC `20261105T041407.076115Z-gate-1df198`: recorded 1 gate results, 1 passed
- 2026-11-05 04:15 UTC `20261105T041413.703356Z-gate-145120`: recorded 5 gate results, 5 passed
- 2026-11-05 08:15 UTC `20261105T081435.122270Z-gate-00ecc3`: recorded 0 gate results, 0 passed
- 2026-11-05 08:15 UTC `20261105T081450.094035Z-gate-b1d335`: recorded 5 gate results, 5 passed
- 2026-11-05 12:19 UTC `20261105T121824.193911Z-gate-8552e6`: recorded 6 gate results, 5 passed
- 2026-11-05 16:16 UTC `20261105T161540.633516Z-gate-af116b`: recorded 1 gate results, 1 passed
- 2026-11-05 16:16 UTC `20261105T161553.205595Z-gate-594b62`: recorded 8 gate results, 6 passed
- 2026-11-05 20:15 UTC `20261105T201420.369152Z-gate-551436`: recorded 7 gate results, 4 passed
