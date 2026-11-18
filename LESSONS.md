# Lessons

659 closed trades labelled, every book. Written by the bot.

- **slow-bleed**: 218 trades, mean -27%. NIO (v-swing): -24% over 15h; Rocco (v-unease): -35% over 15h
- **other**: 203 trades, mean -32%. NIO (v-tight): stop-loss at -21%; GTA (v-tight): stop-loss at -21%
- **won-held**: 119 trades, mean +31%. MEVS (v-no-spike): +13%, peak +66%; MEVS (v-velocity): +13%, peak +66%
- **bought-spike**: 48 trades, mean -35%. BJB (v-unease): up 4646% in 24h at entry, peak +5%; BJB (v-velocity): up 4646% in 24h at entry, peak +5%
- **won-trailed**: 37 trades, mean +73268%. Rocco (v-tight): +35%, peak +168%; Rocco (v-velocity): +80%, peak +152%
- **rug**: 19 trades, mean -100%. SCAMSON (v-tight): event exit: liquidity down 99% since entry, -100% from entry; Anthropig (v-swing): event exit: liquidity down 98% since entry, -100% from entry
- **liquidity-pulled**: 11 trades, mean -78%. OnlyCats (v-velocity): event exit: liquidity down 56% since entry, -80% from entry; BTX (v-unpaid): event exit: liquidity down 42% since entry, -65% from entry
- **stop-too-tight**: 4 trades, mean -39%. Rocco (v-swing): stopped at -25%, then +135% from the exit in a day; Max (v-networks): stopped at -43%, then +76% from the exit in a day

To test: slow-bleed: take profit sooner; bought-spike: skip coins already up a lot in 24h; rug: ask for an older coin; liquidity-pulled: ask for a deeper pool; stop-too-tight: widen the stop by 5 points.
