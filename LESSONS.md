# Lessons

765 closed trades labelled, every book. Written by the bot.

- **slow-bleed**: 263 trades, mean -28%. NIO (v-momentum): -18% over 48h; NIO (v-velocity): -18% over 48h
- **other**: 232 trades, mean -32%. Max (v-swing): stop-loss at -23%; DCTY (v-velocity): event exit: price -35% in 5 minutes, -36% from entry
- **won-held**: 128 trades, mean +29%. DESSA (v-velocity): +4%, peak +19%; JOB (v-no-spike): +6%, peak +53%
- **bought-spike**: 54 trades, mean -35%. DCTY (v-tight): up 32854% in 24h at entry, peak +4%; DCTY (v-unease): up 32854% in 24h at entry, peak +4%
- **won-trailed**: 48 trades, mean +56495%. HOGE (v-swing): +105%, peak +295%; Max (v-tight): +2%, peak +44%
- **rug**: 19 trades, mean -100%. SCAMSON (v-tight): event exit: liquidity down 99% since entry, -100% from entry; Anthropig (v-swing): event exit: liquidity down 98% since entry, -100% from entry
- **liquidity-pulled**: 11 trades, mean -78%. OnlyCats (v-velocity): event exit: liquidity down 56% since entry, -80% from entry; BTX (v-unpaid): event exit: liquidity down 42% since entry, -65% from entry
- **stop-too-tight**: 10 trades, mean -40%. HOGE (v-unease): stopped at -42%, then +147% from the exit in a day; HOGE (v-velocity): stopped at -42%, then +147% from the exit in a day

To test: slow-bleed: take profit sooner; bought-spike: skip coins already up a lot in 24h; rug: ask for an older coin; liquidity-pulled: ask for a deeper pool; stop-too-tight: widen the stop by 5 points.
