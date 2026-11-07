---
title: Memecoin paper book
created: 2026-11-01
updated: 2026-11-07
area: trading
---

*Paper only: simulated fills from live DexScreener prices, 1.50% fee each side plus a size/liquidity
slippage charge. No wallet, nothing reaches the market. Written by `memepaper.py` (repo memecoin-paper); do not hand-edit.*

**Equity 9.314 SOL** (start 10.0 SOL, -6.9%) · cash 8.352 SOL ·
open 4 · closed 10 (4 won) · SOL $90.37 · marked 2026-11-07 03:15 UTC

**Benchmark (vs just holding SOL): -6.9%.** The book is counted in SOL, so its SOL
return *is* its edge over holding SOL. In dollars: $842 vs $949 at the start
(-11.3%); SOL itself moved -4.7%.
Review on 2026-11-30 or after 30 closed v2 trades (3/30), rules unchanged until then.

## v2 test (from 2026-11-03 01:30 UTC)

Does picking beat a random coin that passed the same gates, after costs? Each pick opens a same-size
control position on a random gate pass (`control.json`, same mechanical exits, no judgement exits).

| Arm | Closed | Won | P&L SOL (incl. open) | Return on SOL deployed |
|---|---|---|---|---|
| Picks | 3 | 2 | +0.159 | +9.1% |
| Control | 5 | 0 | -0.381 | -21.8% |

Costs in every fill: 1.5% fee each side, size/liquidity slippage, and a $0.50 sandwich charge per swap.
If every swap were sandwiched at the $5 median: picks -0.289 SOL, control -0.879 SOL.

**Gate value** (raw price moves, no costs; the gate earns its keep if passes beat rejects):
passes 22 tracked, median 1d -11%, 3d -11%, 7d n/a · rejects 24 tracked, median 1d -6%, 3d -9%, 7d n/a.
Legacy v1 positions (opened before v2, 1.25% fee model, sizes to 1 SOL) stay under the same exits and are left out of this table.

## Mechanical arms

Same gate, size, costs and exit code as the picks; rules in `CLAUDE.md`. Judged against the control, and only after enough closed trades.

| Arm | Closed | Won | Open | P&L SOL (incl. open) | Return on SOL deployed |
|---|---|---|---|---|---|
| mech | 1 | 1 | 4 | +0.245 | +19.6% |
| v-dip | 0 | 0 | 0 | +0.000 | +0.0% |
| v-loose | 8 | 3 | 6 | +0.301 | +8.6% |
| v-low-bundle | 8 | 3 | 6 | +0.351 | +10.0% |
| v-mature | 1 | 1 | 4 | +0.176 | +14.1% |
| v-momentum | 8 | 3 | 6 | +0.351 | +10.0% |
| v-networks | 7 | 2 | 6 | +0.338 | +10.4% |
| v-no-spike | 3 | 2 | 5 | +0.032 | +1.6% |
| v-swing | 6 | 2 | 6 | +0.408 | +13.6% |
| v-tight | 11 | 3 | 6 | +0.230 | +5.4% |
| v-unease | 8 | 2 | 6 | +0.368 | +10.5% |
| v-unpaid | 4 | 0 | 6 | -0.472 | -18.9% |
| v-velocity | 8 | 3 | 6 | +0.350 | +10.0% |
| v-x-exit | 0 | 0 | 0 | +0.000 | +0.0% |
| v-x-organic | 0 | 0 | 0 | +0.000 | +0.0% |

## X scout

not connected: no DESK_TOKEN. Clean files in a row: 0 of 3 needed for the X arms. Facts copied by Grok and counted by code: information only, never a gate.

## Reading the coins

Each coin against its own normal. Information only: no rule on this book reads it.

| Coin | Normal 15m swing | vs average paid | Off peak | Unease | Stop, in swings |
|---|---|---|---|---|---|
| JOB | 4.3% | +4% | -11% | 1 of 5 | 8.0 |
| three | 2.1% | -13% | -27% | 3 of 5 | 16.8 |
| HELL | 7.9% | -3% | -9% | 2 of 5 | 4.4 |
| GATO | 3.2% | -4% | -12% | 2 of 5 | 11.0 |

## Dataset

Last check 2026-11-06: 90 of 96 snapshots, 7851 rows, 113 coins, 14.3 MB. No problems.

GeckoTerminal: 6820 calls, 49 refused, 1 failed, 86 waiting. Insider flag fired on 0 of 63 coins where RugCheck's graph found insiders.

Fills: a round trip on Jupiter returned -1.0% (median of 180 quotes, before priority fees); paper charged -7.4%.

Launch feed: running, 13756 launches and 667 graduations in the last day.

## Open positions

| Coin | Mint | Opened | Cost SOL | Entry mcap | Move | Value SOL (incl. realised) | Thesis |
|---|---|---|---|---|---|---|---|
| JOB | `9Pq7aLAb…` | 2026-11-05 02:48 UTC | 0.25 | $3,994,528 | +20% | 0.310 | Gate pass; mature pumpswap coin (200h), mc $4.0M, liq $198k, 1h +1.3%, 24h +70%, 5m +1.2% (no spike), 1h buys 175 vs sells 143. Other passes GTA (6h, vertical +5633% 24h, -29% 1h) skipped. |
| three | `FeMbDoX7…` | 2026-11-06 04:15 UTC | 0.25 | $633,365 | -13% | 0.207 | Gate pass; mature pumpswap coin (4581h), mc $641k, liq $162k, 1h +2.8%, 24h +13.2%, 5m flat, 1h buys 1236 vs sells 489; no spike. Other passes GATO (sellers lead, 1h -3%) and COGE (8h, vertical +5173%) skipped. |
| HELL | `A75Xx6Se…` | 2026-11-06 12:16 UTC | 0.25 | $2,831,474 | -8% | 0.222 | Gate pass; mature pumpswap coin (575h), mc $2.9M, liq $138k, 1h +1.8%, 24h +10.6%, 5m +12.9% (<25%), 1h buys 2817 vs 2752. Other passes GATO (sellers lead), COGE (16h, +8457% 24h) and AMD (10h, +4852% 24h) skipped. |
| GATO | `HsprHxBR…` | 2026-11-06 20:15 UTC | 0.25 | $11,775,041 | -7% | 0.223 | Gate pass; mature pumpswap coin (1760h), mc $11.8M, liq $363k, 1h +5.3%, 24h +23.8%, 5m +0.5% (no spike), 1h buys 443 vs sells 421. Other passes DESSA/NIO/COGE/AMD skipped (sellers lead or vertical 24h); HELL/three already held. |

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

## Orders (last 15)

- 2026-11-05 12:19 UTC `20261105T121824.193911Z-gate-8552e6`: recorded 6 gate results, 5 passed
- 2026-11-05 16:16 UTC `20261105T161540.633516Z-gate-af116b`: recorded 1 gate results, 1 passed
- 2026-11-05 16:16 UTC `20261105T161553.205595Z-gate-594b62`: recorded 8 gate results, 6 passed
- 2026-11-05 20:15 UTC `20261105T201420.369152Z-gate-551436`: recorded 7 gate results, 4 passed
- 2026-11-06 04:14 UTC `20261106T041439.183396Z-gate-1bdfa8`: recorded 1 gate results, 1 passed
- 2026-11-06 04:15 UTC `20261106T041448.700682Z-gate-7832dd`: recorded 5 gate results, 3 passed
- 2026-11-06 04:15 UTC `20261106T041454.569090Z-buy-14524d`: bought three 0.25 SOL @ $0.00063368775; control opened
- 2026-11-06 08:15 UTC `20261106T081534.176212Z-gate-a95c33`: recorded 5 gate results, 3 passed
- 2026-11-06 08:15 UTC `20261106T081541.719602Z-gate-ba1e65`: recorded 2 gate results, 2 passed
- 2026-11-06 12:16 UTC `20261106T121636.720342Z-gate-1ad862`: recorded 8 gate results, 6 passed
- 2026-11-06 12:16 UTC `20261106T121643.686220Z-buy-4a2cd7`: bought HELL 0.25 SOL @ $0.0029684887; control opened
- 2026-11-06 16:19 UTC `20261106T161817.606762Z-gate-0e28fb`: recorded 7 gate results, 7 passed
- 2026-11-06 20:15 UTC `20261106T201502.781553Z-gate-b2e37a`: recorded 7 gate results, 7 passed
- 2026-11-06 20:15 UTC `20261106T201510.655639Z-buy-3f5d46`: bought GATO 0.25 SOL @ $0.011930744; control opened
- 2026-11-07 00:16 UTC `20261107T001515.913613Z-gate-96f007`: recorded 7 gate results, 7 passed
