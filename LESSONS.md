# Lessons

683 closed trades labelled, every book. Written by the bot.

- **slow-bleed**: 226 trades, mean -28%. BLOB (v-unease): -41% over 28h; BLOB (v-velocity): -41% over 28h
- **other**: 210 trades, mean -32%. BLOB (v-dip): event exit: price -31% in 5 minutes, -24% from entry; BLOB (v-loose): event exit: price -31% in 5 minutes, -29% from entry
- **won-held**: 121 trades, mean +30%. BIG (claude): +5%, peak +29%; BIG (mech): +5%, peak +29%
- **bought-spike**: 48 trades, mean -35%. BJB (v-unease): up 4646% in 24h at entry, peak +5%; BJB (v-velocity): up 4646% in 24h at entry, peak +5%
- **won-trailed**: 43 trades, mean +63054%. BLOB (v-tight): +8%, peak +74%; BLOB (v-unpaid): +88%, peak +270%
- **rug**: 19 trades, mean -100%. SCAMSON (v-tight): event exit: liquidity down 99% since entry, -100% from entry; Anthropig (v-swing): event exit: liquidity down 98% since entry, -100% from entry
- **liquidity-pulled**: 11 trades, mean -78%. OnlyCats (v-velocity): event exit: liquidity down 56% since entry, -80% from entry; BTX (v-unpaid): event exit: liquidity down 42% since entry, -65% from entry
- **stop-too-tight**: 5 trades, mean -41%. Max (v-networks): stopped at -43%, then +76% from the exit in a day; Max (v-loose): stopped at -48%, then +96% from the exit in a day

To test: slow-bleed: take profit sooner; bought-spike: skip coins already up a lot in 24h; rug: ask for an older coin; liquidity-pulled: ask for a deeper pool; stop-too-tight: widen the stop by 5 points.
