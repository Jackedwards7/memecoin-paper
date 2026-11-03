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
Shadow rejects (coins the gates failed, scored at 1, 3 and 7 days) show whether the gates help.
**No rule changes before the review.** Filters stop working within weeks, so the review re-checks
every rule against the data.

## Files
- `memepaper.py`: `screen <mint...>`, `gate <mint...>`,
  `buy <mint> <sol> "<thesis>" [--stop -0.35] [--tp1 1.0]`, `sell <mint> <fraction> "<reason>"`,
  `mark` (reprice both books, apply exit rules, score rejects, rewrite `book.md`).
  Always run with `python3 -I`.
- `book.json` (picks), `control.json` (control arm) and `book.md` (report): written by the script
  only. Never hand-edit.
- `PLAYBOOK.md`: the research behind these rules. Read it before judging a coin.
- `sync.sh`: the Mac's 2-minute watcher (pull, mark, push). Not for the cloud run.

## Costs (in the script)
1.5% fee each side (PumpSwap pool fee plus terminal and priority fees) and a slippage charge
based on size against liquidity. Never trade a coin still on the bonding curve.

## Exit rules (applied by `mark`, no judgement needed)
Hard stop −25% to −35% per position; sell half at the take-profit (+60% to +100%); then a 40%
trailing stop from the peak; time stop after 48h without the take-profit if under +20%; a coin with
no price on 3 checks in a row is marked to zero.

## Judgement exits (the review run, picks only)
Sell (`sell <mint> 1 "<reason>"`) if: sellers lead buys for 2+ hours while the price slides;
hourly volume under ~20% of its recent level; liquidity pulled or falling fast; the coin's theme is
clearly rotating away (see `/metas/trending/v1` below). Write the reason plainly.

## Entries
At most ONE new entry per run, and only if cash > 5 SOL and fewer than 6 open v2 positions.
Size **0.25 SOL** (the script caps it). Steps:
1. **Candidates:** Solana mints ending in `pump` from DexScreener
   `https://api.dexscreener.com/token-profiles/latest/v1` and `/token-boosts/top/v1`.
   Boosts are paid ads: a candidate list only, never a reason to buy.
2. **Universe:** keep those with pair age ≥ 6h (cloud) / ≥ 2h (local) and liquidity ≥ $75k
   (`screen` shows both).
3. **Gate every coin in the universe**, not just your favourite, in one call:
   `gate <mint> <mint> ...`. The script checks mint and freeze authority revoked, no risky
   Token-2022 extension, deepest pool is the graduation pool with LP ≥ 90% locked, no wallet over
   5%, insiders ≤ 15%, creator ≤ 10%, no RugCheck danger (including a creator history of rugs), and
   that it is the original, not a copycat of an earlier coin with the same name. Anything it can't
   check fails. The control arm draws at random from all passes, so gating only your pick breaks
   the test.
4. **Pick** from the passes only. Prefer coins that also show 1h buys > sells, 1h and 24h price change
   positive, and a 5m move under +25% (no buying a vertical spike). Same theme counts at most twice
   across open positions. If the theme is in DexScreener's top narratives
   (`https://api.dexscreener.com/metas/trending/v1`), say so in the thesis; it isn't required.
5. `buy` refuses a coin without a gate pass from the last 2 hours, and opens the control position by
   itself on a different gate pass (never the pick). If your pick is the only pass, it gets no control.
No buy is a fine outcome. Cash is a position.

## What not to do (from the research)
No copy-trading wallets, no buying because an influencer called it, no fresh launches (bots win
those in milliseconds), no buying on a boost alone.
