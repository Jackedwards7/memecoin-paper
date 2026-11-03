# Memecoin trading playbook (research)

Copied from Jackson's vault (wiki page memecoin-trading-playbook: first run 2026-11-02, second run
2026-11-03) so the cloud run can read it. Outside knowledge from deep-research runs, not trading
advice. The rules that bind are in CLAUDE.md; this is the evidence behind them. Refreshed at each review.

## What the second run means for decisions here

- **Expect most entries to lose, even after the gate.** The best published rug filter halved losses
  (about 61% to 27%) and its picks still lost money. A pass is permission, not a reason to buy.
- **Never buy near migration.** 84% of migrated coins touched below 30% of their migration price
  within 20 minutes; the pool usually stays, the price doesn't. That is why entries need a pair at
  least 2 h (local) or 6 h (cloud) old.
- **Bundles hide concentration.** Bundled or linked wallets held 36.5% of a migrated coin's supply on
  average. Read RugCheck's insider flags as a floor, not the full picture.
- **Doubles are mostly manipulated** (82.8% showed wash trading, price inflation or >30% ownership
  concentration). A coin that has already doubled needs more scrutiny, not less.
- **Costs are real:** every paper fill now carries a sandwich charge; see CLAUDE.md.
- **Liquidity velocity** (fewer trades to reach a level) predicts graduation, not profit. It's a
  feature for the variant tests, not a buy signal on its own.

What the research says about memecoin trading, boiled down to rules a paper bot can apply. Asked for
in chat on 2026-11-02 so Jackson can feed it to memecoin-paper-book. All of it is outside
knowledge from a deep-research run checked 2026-11-02, not from his raw notes. Full report with
every citation: Memecoin trading playbook (in Jackson's vault).
Paper only: Claude places no real-money trades (paper-trading-experiment). In use as the paper book's rules v2 since 2026-11-03.

## The base rates

- About 1% of pump.fun coins graduate (two-year average; about 0.26% a week in mid-2026). 79% of
  9M launches (Nov 2025 to Oct 2026) never traded after launch day.
- Counting unsold bags at market value, about 10% of wallets were ahead after fees in 2026. The
  "73% profitable" figure counts sold trades only, after most losers had left.
- At least 17% of trades are wash trades. Only about 26% of big ($100k+) tracker "wins" were real
  buy-then-sell trades; 51% were sales of tokens sent from creator-linked wallets.
- The meme sector was about $29.7B on 2026-10-23, roughly 80% below the late-2024 peak. Most guides
  and backtests come from the kinder 2024 market.

## What has worked, and for whom

Documented profit follows information and speed: insiders, then slot-0 snipers and MEV bots, then
scalpers of exchange listings, then copy-traders, then KOL followers. A bot polling DexScreener is
in none of the first three.

- **Copy-trading** with a 2-minute delay averaged −41% per token (median −95%). Some "smart" wallets
  exist to be copied and dumped on.
- **KOL calls:** 76% of 377 crypto influencers on X had promoted now-worthless coins; the biggest
  accounts did worst. Paid undisclosed promos are common.
- **Original over copycat** is the one trend rule with data behind it: originals graduate 9.20% of
  the time, clones 0.86%.
- **Graduated pools are far safer than dev-opened ones:** 98% of graduation pools were never drained;
  99% of pools a dev opened directly were emptied, median 12 minutes in.
- **Filters stop working fast:** one model scored 0.86 in-sample and 0.46 (chance) two weeks later.
  Re-check any learned rule every few weeks.
- **Organic runners still round-trip:** WIF about −97% and FARTCOIN about −95% from their peaks.

## Safety gates before any paper entry

Run in order; a hard fail drops the coin. Sources and thresholds are in the report's 17-gate table;
values marked *guess* are starting points, not sourced.

1. Mint authority and freeze authority revoked (RugCheck `mintAuthority`, `freezeAuthority`).
2. No risky Token-2022 extension: permanent delegate, transfer hook, transfer fee above a few %
   (RugCheck `token_extensions`, GoPlus). 92% of new tokens use Token-2022, so this always runs.
3. Pool is the canonical graduation pool, not a dev-opened one; LP burned or locked
   (`markets[].lp.lpLockedPct`).
4. Supply spread: no linked cluster with a big share (Bubblemaps-style), bundled launch under about
   15–20%, snipers under about 30%, creator under about 10% (Webacy and guide thresholds).
5. Creator has no history of dead or rugged launches (pump.fun MCP creator profile).
6. Not a copycat: the earliest pair with that name is the original.
7. Paid attention only (DexScreener boost with no organic profile) is a warning, never a reason to buy.
8. When RugCheck and GoPlus disagree, count it as a fail.

## Costs the bot must charge itself

- Curve fee: 1%, 1.25% or 1.70% (sources conflict; 1.70% since 2026-10-17 per TokenPost). Use 1.70%
  for curve-stage trades until on-chain config shows otherwise.
- Graduated PumpSwap pools: pool fee 0.25% to about 1.2% by tier, plus a terminal fee of 0.5–1% a side.
- Price impact from the curve: 1 SOL into a 30 SOL reserve fills about 3.3% worse.
- An MEV charge that rises with slippage: swaps set at 20–50% slippage were sandwiched 148 per 10,000
  against 8 per 10,000 at 1–3%.

## Sizing and tests

- Practitioner sizing is 1–5% of bankroll per play; the report proposes 0.25 SOL on a 10 SOL book.
  The running book allows 1 SOL (10%).
- Two control arms make the 2026-11-30 review meaningful: random entries that pass the same gates,
  and rejected coins tracked as if bought. The test is whether gated picks beat random gated picks
  after costs.

> [!question] Unclear: the true pump.fun curve fee (1% / 1.25% / 1.70%) and the current PumpSwap tier
> table. pump.fun's fee page returned 403; reading on-chain config would settle it.

## Finding trends

Social APIs are now costly or closed: X charges $0.005 a post read (from 2026-02-06), Reddit
reportedly closed new API access on 2026-10-31, and the Google Trends API is invite-only. 23.5% of
pump.fun coins launch shortly after an X or Truth Social post, so by the time a bot sees a social
spike, creators have acted. The free, readable signal is narrative rotation on DexScreener
(`/metas/trending/v1`). The daily routine logs it: memecoin-trend-check.

## Second run, 2026-11-03: bot design and self-learning

A second deep-research run, mostly on academic papers, also outside knowledge:
Memecoin bot research (in Jackson's vault).

- Holding from the curve to graduation has negative expected value. 84% of migrated coins touch
  below 30% of their migration price within 20 minutes. The pools are rarely drained (98%, above);
  the price collapses anyway.
- The best published rug filter cut simulated losses from about 61% to 27%, but its picks still
  lost money. Score our filter on losses avoided compared with the control arm.
- Two new features: liquidity velocity (how few trades a coin needs to reach a curve level) and
  holder concentration after merging bundled wallets.
- Sandwich bots kept $345M on Solana over 3 years. Paper fills need a sandwich charge for each route.
- Self-tuning: log every variant, deflate results by the number tried, and promote a change only if
  it passes a PBO or deflated-Sharpe check across several splits. Strategies that passed still lost
  money.
