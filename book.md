---
title: Memecoin paper book
created: 2026-11-01
updated: 2026-11-19
area: trading
---

*Paper only: simulated fills from live DexScreener prices, 1.50% fee each side plus a size/liquidity
slippage charge. No wallet, nothing reaches the market. Written by `memepaper.py` (repo memecoin-paper); do not hand-edit.*

**Equity 9.492 SOL** (start 10.0 SOL, -5.1%) · cash 8.958 SOL ·
open 1 · closed 20 (6 won) · SOL $74.46 · marked 2026-11-19 09:53 UTC

**Benchmark (vs just holding SOL): -5.1%.** The book is counted in SOL, so its SOL
return *is* its edge over holding SOL. In dollars: $707 vs $949 at the start
(-25.5%); SOL itself moved -21.5%.
Review on 2026-11-30 or after 30 closed v2 trades (13/30), rules unchanged until then.

## v2 test (from 2026-11-03 01:30 UTC)

Does picking beat a random coin that passed the same gates, after costs? Each pick opens a same-size
control position on a random gate pass (`control.json`, same mechanical exits, no judgement exits).

| Arm | Closed | Won | P&L SOL (incl. open) | Return on SOL deployed |
|---|---|---|---|---|
| Picks | 13 | 4 | +0.337 | +9.6% |
| Control | 13 | 0 | -1.064 | -30.4% |

Costs in every fill: 1.5% fee each side, size/liquidity slippage, and a $0.50 sandwich charge per swap.
If every swap were sandwiched at the $5 median: picks -1.295 SOL, control -2.575 SOL.

**Gate value** (raw price moves, no costs; the gate earns its keep if passes beat rejects):
passes 64 tracked, median 1d -67%, 3d -96%, 7d -100% · rejects 79 tracked, median 1d -58%, 3d -80%, 7d -98%.
Legacy v1 positions (opened before v2, 1.25% fee model, sizes to 1 SOL) stay under the same exits and are left out of this table.

## Mechanical arms

Same gate, size, costs and exit code as the picks; rules in `CLAUDE.md`. Judged against the control, and only after enough closed trades.

| Arm | Closed | Won | Open | P&L SOL (incl. open) | Return on SOL deployed |
|---|---|---|---|---|---|
| mech | 11 | 3 | 1 | +0.390 | +13.0% |
| v-dip | 3 | 0 | 2 | -0.256 | -20.5% |
| v-loose | 69 | 16 | 6 | -2.018 | -10.8% |
| v-low-bundle | 74 | 17 | 6 | -3.245 | -16.2% |
| v-mature | 32 | 8 | 1 | -1.004 | -12.2% |
| v-momentum | 74 | 17 | 6 | -3.245 | -16.2% |
| v-networks | 68 | 16 | 6 | -1.875 | -10.1% |
| v-no-spike | 44 | 13 | 5 | +6771.488 | +55277.5% |
| v-swing | 95 | 20 | 5 | -3.175 | -12.7% |
| v-tight | 91 | 25 | 6 | -2.787 | -11.5% |
| v-unease | 80 | 18 | 6 | -2.020 | -9.4% |
| v-unpaid | 49 | 6 | 2 | -4.559 | -35.8% |
| v-velocity | 71 | 18 | 6 | -2.303 | -12.0% |
| v-x-exit | 0 | 0 | 0 | +0.000 | +0.0% |
| v-x-organic | 0 | 0 | 0 | +0.000 | +0.0% |

## X scout

not connected: no DESK_TOKEN. Clean files in a row: 0 of 3 needed for the X arms. Facts copied by Grok and counted by code: information only, never a gate.

## Reading the coins

Each coin against its own normal. Information only: no rule on this book reads it.

| Coin | Normal 15m swing | vs average paid | Off peak | Unease | Stop, in swings |
|---|---|---|---|---|---|
| BRUH | 2.5% | -12% | -21% | 2 of 5 | 14.1 |

## Dataset

Last check 2026-11-18: 90 of 96 snapshots, 14389 rows, 172 coins, 139.9 MB. No problems.

GeckoTerminal: 56692 calls, 474 refused, 17 failed, 104 waiting. Insider flag fired on 0 of 67 coins where RugCheck's graph found insiders.

Fills: a round trip on Jupiter returned -1.5% (median of 180 quotes, before priority fees); paper charged -8.3%.

Launch feed: running, 10410 launches and 810 graduations in the last day.

Learning run 2026-11-15: 11 of 14 arms have 15+ trades. Promoted: none. Proposes only until 2026-11-30. Detail: LEARNING.md on `state`. No rule on this book reads it.

## Open positions

| Coin | Mint | Opened | Cost SOL | Entry mcap | Move | Value SOL (incl. realised) | Thesis |
|---|---|---|---|---|---|---|---|
| BRUH | `PgFtGGqu…` | 2026-11-08 08:15 UTC | 0.25 | $1,080,245 | +271% | 0.771 | Gate pass; 28h pumpswap coin, mc $1.07M, liq $84k (thin), 1h +42%, 24h +84%, 5m -2.2% (no spike now), 1h buys 163 vs sells 92. Other passes COGE (24h -92%) and GIGAHUG (11.7h, +1775% 24h vertical) skipped; GATO/HELL already held. |

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
| NIO | 2026-11-10 20:16 UTC → 2026-11-12 20:16 UTC | 0.25 | -0.043 (-17%) | time stop: 48h held, -12%, no take-profit |
| RAMBO | 2026-11-13 00:15 UTC → 2026-11-14 16:08 UTC | 0.25 | -0.046 (-18%) | event exit: price -20% in 5 minutes, -20% from entry |
| GATO | 2026-11-13 16:37 UTC → 2026-11-15 16:37 UTC | 0.25 | -0.032 (-13%) | time stop: 48h held, -15%, no take-profit |
| BIG | 2026-11-15 12:16 UTC → 2026-11-17 12:16 UTC | 0.25 | +0.012 (+5%) | time stop: 48h held, +15%, no take-profit |
| BLOB | 2026-11-16 08:15 UTC → 2026-11-17 14:46 UTC | 0.25 | -0.090 (-36%) | event exit: price -31% in 5 minutes, -26% from entry |
| Leonida | 2026-11-19 08:16 UTC → 2026-11-19 09:12 UTC | 0.25 | -0.118 (-47%) | event exit: price -28% in 5 minutes, -41% from entry |

## Log

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
- 2026-11-12 20:16 UTC SELL 100% NIO -> 0.207 SOL @ $0.001098: time stop: 48h held, -12%, no take-profit
- 2026-11-13 00:15 UTC BUY RAMBO 0.25 SOL @ $0.012660836 (mc $12,486,694): Gate pass; mature pumpswap coin (225h), mc $12.5M, liq $309k, 1h +12%, 24h +108%, 5m +0.5% (no spike), 1h buys 212 vs sells 61. Other passes DESSA/GATO skipped (24h negative, 1h negative); CBUCKS failed gate (14% wallet).
- 2026-11-13 16:37 UTC BUY GATO 0.25 SOL @ $0.0080315323 (mc $7,926,891): Gate pass; mature pumpswap coin (1924h), mc $7.8M, liq $298k, 1h +30.8%, 24h +37%, 5m +4.2% (no spike), 1h buys 1257 vs sells 915, vol1h $220k. Other universe coins CBUCKS (14% wallet) and WASTED (copycat) failed gate.
- 2026-11-14 16:08 UTC SELL 100% RAMBO -> 0.204 SOL @ $0.01015: event exit: price -20% in 5 minutes, -20% from entry
- 2026-11-15 12:16 UTC BUY BIG 0.25 SOL @ $0.0013002246 (mc $1,234,475): Gate pass; 164h pumpswap coin, mc $1.19M, liq $103k, 1h +0.7%, 24h +4.8% (cooled from earlier +438% spike), 5m -4.8% (no spike), 1h buys 1071 vs sells 1009; volume modest. Only unheld pass; CBUCKS failed gate (14% wallet); GATO/BRUH held.
- 2026-11-15 16:37 UTC SELL 100% GATO -> 0.218 SOL @ $0.006857: time stop: 48h held, -15%, no take-profit
- 2026-11-16 08:15 UTC BUY BLOB 0.25 SOL @ $0.012940775 (mc $12,832,050): Gate pass; 377h pumpswap coin, mc $12.8M, liq $296k, 1h +27.9%, 24h +254% (extended, risk noted), 5m +1.2% (no spike now), 1h buys 1901 vs sells 1506, vol1h $395k. Other pass GATO skipped (sellers lead, flat); CBUCKS (13% wallet), WASTED/Anthropig (copycat) failed gate.
- 2026-11-17 12:16 UTC SELL 100% BIG -> 0.262 SOL @ $0.001496: time stop: 48h held, +15%, no take-profit
- 2026-11-17 14:46 UTC SELL 100% BLOB -> 0.160 SOL @ $0.00954: event exit: price -31% in 5 minutes, -26% from entry
- 2026-11-19 08:16 UTC BUY Leonida 0.25 SOL @ $0.0013972868 (mc $1,391,536): Gate pass; 31h pumpswap coin, mc $1.38M, liq $91k (thin), 1h +0.4%, 24h +76%, 5m -2.5% (no spike), 1h buys 1461 vs sells 628, vol1h $49k. Other passes GATO (24h -53%), GTASZN (8.5h, +1384% vertical), HOGE (sellers lead) skipped; ANTS (copycat), CBUCKS (13% wallet) failed gate.
- 2026-11-19 09:12 UTC SELL 100% Leonida -> 0.132 SOL @ $0.0008238: event exit: price -28% in 5 minutes, -41% from entry

## Orders (last 15)

- 2026-11-17 00:16 UTC `20261117T001605.758942Z-gate-7d4b07`: recorded 7 gate results, 4 passed
- 2026-11-17 04:16 UTC `20261117T041515.475262Z-gate-7d6bba`: recorded 8 gate results, 6 passed
- 2026-11-17 08:16 UTC `20261117T081530.755954Z-gate-50a94b`: recorded 10 gate results, 8 passed
- 2026-11-17 12:15 UTC `20261117T121501.053963Z-gate-f177f0`: recorded 1 gate results, 1 passed
- 2026-11-17 12:16 UTC `20261117T121515.723220Z-gate-28a21d`: recorded 10 gate results, 9 passed
- 2026-11-17 16:15 UTC `20261117T161504.970872Z-gate-031789`: recorded 9 gate results, 7 passed
- 2026-11-17 20:16 UTC `20261117T201535.533397Z-gate-4f0267`: recorded 4 gate results, 3 passed
- 2026-11-18 00:18 UTC `20261118T001726.900929Z-gate-6c739f`: recorded 2 gate results, 1 passed
- 2026-11-18 04:15 UTC `20261118T041507.050349Z-gate-8aa8d9`: recorded 2 gate results, 2 passed
- 2026-11-18 08:16 UTC `20261118T081529.535533Z-gate-f504b8`: recorded 3 gate results, 2 passed
- 2026-11-18 12:16 UTC `20261118T121619.057713Z-gate-44244b`: recorded 5 gate results, 4 passed
- 2026-11-18 16:16 UTC `20261118T161555.293740Z-gate-d8edee`: recorded 8 gate results, 7 passed
- 2026-11-18 20:15 UTC `20261118T201515.897489Z-gate-c608fd`: recorded 5 gate results, 4 passed
- 2026-11-19 08:16 UTC `20261119T081602.722167Z-gate-81f368`: recorded 6 gate results, 4 passed
- 2026-11-19 08:16 UTC `20261119T081608.934900Z-buy-82c08a`: bought Leonida 0.25 SOL @ $0.0013972868; control opened
