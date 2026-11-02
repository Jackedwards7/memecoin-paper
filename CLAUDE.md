# Memecoin paper book

A **paper** (fake-money) memecoin book that Claude trades on its own judgement for Jackson
(he asked for it 2026-11-01). Start 10 SOL. No wallet, no keys, no real orders, ever: every fill
is simulated by `memepaper.py` from live public prices. Never add a private key or wallet here.

## Success test (agreed with Jackson 2026-11-02)
Review on 2026-11-30 or after 30 closed trades, whichever is first. Success = beating plain SOL
holding, i.e. a positive SOL-denominated return after fees. **No rule changes before the review.**

## Files
- `memepaper.py`: `screen <mint...>`, `buy <mint> <sol> "<thesis>" [--stop -0.35] [--tp1 1.0]`,
  `sell <mint> <fraction> "<reason>"`, `mark` (reprice + apply exit rules + rewrite `book.md`).
  Always run with `python3 -I`.
- `book.json` (state) and `book.md` (report): written by the script only. Never hand-edit.
- `sync.sh`: the Mac's 2-minute watcher (pull, mark, push). Not for the cloud run.

## Exit rules (applied by `mark`, no judgement needed)
Hard stop −25% to −35% per position; sell half at the take-profit (+60% to +100%); then a 40%
trailing stop from the peak; time stop after 48h without the take-profit if under +20%; a coin with
no price on 3 checks in a row is marked to zero.

## Judgement exits (the review run)
Sell (`sell <mint> 1 "<reason>"`) if: sellers lead buys for 2+ hours while the price slides;
hourly volume under ~20% of its recent level; liquidity pulled or falling fast; the coin's theme is
clearly rotating away. Write the reason plainly.

## Entry rules (strict: the cloud run has no holder data)
At most ONE new entry per run, and only if cash > 5 SOL and fewer than 6 open. Max 1 SOL; in the
cloud run use 0.5 SOL. Candidates from DexScreener (`https://api.dexscreener.com/token-boosts/top/v1`,
`/token-profiles/latest/v1`, Solana mints ending in `pump`), checked with `screen`. All must hold:
- pair age ≥ 6h (cloud) / ≥ 2h (local, where holders can be checked), liquidity ≥ $75k
- 1h buys > sells, 1h and 24h price change positive, 5m not a spike above +25%
- RugCheck `https://api.rugcheck.xyz/v1/tokens/<mint>/report/summary`: no risks listed, LP mostly locked
- not a copy of a coin already held (same theme counts once at most twice)
Boosts on DexScreener are paid ads, a candidate list only, never a reason to buy.
No buy is a fine outcome. Cash is a position.
