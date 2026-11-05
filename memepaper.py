#!/usr/bin/env python3
"""Memecoin paper book: screen, paper-buy, paper-sell and mark-to-market.

Paper only. No wallet, no keys, no orders: prices come from the free public
DexScreener and RugCheck APIs and every fill is simulated.

  python3 -I memepaper.py screen <mint> [<mint> ...]   # table of live stats
  python3 -I memepaper.py gate <mint> [<mint> ...]     # hard safety gates; passes unlock buy
  python3 -I memepaper.py buy <mint> <sol> "<thesis>" [--stop -0.35] [--tp1 1.0]
  python3 -I memepaper.py sell <mint> <fraction 0-1> "<reason>"
  python3 -I memepaper.py mark        # reprice, apply stops/take-profits, write the .md

State mode (Tier 1 phase 1; on when MEMEPAPER_STATE names a folder): books live in
<state>/books/<arm>.json, and only `tick` changes them. `gate`, `buy` and `sell` then write order
files to <state>/orders/ instead, and the next tick applies them in order. One writer per file.

  python3 -I memepaper.py tick        # apply pending orders, then mark
  python3 -I memepaper.py status      # report, pending orders, last results (read only)
  python3 -I memepaper.py replay <YYYY-MM-DD>   # re-run the arms' picks on a day's dataset
  python3 -I memepaper.py brief <mint>          # one page on a coin: chart, reading, X, similar cases
  python3 -I memepaper.py autopsy [days]        # what separated the winners from the collapses
  python3 -I memepaper.py datacheck [YYYY-MM-DD]  # how complete a day of the dataset is
  python3 -I memepaper.py migrate <old repo dir> <state dir>   # one-time move of the books
  python3 -I memepaper.py loop [--minutes 55] [--every 60]     # the hot loop (GitHub Actions)
  python3 -I memepaper.py watchdog    # alert if the loop's health.json is stale
  python3 -I memepaper.py feed [--seconds N]   # keep the free launch stream in MEMEPAPER_FEED (a server, not Actions)
  python3 -I memepaper.py learn       # the weekly learning run, now; proposes only until LEARN_FROM
  python3 -I memepaper.py mergecheck  # reads a diff on stdin: may it merge without Jackson?

Alerts go to ntfy when NTFY_TOPIC is set (a GitHub secret); otherwise they only print.

Rules v2 (from 2026-11-03, Jackson's call after the playbook research): every buy needs a gate
pass from the last 2 hours, and each buy also opens a same-size position in control.json on a
random coin from the same gate-pass pool. Gate failures are tracked as shadow rejects for 7 days.
The review asks whether picks beat the control after costs.
"""
import json, sys, time, subprocess, datetime, os, fcntl, random, urllib.parse, copy, gzip, glob, re, hashlib, math, struct, zlib
import base64, itertools, socket, sqlite3, ssl, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
BOOK = os.path.join(HERE, "book.json")
CONTROL = os.path.join(HERE, "control.json")
REPORT = os.path.join(HERE, "book.md")

START_SOL = 10.0
START_SOL_USD = 94.86   # SOL price when the book opened (2026-11-02 05:44 UTC), for the benchmark
V2_START = "2026-11-03 01:30 UTC"  # rules v2 begin; positions opened before are legacy v1
REVIEW_DATE = "2026-11-30"  # judge v2 then, or after 30 closed v2 trades; rules frozen until then
FEE = 0.015         # v2: PumpSwap pool fee 0.25-1.2% + terminal/priority 0.5-1%, each side (v1 used 1.25%)
SLIP_K = 0.5        # extra slippage: size / liquidity * SLIP_K (rough constant-product impact)
# Sandwich (MEV) charge per swap, from 2026-11-03 research: sandwiched swaps lose a median ~$5, and
# memecoin terminal users are hit 14-21x their share of swaps. The share of our swaps that would be
# sandwiched isn't measured; $0.50 assumes about 1 in 10 (a guess, labelled as one). The report also
# shows P&L as if every swap were sandwiched at the median.
SANDWICH_USD = 0.50
SANDWICH_STRESS_USD = 5.0
MAX_POS_SOL = 0.25  # v2: 2.5% of the starting book (practitioner sizing is 1-5% a play; v1 allowed 1 SOL)
MAX_OPEN = 6        # open v2 positions; legacy v1 positions don't count
GATE_TTL_H = 2      # a buy needs a gate pass this recent
GRAD_POOLS = ("pump_fun_amm", "raydium", "raydium_cpmm")  # graduation pools (PumpSwap; Raydium before 2025)
LP_LOCK_MIN = 90          # % of the deepest pool's LP burned or locked
TOP_HOLDER_MAX = 0.05     # any single non-pool wallet
INSIDER_MAX = 0.15        # wallets RugCheck flags as insiders (bundles, linked wallets)
COPY_MIN_LIQ = 10_000     # $ liquidity for a same-name pool to count as an earlier original
CREATOR_MAX = 0.10
TRANSFER_FEE_MAX = 3      # % Token-2022 transfer fee
REJECT_DAYS = (1, 3, 7)   # shadow rejects are scored this many days after the gate failed them
TIME_STOP_H = 48          # flat this long without hitting the take-profit -> sell
TIME_STOP_MIN_GAIN = 0.20 # "flat" = less than +20% from entry
# Rug rule (phase 2): a coin missing from the batch price call counts as rugged only after
# RUG_MISSING_MIN minutes AND when both second sources agree it's gone: DexScreener search finds no
# pair with GONE_LIQ+ liquidity, and RugCheck marks it rugged or shows under GONE_LIQ in its pools.
# Replaces "3 checks in a row", which at 60 s ticks would zero a live coin after a 3-minute API blip.
RUG_MISSING_MIN = 30
RUG_RECHECK_MIN = 5       # how often the second sources are asked while a coin is missing
RUG_BACKSTOP_H = 24       # missing this long with the sources disagreeing -> marked to zero anyway
GONE_LIQ = 1_000
# Event exits (phase 2): sell at once, before the normal rules, on either of these.
EVENT_LIQ_DROP = 0.40     # pool liquidity down this much since entry (a pull or a drain)
EVENT_M5_DROP = -20       # % price change over 5 minutes (DexScreener's m5)
STALE_MIN = 20            # watchdog: last pushed tick older than this -> alert (pushes come every 10 min)
ERRORS_ALERT = 3          # failed ticks in a row before an alert
PUSH_EVERY_S = 600        # the loop pushes on anything material, else this often
# Phase 3: every CYCLE_MIN the loop snapshots the universe into data/ and runs the mechanical arms.
CYCLE_MIN = 15
CYCLE_BUDGET_S = 45       # gating stops here and resumes next cycle, so exits are never held up
UNIVERSE_MIN_AGE_H = 6    # the cloud universe rule (CLAUDE.md, Entries)
UNIVERSE_MIN_LIQ = 75_000
GATE_REFRESH_MIN = 60     # a coin is re-gated at most this often (a pass lasts GATE_TTL_H)
WATCH_DAYS = 10           # a coin that ever qualified is tracked this long after it last did
WATCH_FRESH_H = 24        # one that never has gets this long from its last listing (most are tiny)
WATCH_MAX = 400
GATE_STOP_AFTER = 3       # checks that couldn't finish in one cycle before gating waits for the next
CANT_CHECK = ("RugCheck unavailable", "copycat check failed")  # an outage, not a verdict on the coin
ARM_CASH_FLOOR = 5.0      # the same floor Claude's entries have
ARM_COOLDOWN_H = 24       # an arm won't re-buy a coin it closed this recently
# The Grok X scout writes one file per run to the private desk; the loop reads the newest. Nothing
# in a file is trusted: it's shape-checked, a sample of its posts is looked up on X, and the X arms
# only act after SCOUT_TRUST_RUNS clean files in a row. Any bad file resets that to zero.
DESK_SCOUT = "https://api.github.com/repos/Jackedwards7/lucent-bot-desk/contents/from-bots/scout/memecoin"
SCOUT_MAX_AGE_H = 5       # a run every 4 hours, plus lateness; older data isn't used
SCOUT_TRUST_RUNS = 3
SCOUT_SAMPLE = 5          # posts looked up per file
SCOUT_TIME_SLACK_S = 120
SCOUT_MAX_COINS, SCOUT_MAX_POSTS = 15, 20
X_NEW_DAYS = 30           # an account younger than this is "new"
X_SMALL_FOLLOWERS = 10_000
X_KOL_FOLLOWERS = 100_000
X_KOL_BURST = 3           # large accounts on one coin in a window, and more than last window
DESK_STORIES = DESK_SCOUT.rsplit("/", 1)[0] + "/stories"  # Grok's why-it's-moving notes: information only
DESK_OPINION = DESK_SCOUT.rsplit("/", 1)[0] + "/opinion"  # Grok's weekly argument against our lessons
STORY_MAX_CHARS = 400     # a note longer than this is cut: it's read as data, never as instructions
# The reading layer (Tier 1 phase 3b). Records and derives; it never changes the live book's rules.
SCHEMA = 4                # dataset version; a change here means old rows lack the new fields
GT = "https://api.geckoterminal.com/api/v2/networks/solana"
GT_PER_TICK = 3           # calls a minute. Docs say 30; live probes hit 429 after a handful
GT_GAP_S = 5
GT_BACKOFF_S = 180
GT_CHUNK = 30             # pools per multi-pool call
READ_MIN_CANDLES = 12
READ_WINDOW = 96          # a coin's "normal" is its last day of 15-minute candles
UNEASE_EXIT = 4           # of the five signs: v-unease sells here. A guess the arm exists to test
SWING_K = 4               # v-swing's stop, in normal 15-minute swings. Also a guess
MAX_NETWORKS = 0.15       # v-networks: the gate's insider limit, applied to the graph instead
AUTOPSY_DAYS = 14
AUTOPSY_HOURS = 24        # how far ahead a coin is judged
AUTOPSY_WIN = 1.0         # +100% at some point in that time, before any -35%
AUTOPSY_LOSS = -0.5
AUTOPSY_CRASH = -0.8      # the danger check's collapse: this far under the sampled price in that time
AUTOPSY_MIN = 30          # coins on each side before a result is shown at all
DATA_MIN_CYCLES = 85      # of 96 a day, before the check alerts
DATA_MAX_MB = 500
GT_FIRST_CANDLES = 1000   # a coin's first fetch brings its history, so a reading needn't wait a day
# The free launch stream (PumpPortal, no key, no wallet). `feed` is its own always-on process and
# writes a local sqlite file, never the state branch; the loop only reads that file. It can't run on
# Actions: see server/setup.sh. With MEMEPAPER_FEED unset everything here does nothing.
PP_HOST, PP_PATH = "pumpportal.fun", "/api/data"
FEED_QUIET_S = 120        # launches come every few seconds: this long with no frame is a dead connection
FEED_RETRY_S = (5, 900)   # reconnect wait, doubling
FEED_STEADY_S = 300       # a connection that lasted this long starts the wait again
FEED_BAN_S = 3900         # a refused handshake may be a ban, and PumpPortal's lift hourly
FEED_MAX_FRAME = 1 << 20
FEED_GRAD_H = 2           # how long a graduate is offered to the watch list once old enough for the universe
FEED_STALE_MIN = 30
# Jupiter's real prices beside the paper fills. Quotes only: nothing is signed or sent.
JUP = "https://lite-api.jup.ag/swap/v1/quote"
JUP_KEYED = "https://api.jup.ag/swap/v1/quote"
JUP_COINS = 5             # coins a cycle, two calls each
JUP_COINS_KEYLESS = 2     # with no key it refused the sixth call of a burst (measured 2026-11-03)
JUP_BPS = 1000
JUP_STOP_AFTER = 2        # failed coins before this cycle gives up: it's only a measurement
HEALTH_PING_S = 300
LOCK = "/tmp/memepaper.lock"  # the 2-minute watcher and manual trades never write at once
# Post-mortems (Tier 1 phase 4). A trade is labelled once it's a day old, so what the coin did after
# the exit can count.
LABELS = ("rug", "liquidity-pulled", "copycat", "bought-spike", "theme-faded", "stop-too-tight",
          "slow-bleed", "won-held", "won-trailed", "other")  # copycat and theme-faded need judgement: code never picks them
LABEL_WAIT_H = 25         # a closed trade gets its label after this long, with or without the 24h look-back
STOP_RECOVERED = 0.5      # stopped out, then the coin rose this much from the exit: the stop was too tight
SPIKE_H24, SPIKE_M5, SPIKE_PEAK = 150, 15, 0.05  # bought after this much, and never rose past this
BLEED_H = 12              # a loss held this long fell slowly
LESSONS_MAX = 3000        # bytes in LESSONS.md
LESSON_REPEAT = 3         # a label seen this often becomes an idea to test
# The weekly learning run (phase 5). It proposes only until LEARN_FROM: rules v2 are frozen for the review.
LEARN_FROM = "2026-11-30 00:00 UTC"
LEARN_DAYS = 28           # the scoring window
LEARN_SIM_DAYS = 14       # how much of the dataset a challenger is replayed on
LEARN_MIN_TRADES = 15     # closed trades before an arm can be promoted or retired
LEARN_MAX_ARMS = 8        # no new challenger while this many arms or more are live
LEARN_SPLITS = 8          # time blocks for PBO: 70 ways to split them in half
DSR_MIN, PBO_MAX = 0.95, 0.10
PARAM_KEYS = ("stop", "tp1", "sol", "max_open", "min_age_h", "min_liq", "max_h24")
# What a merge without Jackson may touch. Guarded names are the safety limits and this guard itself.
MERGE_PATHS = ("memepaper.py", "params/")
MERGE_NEVER = ("params/bounds.json",)
GUARDED = ("FEE", "SANDWICH_USD", "SLIP_K", "MAX_POS_SOL", "MAX_OPEN", "GATE_TTL_H", "GRAD_POOLS", "LP_LOCK_MIN", "TOP_HOLDER_MAX", "INSIDER_MAX", "COPY_MIN_LIQ",
           "CREATOR_MAX", "TRANSFER_FEE_MAX", "UNIVERSE_MIN_AGE_H", "UNIVERSE_MIN_LIQ", "LEARN_FROM", "MERGE_PATHS", "MERGE_NEVER",
           "GUARDED", "GUARDED_FUNCS", "NO_WALLET", "PARAM_KEYS")
GUARDED_FUNCS = ("gate_one", "gate", "_passed", "impact", "_open", "_sell", "_apply_exits", "_clamped", "arm_cfg", "merge_refusals", "guard", "learn")
NO_WALLET = re.compile(r"private.?key|secret.?key|seed.?phrase|mnemonic|keypair|signTransaction|sendTransaction|/swap\b", re.I)
GUARD_S = 3600            # new code that stays healthy this long becomes the version to go back to
ORDERS = None             # state mode: the orders inbox folder. None = legacy mode (books beside the code)
BOOKS = None              # state mode: the folder of arm books
STATE = None              # state mode: the state branch's worktree
ORDER_TTL_MIN = 30        # a buy order older than this is refused: its prices and thesis are stale
APPLIED_KEEP = 500        # order ids remembered in the claude book, so none is applied twice
STOP_RANGE = (-0.5, -0.1) # an order's stop and take-profit must sit inside these
TP1_RANGE = (0.2, 5.0)


class Refused(Exception):
    """A trade the rules don't allow. Legacy commands exit with it; ticks record it."""


def use_state(d):
    """Point every path at a state folder (the state branch's worktree)."""
    global BOOK, CONTROL, REPORT, SOL_CACHE, ORDERS, BOOKS, STATE
    STATE = d
    BOOKS, ORDERS = os.path.join(d, "books"), os.path.join(d, "orders")
    for x in (BOOKS, ORDERS, os.path.join(ORDERS, "done")):
        os.makedirs(x, exist_ok=True)
    BOOK, CONTROL = os.path.join(BOOKS, "claude.json"), os.path.join(BOOKS, "control.json")
    REPORT, SOL_CACHE = os.path.join(d, "book.md"), os.path.join(d, ".sol_usd")


def get(url):
    # curl, not urllib: the python.org build on this Mac has no CA bundle installed.
    out = subprocess.run(["curl", "-sf", "-m", "20", "-A", "memepaper/1.0", url],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


SOL_MINT = "So11111111111111111111111111111111111111112"
SOL_CACHE = os.path.join(HERE, ".sol_usd")  # last good price, for when both sources fail


def sol_usd():
    """SOL in USD: CoinGecko, else the deepest DexScreener SOL/USDC-USDT pair, else the
    last good price (under 6h old). Free CoinGecko rate-limits shared cloud IPs."""
    px = None
    try:
        px = float(get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd")["solana"]["usd"])
    except Exception:
        try:
            ps = [p for p in get(f"https://api.dexscreener.com/tokens/v1/solana/{SOL_MINT}")
                  if p["baseToken"]["address"] == SOL_MINT and p["quoteToken"]["symbol"] in ("USDC", "USDT")]
            best = max(ps, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
            px = float(best["priceUsd"])
        except Exception:
            pass
    if px and 1 < px < 100000:
        open(SOL_CACHE, "w").write(f"{px} {time.time()}")
        return px
    try:
        v, t = open(SOL_CACHE).read().split()
        if time.time() - float(t) < 6 * 3600:
            return float(v)
    except Exception:
        pass
    raise RuntimeError("no SOL price from CoinGecko, DexScreener or a recent cache")


def pairs(mints):
    """Best (most liquid) Solana pair per mint, from DexScreener (30 per call)."""
    out = {}
    for i in range(0, len(mints), 30):
        chunk = ",".join(mints[i:i + 30])
        data = get(f"https://api.dexscreener.com/tokens/v1/solana/{chunk}") or []
        for p in data:
            m = p["baseToken"]["address"]
            liq = (p.get("liquidity") or {}).get("usd") or 0
            if m not in out or liq > ((out[m].get("liquidity") or {}).get("usd") or 0):
                out[m] = p
    return out


def rug(mint):
    try:
        r = get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary")
        return r.get("score_normalised"), [x.get("name") for x in r.get("risks", [])]
    except Exception as e:
        return None, [f"rugcheck error {e}"]


def load(path=None):
    path = path or BOOK  # looked up at call time, so tests can point BOOK at a temp folder
    if os.path.exists(path):
        b = json.load(open(path))
    else:
        b = {"start_sol": START_SOL, "cash_sol": START_SOL, "positions": {}, "closed": [], "log": []}
    b.setdefault("gate_pass", {})
    b.setdefault("rejects", {})
    b.setdefault("passes", {})
    return b


def save(b, path=None):
    """Write to a temp file and rename, so a crash never leaves half a book."""
    path = path or BOOK
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(b, f, indent=2)
    os.replace(tmp, path)


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def gate_one(mint, p, info=None):
    """The playbook's hard safety gates (wiki: memecoin-trading-playbook). Returns the failures;
    an empty list is a pass. Anything that can't be checked counts as a fail. If `info` is a dict
    it's filled with the measurements behind the checks, for the dataset and the arms."""
    info = {} if info is None else info
    try:
        r = get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report")
    except Exception as e:
        return [f"RugCheck unavailable ({e.__class__.__name__})"]
    fails = []
    info.update(score=r.get("score_normalised"), holders=r.get("totalHolders"), creator_raw=r.get("creatorBalance"),
                graph=r.get("graphInsidersDetected"), flagged=sum(1 for h in r.get("topHolders") or [] if h.get("insider")),
                detail={"networks": (r.get("insiderNetworks") or [])[:10], "creator": r.get("creator"), "lp_providers": r.get("totalLPProviders"),
                        "top": [[h.get("pct"), bool(h.get("insider")), h.get("owner")] for h in (r.get("topHolders") or [])[:20]]})
    # 1-2. authorities revoked, no risky Token-2022 extension
    if r.get("mintAuthority") or r.get("freezeAuthority"):
        fails.append("mint or freeze authority not revoked")
    ext = r.get("token_extensions") or {}
    for k in ("permanentDelegate", "transferHook", "nonTransferable"):
        if ext.get(k):
            fails.append(f"Token-2022 {k}")
    if ((r.get("transferFee") or {}).get("pct") or 0) > TRANSFER_FEE_MAX:
        fails.append(f"transfer fee {r['transferFee']['pct']}%")
    if r.get("rugged"):
        fails.append("RugCheck marks it rugged")
    danger = [x.get("name") for x in r.get("risks") or [] if x.get("level") == "danger"]
    if danger:
        fails.append("RugCheck danger: " + ", ".join(danger))
    # 3. the deepest pool is the graduation pool with its LP locked, not a pool the dev opened
    mk = [m for m in r.get("markets") or [] if m.get("lp")]
    if mk:
        deep = max(mk, key=lambda m: (m["lp"].get("quoteUSD") or 0) + (m["lp"].get("baseUSD") or 0))
        locked = info["lp_locked"] = deep["lp"].get("lpLockedPct") or 0
        if deep.get("marketType") not in GRAD_POOLS:
            fails.append(f"deepest pool is {deep.get('marketType')}, not a graduation pool")
        elif locked < LP_LOCK_MIN:
            fails.append(f"LP only {locked:.0f}% locked")
    else:
        fails.append("no pool data")
    # 4. supply spread: no big single wallet, insider cluster or creator bag
    supply = (r.get("token") or {}).get("supply") or 0
    pools = {m.get("pubkey") for m in mk} | {a for a, v in (r.get("knownAccounts") or {}).items()
                                              if (v or {}).get("type") == "AMM"}
    if supply:
        big = [h for h in r.get("topHolders") or []
               if h.get("owner") not in pools and h.get("address") not in pools
               and h.get("amount", 0) / supply > TOP_HOLDER_MAX]
        if big:
            fails.append(f"a wallet holds {big[0]['amount'] / supply:.0%} of supply")
        # RugCheck's per-wallet insider flag; its network totals overlap and include the pool.
        ins = sum(h.get("amount", 0) for h in r.get("topHolders") or []
                  if h.get("insider") and h.get("owner") not in pools) / supply
        nets = [n.get("currentHolding") for n in r.get("insiderNetworks") or []]
        wallets = [h.get("amount", 0) / supply for h in r.get("topHolders") or []
                   if h.get("owner") not in pools and h.get("address") not in pools]
        info.update(insider=ins, creator=(r.get("creatorBalance") or 0) / supply,
                    networks=round(sum(x or 0 for x in nets) / supply, 6) if nets else None,
                    top=max(wallets, default=0), top10=round(sum(sorted(wallets)[-10:]), 6))
        if ins > INSIDER_MAX:
            fails.append(f"insider wallets hold {ins:.0%}")
        if (r.get("creatorBalance") or 0) / supply > CREATOR_MAX:
            fails.append(f"creator holds {r['creatorBalance'] / supply:.0%}")
    else:
        fails.append("no supply data")
    # 6. originals only: the earliest real Solana pool with this name must be this mint. Same-name
    # launches that never got a real pool (dead on the curve) don't count as the original.
    name = (r.get("tokenMeta") or {}).get("name") or p["baseToken"].get("name")
    try:
        same = [q for q in get("https://api.dexscreener.com/latest/dex/search?q=" + urllib.parse.quote(name)).get("pairs") or []
                if q.get("chainId") == "solana" and q.get("pairCreatedAt") and norm(q["baseToken"].get("name")) == norm(name)
                and ((q.get("liquidity") or {}).get("usd") or 0) >= COPY_MIN_LIQ]
        if same:
            first = min(same, key=lambda q: q["pairCreatedAt"])
            if first["baseToken"]["address"] != mint:
                fails.append(f"copycat: an earlier '{name}' exists ({first['baseToken']['address'][:6]})")
    except Exception as e:
        fails.append(f"copycat check failed ({e.__class__.__name__})")
    return fails


def gate(mints):
    """Gate each mint. A pass is remembered for GATE_TTL_H hours (buy needs it, and the pool of
    passes is what the control arm draws from); a fail becomes a shadow reject, scored later."""
    t = time.time()
    ps = pairs(mints)
    results = {}
    for m in mints:
        p = ps.get(m)
        if not p:
            print(f"{m[:6]}  FAIL no pair")
            continue
        fails = gate_one(m, p)
        sym = p["baseToken"]["symbol"]
        results[m] = {"symbol": sym, "px": float(p["priceUsd"]), "fails": fails}
        if fails:
            print(f"{sym[:10]:10} {m[:6]}  FAIL " + "; ".join(fails))
        else:
            warn = "  (warning: paid boost with no profile)" if p.get("boosts") and not p.get("info") else ""
            print(f"{sym[:10]:10} {m[:6]}  PASS{warn}")
    if ORDERS:
        o = write_order("gate", results=results)
        print(f"queued {o['id']}: the next tick records these results")
        return
    b = load()
    _ingest_gate(b, results, t)
    save(b)


def _ingest_gate(b, results, t):
    """Record gate results checked at time t: passes unlock buys for GATE_TTL_H hours, fails
    revoke any pass and become shadow rejects."""
    b["gate_pass"] = {m: s for m, s in b["gate_pass"].items() if time.time() - s < GATE_TTL_H * 3600}
    for m, r in results.items():
        if r["fails"]:
            b["gate_pass"].pop(m, None)
            if m not in b["rejects"]:
                b["rejects"][m] = {"symbol": r["symbol"], "at": t, "px": r["px"], "fails": r["fails"], "moves": {}}
        else:
            # Shadow passes: scored like rejects, so the gate is judged on losses avoided
            # (passes against rejects), not on whether any pick made money.
            if m not in b["passes"] and m not in b["rejects"]:
                b["passes"][m] = {"symbol": r["symbol"], "at": t, "px": r["px"], "fails": [], "moves": {}}
            if time.time() - t < GATE_TTL_H * 3600:
                b["gate_pass"][m] = max(t, b["gate_pass"].get(m, 0))


def clock():
    return time.time()  # one place to fake the time in tests


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def impact(sol, p, su):
    liq_sol = ((p.get("liquidity") or {}).get("usd") or 0) / su / 2  # one side of the pool
    return min(0.5, SLIP_K * sol / liq_sol) if liq_sol else 0.5


def screen(mints):
    ps = pairs(mints)
    t = time.time() * 1000
    rows = []
    for m in mints:
        p = ps.get(m)
        if not p:
            rows.append((0, f"{m[:6]}  no pair"))
            continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        tx = p.get("txns", {}).get("h1", {})
        pc = p.get("priceChange", {})
        age = (t - (p.get("pairCreatedAt") or t)) / 3.6e6
        rows.append((p.get("marketCap") or 0,
                     f"{p['baseToken']['symbol'][:10]:10} {m[:6]} {p['dexId'][:9]:9} mc ${(p.get('marketCap') or 0)/1e3:8.0f}k "
                     f"liq ${liq/1e3:6.0f}k vol1h ${(p.get('volume') or {}).get('h1',0)/1e3:6.0f}k "
                     f"b/s1h {tx.get('buys',0)}/{tx.get('sells',0)} "
                     f"5m {pc.get('m5',0):+6.1f}% 1h {pc.get('h1',0):+6.1f}% 24h {pc.get('h24',0):+7.1f}% age {age:6.1f}h"))
    for _, r in sorted(rows, reverse=True):
        print(r)


def _open(b, mint, sol, thesis, stop, tp1, p, su):
    px = float(p["priceUsd"])
    fill = px * (1 + impact(sol, p, su))
    mev = SANDWICH_USD / su
    tokens = (sol * (1 - FEE) - mev) * su / fill
    score, risks = rug(mint)
    b["cash_sol"] -= sol
    b["positions"][mint] = {
        "symbol": p["baseToken"]["symbol"], "opened": now(), "cost_sol": sol, "tokens": tokens,
        "entry_px": fill, "entry_mc": p.get("marketCap"), "peak_px": fill, "stop": stop, "tp1": tp1,
        "tp1_done": False, "thesis": thesis, "rugcheck": score, "risks": risks, "realised_sol": 0.0,
        "dex": p["dexId"], "url": p.get("url"), "v": 2, "mev_sol": mev, "swaps": 1,
        "entry_liq": (p.get("liquidity") or {}).get("usd") or 0, **_entry_context(b, mint, p)}
    b["log"].append(f"{now()} BUY {p['baseToken']['symbol']} {sol:.2f} SOL @ ${fill:.8g} (mc ${p.get('marketCap',0):,.0f}): {thesis}")
    print(b["log"][-1])


def buy(mint, sol, thesis, stop=-0.35, tp1=1.0):
    """Legacy mode: trade now. State mode: queue an order for the next tick."""
    if ORDERS:
        o = write_order("buy", mint=mint, sol=float(sol), thesis=thesis, stop=float(stop), tp1=float(tp1))
        print(f"queued {o['id']}: the next tick re-checks the gate and buys")
        return
    b, c = load(), load(CONTROL)
    try:
        _buy(b, c, mint, sol, thesis, stop, tp1)
    except Refused as e:
        sys.exit(str(e))


def _entry_context(b, mint, p):
    """What the position remembers about its entry, for the casebook: how the coin looked, how long
    since this book's last loss (revenge entries) and whether it has held this coin before."""
    t = round(clock())
    lost = [_ts(x["closed"]) for x in b["closed"] if x.get("pnl_sol", 0) < 0 and x.get("closed")]
    at = make_row(mint, p, None, t)
    for k in ("gate", "arms", "x", "t", "mint", "symbol"):
        at.pop(k)
    if STATE:
        at["read"] = _jload(os.path.join(STATE, "reads.json"), {}).get(mint)
    return {"at_entry": at, "reentry": any(x.get("mint") == mint for x in b["closed"]),
            "since_loss_h": round((t - max(lost)) / 3600, 1) if lost else None}


def _buy(b, c, mint, sol, thesis, stop, tp1, regate=False, persist=True):
    """Open the pick and its control, saving both books. Raises Refused, changing nothing.
    regate: run the gate again on the pick first (ticks do, so a pass is fresh when it's used).
    persist: save the books here (legacy); a tick saves them itself, together with the order id."""
    sol = min(float(sol), MAX_POS_SOL, b["cash_sol"])
    if not (STOP_RANGE[0] <= stop <= STOP_RANGE[1] and TP1_RANGE[0] <= tp1 <= TP1_RANGE[1]):
        raise Refused(f"stop {stop} or take-profit {tp1} outside the allowed range")
    if sol <= 0:
        raise Refused("no cash")
    if sum(1 for q in b["positions"].values() if q.get("v") == 2) >= MAX_OPEN:
        raise Refused("max open positions reached")
    if mint in b["positions"]:
        raise Refused("already holding")
    t = time.time()
    pool = [m for m, s in b["gate_pass"].items() if t - s < GATE_TTL_H * 3600]
    if mint not in pool:
        raise Refused(f"no gate pass in the last {GATE_TTL_H}h: run `gate {mint}` first")
    if regate:
        p = pairs([mint]).get(mint)
        fails = gate_one(mint, p) if p else ["no pair"]
        if fails:
            _ingest_gate(b, {mint: {"symbol": (p or {}).get("baseToken", {}).get("symbol", mint[:6]),
                                    "px": float(p["priceUsd"]) if p else 0.0, "fails": fails}}, t)
            raise Refused("gate failed at execution: " + "; ".join(fails))
    su = sol_usd()
    # The control never draws the pick itself (from 2026-11-03): a control on the same coin
    # copies the pick's result and tells the review nothing.
    free = [m for m in pool if m != mint and m not in c["positions"]]
    ctl = random.SystemRandom().choice(free) if free else None
    ps = pairs([mint] + ([ctl] if ctl else []))
    if mint not in ps:
        raise Refused("no price for the pick")
    _open(b, mint, sol, thesis, stop, tp1, ps[mint], su)
    if persist:
        save(b)
    # Control arm: same size and exits, on a coin drawn at random from the same gate passes.
    if ctl and ctl in ps:
        _open(c, ctl, sol, f"control for {ps[mint]['baseToken']['symbol']}: random pick from {len(free)} other gate passes", stop, tp1, ps[ctl], su)
        if persist:
            save(c, CONTROL)
    else:
        print("no control entry: no other unheld gate pass to draw from")


def _sell(b, mint, frac, reason, p, su):
    pos = b["positions"][mint]
    qty = pos["tokens"] * frac
    px = float(p["priceUsd"]) if p else 0.0
    gross_sol = qty * px / su
    proceeds = gross_sol * (1 - FEE) * (1 - impact(gross_sol, p, su) if p else 0)
    if p:  # a real swap: charge the sandwich cost (a rug marked to zero isn't a swap)
        mev = min(proceeds, SANDWICH_USD / su)
        proceeds -= mev
        pos["mev_sol"] = pos.get("mev_sol", 0.0) + mev
        pos["swaps"] = pos.get("swaps", 0) + 1
    pos["tokens"] -= qty
    pos["realised_sol"] += proceeds
    b["cash_sol"] += proceeds
    b["log"].append(f"{now()} SELL {frac:.0%} {pos['symbol']} -> {proceeds:.3f} SOL @ ${px:.8g}: {reason}")
    if pos["tokens"] <= 1e-9 or frac >= 0.999:
        pnl = pos["realised_sol"] - pos["cost_sol"]
        b["closed"].append({**pos, "mint": mint, "closed": now(), "pnl_sol": pnl,
                            "pnl_pct": pnl / pos["cost_sol"], "exit_reason": reason, "exit_px": px})
        del b["positions"][mint]
    print(b["log"][-1])


def sell(mint, frac, reason):
    """Legacy mode: sell now. State mode: queue an order for the next tick."""
    if ORDERS:
        o = write_order("sell", mint=mint, fraction=float(frac), reason=reason)
        print(f"queued {o['id']}: the next tick sells")
        return
    b = load()
    su = sol_usd()
    p = pairs([mint]).get(mint)
    _sell(b, mint, float(frac), reason, p, su)
    save(b)
    write_report(b, su, pairs(list(b["positions"])) if b["positions"] else {})


def held_hours(pos):
    opened = datetime.datetime.strptime(pos["opened"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - opened).total_seconds() / 3600


def mark(quiet=False):
    """Reprice everything. Rules, in order:
      - hard stop at entry*(1+stop) until the take-profit has fired;
      - at +tp1, sell half (cost back out);
      - after that, a 40% trailing stop from the peak on the rest;
      - time stop: held TIME_STOP_H hours, take-profit never reached and less than
        +TIME_STOP_MIN_GAIN from entry -> sell, the money is better used elsewhere;
      - event exits first: liquidity down EVENT_LIQ_DROP since entry, or price down EVENT_M5_DROP %
        in 5 minutes, sells everything at once;
      - a coin missing from the price call is marked to zero only by the rug rule (see the constants).
    The control book gets the same rules; shadow rejects get their 1/3/7-day moves recorded."""
    b = load()
    c = load(CONTROL)
    extra = {p: load(p) for p in other_arms()}  # phase 3's variant books, when there are any
    su = sol_usd()
    t = time.time()
    shadows = [(k, m) for k in ("rejects", "passes") for m, r in b[k].items()
               if any(f"{d}d" not in r["moves"] and t - r["at"] >= d * 86400 for d in REJECT_DAYS)]
    due = list(dict.fromkeys(m for _, m in shadows))
    held = [m for bk in (b, c, *extra.values()) for m in bk["positions"]]
    want = list(dict.fromkeys(held + due))
    ps = pairs(want) if want else {}
    for bk in (b, c, *extra.values()):
        _apply_exits(bk, ps, su)
    for p, bk in extra.items():
        bk["last_mark"] = now()
        save(bk, p)
    for k, m in shadows:
        r, p = b[k][m], ps.get(m)
        for d in REJECT_DAYS:
            if f"{d}d" in r["moves"] or t - r["at"] < d * 86400:
                continue
            if p:
                r["moves"][f"{d}d"] = float(p["priceUsd"]) / r["px"] - 1
            elif t - r["at"] > (d + 1) * 86400:
                r["moves"][f"{d}d"] = -1.0  # no pair a day past due: gone
    c["last_mark"] = b["last_mark"] = now()
    save(c, CONTROL)
    save(b)
    write_report(b, su, ps, c, quiet=quiet)


def _liq(p):
    return (p.get("liquidity") or {}).get("usd") or 0


def _second_look(mint):
    """Ask the second sources about a coin the batch call didn't return. ('alive', pair) when
    DexScreener search still has a liquid pair, ('gone', None) when search has none AND RugCheck
    calls it rugged or its pools hold under GONE_LIQ, else ('unknown', None): keep waiting."""
    try:
        found = [q for q in get("https://api.dexscreener.com/latest/dex/search?q=" + mint).get("pairs") or []
                 if q.get("chainId") == "solana" and q["baseToken"].get("address") == mint]
    except Exception:
        return "unknown", None
    live = [q for q in found if _liq(q) >= GONE_LIQ]
    if live:
        return "alive", max(live, key=_liq)
    try:
        r = get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report")
    except Exception:
        return "unknown", None
    pooled = sum((m["lp"].get("quoteUSD") or 0) + (m["lp"].get("baseUSD") or 0)
                 for m in r.get("markets") or [] if m.get("lp"))
    return ("gone", None) if r.get("rugged") or pooled < GONE_LIQ else ("unknown", None)


def _apply_exits(b, ps, su):
    t = clock()
    for mint in list(b["positions"]):
        pos = b["positions"][mint]
        p = ps.get(mint)
        if not p:
            pos.pop("misses", None)  # v1's counter; the rug rule below is time-based
            since = pos.setdefault("missing_since", t)
            if t - since < RUG_MISSING_MIN * 60:
                continue
            if t - since >= RUG_BACKSTOP_H * 3600:
                _sell(b, mint, 1.0, f"no price for {RUG_BACKSTOP_H}h: treated as rugged, marked to zero", None, su)
                continue
            if t - pos.get("second_look", 0) < RUG_RECHECK_MIN * 60:
                continue
            pos["second_look"] = t
            state, p = _second_look(mint)
            if state == "gone":
                _sell(b, mint, 1.0, f"no price for {(t - since) / 60:.0f} min and RugCheck and DexScreener "
                                    "search both show it gone: treated as rugged, marked to zero", None, su)
            if state != "alive":
                continue
        for k in ("misses", "missing_since", "second_look"):
            pos.pop(k, None)
        px = float(p["priceUsd"])
        pos["peak_px"] = max(pos["peak_px"], px)
        r = px / pos["entry_px"] - 1
        liq = _liq(p)
        base = pos.setdefault("entry_liq", liq)  # positions opened before phase 2: first seen liquidity
        m5 = (p.get("priceChange") or {}).get("m5")
        if base and liq <= base * (1 - EVENT_LIQ_DROP):
            _sell(b, mint, 1.0, f"event exit: liquidity down {1 - liq / base:.0%} since entry, {r:+.0%} from entry", p, su)
        elif m5 is not None and float(m5) <= EVENT_M5_DROP:
            _sell(b, mint, 1.0, f"event exit: price {float(m5):+.0f}% in 5 minutes, {r:+.0%} from entry", p, su)
        elif not pos["tp1_done"] and r >= pos["tp1"]:
            pos["tp1_done"] = True
            _sell(b, mint, 0.5, f"take-profit at {r:+.0%}: half sold, cost recovered", p, su)
        elif not pos["tp1_done"] and r <= pos["stop"]:
            _sell(b, mint, 1.0, f"stop-loss at {r:+.0%}", p, su)
        elif pos["tp1_done"] and px <= pos["peak_px"] * 0.6:
            _sell(b, mint, 1.0, f"trailing stop: 40% off peak, {r:+.0%} from entry", p, su)
        elif not pos["tp1_done"] and held_hours(pos) >= TIME_STOP_H and r < TIME_STOP_MIN_GAIN:
            _sell(b, mint, 1.0, f"time stop: {held_hours(pos):.0f}h held, {r:+.0%}, no take-profit", p, su)


def other_arms():
    """Book files beyond claude and control (state mode only)."""
    if not BOOKS:
        return []
    return [os.path.join(BOOKS, f) for f in sorted(os.listdir(BOOKS))
            if f.endswith(".json") and f not in ("claude.json", "control.json")]


_LAST_ORDER_US = 0


def write_order(kind, **fields):
    """Drop an order file in the inbox. The id starts with the UTC time, so a sort is time order.
    Written to a temp name and renamed, so a tick never reads half an order."""
    global _LAST_ORDER_US
    us = max(time.time_ns() // 1000, _LAST_ORDER_US + 1)  # strictly increasing, even within one microsecond
    _LAST_ORDER_US = us
    t = us / 1e6
    oid = (datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%f")
           + f"Z-{kind}-{random.SystemRandom().randrange(16 ** 6):06x}")
    o = {"id": oid, "kind": kind, "at": t, "by": os.environ.get("MEMEPAPER_BY", "local"), **fields}
    tmp = os.path.join(ORDERS, f".{oid}.tmp")
    with open(tmp, "w") as f:
        json.dump(o, f, indent=2)
    os.replace(tmp, os.path.join(ORDERS, oid + ".json"))
    return o


def _apply_one(b, c, o):
    """One order's effect on the books (not yet saved). Returns its result line."""
    kind, age = o.get("kind"), time.time() - float(o.get("at") or 0)
    if kind == "gate":
        _ingest_gate(b, o["results"], float(o["at"]))
        return f"recorded {len(o['results'])} gate results, {sum(1 for r in o['results'].values() if not r['fails'])} passed"
    if kind == "buy":
        if age > ORDER_TTL_MIN * 60:
            return f"refused: order is {age / 60:.0f} min old (limit {ORDER_TTL_MIN})"
        try:
            n = len(c["positions"])
            _buy(b, c, o["mint"], float(o["sol"]), str(o["thesis"]), float(o.get("stop", -0.35)),
                 float(o.get("tp1", 1.0)), regate=True, persist=False)
        except Refused as e:
            return f"refused: {e}"
        pos = b["positions"][o["mint"]]
        _mech_copy(b, o["mint"])
        ctl = "control opened" if len(c["positions"]) > n else "no control"
        return f"bought {pos['symbol']} {pos['cost_sol']:.2f} SOL @ ${pos['entry_px']:.8g}; {ctl}"
    if kind == "sell":
        m, frac = o.get("mint"), float(o.get("fraction", 0))
        if m not in b["positions"]:
            return "refused: not held"
        if not 0 < frac <= 1:
            return f"refused: fraction {frac} not in (0, 1]"
        p = pairs([m]).get(m)
        _extra(round(clock()), k="judgement", mint=m, fraction=frac, reason=str(o.get("reason", "")),
               px=float(p["priceUsd"]) if p else None, gain=float(p["priceUsd"]) / b["positions"][m]["entry_px"] - 1 if p else None)
        _sell(b, m, frac, str(o.get("reason", "")), p, sol_usd())
        return f"sold {frac:.0%} of {m[:6]}"
    return f"refused: unknown kind {kind!r}"


def apply():
    """Apply every pending order, oldest first. An order's id goes into the claude book in the same
    save as its effect, and the file moves to orders/done/ after, so a crash between the two can't
    apply an order twice. Returns how many orders were handled."""
    b, c = load(), load(CONTROL)
    b.setdefault("applied", [])
    seen = {x["id"] for x in b["applied"]}
    n = 0
    for f in sorted(x for x in os.listdir(ORDERS) if x.endswith(".json")):
        path = os.path.join(ORDERS, f)
        try:
            o = json.load(open(path))
            oid = o["id"]
        except Exception as e:
            o, oid = {"id": f[:-5]}, f[:-5]
            o["result"] = f"refused: unreadable ({e.__class__.__name__})"
        else:
            if oid in seen:
                o["result"] = next(x["result"] for x in b["applied"] if x["id"] == oid)
            else:
                o["result"] = _apply_one(b, c, o)
        if oid not in seen:
            b["applied"] = (b["applied"] + [{"id": oid, "kind": o.get("kind"), "result": o["result"], "at": now()}])[-APPLIED_KEEP:]
            seen.add(oid)
            # Claude's book first: it holds the order id. If the process dies before the control
            # save, the order is never re-applied, so at worst a control entry is missing, never doubled.
            save(b)
            save(c, CONTROL)
        o["applied_at"] = now()
        done = os.path.join(ORDERS, "done", f)
        with open(done + ".tmp", "w") as fh:
            json.dump(o, fh, indent=2)
        os.replace(done + ".tmp", done)
        os.remove(path)
        print(f"order {oid}: {o['result']}")
        n += 1
    return n


def _fingerprint():
    """What a tick changed that's worth pushing: trades, orders, rejects scored, trailing peaks."""
    out = []
    for p in [BOOK, CONTROL] + other_arms():
        bk = load(p)
        out.append((len(bk["log"]), len(bk.get("applied", [])), len(bk["closed"]),
                    sum(len(r["moves"]) for k in ("rejects", "passes") for r in bk[k].values()),
                    tuple(sorted((m, x["peak_px"]) for m, x in bk["positions"].items() if x.get("tp1_done")))))
    return out


def tick(quiet=True):
    """State mode's one writer step: apply orders, then mark. Prints `material: yes|no` last, so the
    runner knows whether to push now or wait."""
    if not ORDERS:
        sys.exit("tick needs state mode: set MEMEPAPER_STATE to the state folder")
    before = _fingerprint()
    n = apply()
    mark(quiet=quiet)
    material = n > 0 or _fingerprint() != before
    print(f"material: {'yes' if material else 'no'}")
    return material


def _momentum(r):
    """Claude's entry preference, as a rule: 1h buys > sells, 1h and 24h up, no vertical 5m spike."""
    return r["buys_h1"] > r["sells_h1"] and r["h1"] > 0 and r["h24"] > 0 and r["m5"] < 25


# The mechanical arms. Each is a rule over a dataset row (and, for v-dip, the coin's price a week
# ago) plus which qualifying coin it takes: the highest value of `rank`. Every arm uses the same
# gate, size, costs and exit code; only what's listed here differs. See CLAUDE.md, Arms.
VARIANTS = {
    "v-momentum":   {"rule": lambda r, wk: _momentum(r), "rank": "vol_h24"},
    "v-no-spike":   {"rule": lambda r, wk: _momentum(r) and r["h24"] <= 150, "rank": "vol_h24"},
    "v-mature":     {"rule": lambda r, wk: r["age_h"] >= 72 and r["liq"] >= 150_000, "rank": "liq"},
    "v-tight":      {"rule": lambda r, wk: _momentum(r), "rank": "vol_h24", "stop": -0.20, "tp1": 0.40},
    "v-loose":      {"rule": lambda r, wk: _momentum(r), "rank": "vol_h24", "stop": -0.40, "tp1": 1.50},
    "v-dip":        {"rule": lambda r, wk: wk is not None and r["px"] > wk and -35 <= r["h24"] <= -15
                                           and r["buys_h1"] > r["sells_h1"], "rank": "vol_h24"},
    "v-low-bundle": {"rule": lambda r, wk: _momentum(r) and (r["gate"].get("insider") is not None)
                                           and r["gate"]["insider"] <= 0.05, "rank": "vol_h24"},
    "v-velocity":   {"rule": lambda r, wk: _momentum(r), "rank": "avg_trade"},
    "v-x-organic":  {"rule": lambda r, wk: _momentum(r) and _x_organic(r), "rank": "vol_h24"},
    "v-x-exit":     {"rule": lambda r, wk: _momentum(r) and _x_ok(r), "rank": "vol_h24", "x_exit": True},
    "v-swing":      {"rule": lambda r, wk: _momentum(r) and _read(r, "swing"), "rank": "vol_h24", "swing_stop": True},
    "v-unease":     {"rule": lambda r, wk: _momentum(r) and _read(r, "swing"), "rank": "vol_h24", "unease_exit": True},
    # RugCheck's per-wallet flag read 0 on 8 of 8 live coins while its graph held up to 50%: this
    # prices the difference. No network found counts as clean.
    "v-networks":   {"rule": lambda r, wk: _momentum(r) and ((r.get("gate") or {}).get("networks") or 0) <= MAX_NETWORKS, "rank": "vol_h24"},
    # Every other arm and the control only see coins someone paid to list. This one only sees coins
    # nobody did, under the same gate: it prices that bias.
    "v-unpaid":     {"rule": lambda r, wk: _momentum(r) and not r.get("paid", True), "rank": "vol_h24", "unpaid": True},
}


_CLAMPED = set()  # what's been alerted in this process, so a bad file doesn't alert every cycle


def _clamped(name, raw, alert=True):
    """An arm's numbers, forced inside params/bounds.json. A value out of bounds is clamped and alerted,
    never used; a key the bounds don't list, or that isn't a number, is dropped. No bounds file means
    no overrides at all."""
    if not raw:
        return {}
    bounds = _jload(os.path.join(HERE, "params", "bounds.json"), {})
    out, bad = {}, []
    for k, v in raw.items():
        lim = bounds.get(k)
        if not lim or isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            bad.append(f"{k} dropped")
            continue
        out[k] = min(lim[1], max(lim[0], v))
        if out[k] != v:
            bad.append(f"{k} {v} clamped to {out[k]}")
    if alert and bad and (name, tuple(bad)) not in _CLAMPED:
        _CLAMPED.add((name, tuple(bad)))
        notify("memepaper: param out of bounds", f"{name}: {'; '.join(bad)}", "high", "warning")
    return out


def _registry():
    """Arms the learning run has retired or added (state/params/arms.json)."""
    r = _jload(os.path.join(STATE, "params", "arms.json"), {}) if STATE else {}
    return {"retired": r.get("retired", []), "added": r.get("added", {})}


def arm_cfg(name):
    """An arm's settings. Arms in the code run as written. An arm the learning run added is a code arm
    with new numbers, inside the bounds: a rule is never data, and new numbers are a new arm, so no
    arm's record mixes two sets of rules."""
    if name in VARIANTS:
        return VARIANTS[name]
    add = _registry()["added"][name]
    return {**VARIANTS[add["base"]], **_clamped(name, {k: v for k, v in add.items() if k != "base"})}


def live_arms():
    reg = _registry()
    return {n: arm_cfg(n) for n in [*VARIANTS, *reg["added"]] if n not in reg["retired"]}


def _arm_stop(a, r):
    return min(STOP_RANGE[1], max(STOP_RANGE[0], -SWING_K * r["read"]["swing"])) if a.get("swing_stop") else a.get("stop", -0.35)


def _x_burst(c):
    return bool(c and c["trusted"] and c["kol"] >= X_KOL_BURST and c["kol"] > c["kol_before"])


def _read(r, k):
    return (r.get("read") or {}).get(k)


def _x_ok(r):
    """X data the arms may use: a trusted scout, recent, with this coin in it."""
    return bool(r.get("x") and r["x"]["trusted"])


def _x_organic(r):
    """Posts rising, mostly from small accounts over X_NEW_DAYS old."""
    x = r.get("x") or {}
    return _x_ok(r) and x["posts"] > x["before"] and (x["small_share"] or 0) >= 0.5


def _passed(r, unpaid=False):
    """A row an arm may buy: in the universe with a clean gate result from the last GATE_TTL_H."""
    g = r.get("gate")
    return bool(r["eligible"] and (unpaid or r.get("paid", True)) and g and not g["fails"] and r["t"] - g["at"] < GATE_TTL_H * 3600)


def view(bk, t):
    """All pick() needs to know about a book. Saved in the dataset, so a day can be replayed exactly."""
    cut = t - ARM_COOLDOWN_H * 3600
    recent = [x["mint"] for x in bk["closed"] if _ts(x["closed"]) >= cut]
    return {"cash": round(bk["cash_sol"], 9), "held": sorted(bk["positions"]), "recent": sorted(set(recent))}


def pick(name, rows, v, week=None, a=None):
    """The row this arm buys this cycle, or None. Pure: same inputs, same answer, live or replayed."""
    arm_ = a or arm_cfg(name)
    if v["cash"] <= ARM_CASH_FLOOR or len(v["held"]) >= arm_.get("max_open", MAX_OPEN):
        return None
    ok = [r for r in rows if _passed(r, arm_.get("unpaid")) and r["mint"] not in v["held"] and r["mint"] not in v["recent"]
          and r["age_h"] >= arm_.get("min_age_h", 0) and r["liq"] >= arm_.get("min_liq", 0) and r["h24"] <= arm_.get("max_h24", math.inf)
          and arm_["rule"](r, (week or {}).get(r["mint"]))]
    return max(ok, key=lambda r: (r[arm_["rank"]], r["mint"])) if ok else None


def _ts(s):
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M UTC").replace(tzinfo=datetime.timezone.utc).timestamp()


def candidates():
    """Solana mints ending in `pump` from DexScreener's profile and boost lists, as in CLAUDE.md.
    Boosts are paid ads: a candidate list only. One list failing is fine; both failing isn't."""
    out, errs = [], []
    for u in ("https://api.dexscreener.com/token-profiles/latest/v1",
              "https://api.dexscreener.com/token-boosts/top/v1"):
        try:
            out += [x["tokenAddress"] for x in get(u) or []
                    if x.get("chainId") == "solana" and str(x.get("tokenAddress", "")).endswith("pump")]
        except Exception as e:
            errs.append(e)
    if len(errs) == 2:
        raise errs[0]
    return list(dict.fromkeys(out))


def _jload(path, default):
    return json.load(open(path)) if os.path.exists(path) else default


def _jsave(path, x):
    with open(path + ".tmp", "w") as f:
        json.dump(x, f)
    os.replace(path + ".tmp", path)


def make_row(mint, p, gate_, t):
    """One dataset row. Keeps the gate result as it was then: RugCheck's flags change over time."""
    tx, vol, pc = p.get("txns") or {}, p.get("volume") or {}, p.get("priceChange") or {}
    h1, h24, m5, h6 = tx.get("h1") or {}, tx.get("h24") or {}, tx.get("m5") or {}, tx.get("h6") or {}
    lq, info = p.get("liquidity") or {}, p.get("info") or {}
    trades = (h24.get("buys") or 0) + (h24.get("sells") or 0)
    age = (t * 1000 - (p.get("pairCreatedAt") or t * 1000)) / 3.6e6
    return {"t": t, "mint": mint, "symbol": p["baseToken"].get("symbol"), "px": float(p["priceUsd"]),
            "liq": _liq(p), "mc": p.get("marketCap") or 0, "dex": p.get("dexId"), "age_h": round(age, 2),
            "vol_h1": vol.get("h1") or 0, "vol_h24": vol.get("h24") or 0,
            "buys_h1": h1.get("buys") or 0, "sells_h1": h1.get("sells") or 0,
            "buys_h24": h24.get("buys") or 0, "sells_h24": h24.get("sells") or 0, "trades_h24": trades,
            "avg_trade": round((vol.get("h24") or 0) / trades, 2) if trades else 0,
            "m5": pc.get("m5") or 0, "h1": pc.get("h1") or 0, "h6": pc.get("h6") or 0, "h24": pc.get("h24") or 0,
            "eligible": age >= UNIVERSE_MIN_AGE_H and _liq(p) >= UNIVERSE_MIN_LIQ, "gate": gate_, "arms": [], "x": None,
            # Raw from here on: null means the source didn't say, which is not the same as 0.
            "v": SCHEMA, "pool": p.get("pairAddress"), "m5_raw": pc.get("m5"), "buys_m5": m5.get("buys"), "sells_m5": m5.get("sells"),
            "buys_h6": h6.get("buys"), "sells_h6": h6.get("sells"), "vol_m5": vol.get("m5"), "vol_h6": vol.get("h6"),
            "liq_base": lq.get("base"), "liq_quote": lq.get("quote"), "fdv": p.get("fdv"), "boosts": (p.get("boosts") or {}).get("active"),
            "links": sorted({x.get("type") or x.get("platform") or "?" for x in info.get("socials") or []}
                            | ({"website"} if info.get("websites") else set())) if info else None}


def snapshot(t):
    """Price the watch list, gate what's due (longest wait first, inside CYCLE_BUDGET_S) and return
    (rows, pairs, new gate results). Rows cover every coin that has ever qualified, so one that
    collapses stays in the data: a dataset of only the living would flatter every rule."""
    wp, gp = os.path.join(STATE, "watch.json"), os.path.join(STATE, "gate.json")
    watch, cache = _jload(wp, {}), _jload(gp, {})
    for m in candidates():
        watch.setdefault(m, {"ok": False}).update(t=t, paid=True)
    for m in _jload(os.path.join(STATE, "gt.json"), {}).get("free", []) + feed_grads(t):  # unpaid: only v-unpaid may trade them
        watch.setdefault(m, {"ok": False, "paid": False})["t"] = t
    for m in held_coins():  # everything held is read, however it got there
        watch.setdefault(m, {}).update(ok=True, t=t)
    live = [(m, w) for m, w in watch.items() if t - w["t"] < (WATCH_DAYS * 86400 if w["ok"] else WATCH_FRESH_H * 3600)]
    watch = dict(sorted(live, key=lambda x: (not x[1]["ok"], not x[1]["ok"] and not x[1].get("paid", True), -x[1]["t"]))[:WATCH_MAX])
    ps, rows = pairs(list(watch)), {}
    for m, w in watch.items():
        p = ps.get(m)
        if p and p.get("priceUsd") and p.get("dexId"):  # DexScreener lists some pairs with no price yet
            r = make_row(m, p, None, t)
            r["paid"] = w.get("paid", True)
            if r["eligible"]:
                w.update(ok=True, t=t)
            if w["ok"]:
                rows[m] = r
    due = [m for m, r in rows.items() if r["eligible"]
           and t - cache.get(m, {}).get("tried", 0) >= GATE_REFRESH_MIN * 60]
    due.sort(key=lambda m: (not rows[m]["paid"], cache.get(m, {}).get("tried", 0)))
    results, end, stuck = {}, clock() + CYCLE_BUDGET_S, 0
    for m in due:
        if clock() >= end or stuck >= GATE_STOP_AFTER:
            break
        info = {}
        fails = gate_one(m, ps[m], info)
        if any(f.startswith(CANT_CHECK) for f in fails):
            cache.setdefault(m, {"at": 0, "fails": fails})["tried"] = t
            stuck += 1
            continue
        _extra(t, k="gate", mint=m, **info.pop("detail", {}), orders=_orders(m))
        cache[m] = {"at": t, "tried": t, "fails": fails, **info, **_gate_moves(cache.get(m), info, t)}
        if rows[m]["paid"]:  # unpaid coins stay out of the books' pass lists and the control's pool
            results[m] = {"symbol": rows[m]["symbol"], "px": rows[m]["px"], "fails": fails}
    cache = {m: g for m, g in cache.items() if t - g["tried"] < 2 * 86400}
    for m, r in rows.items():
        r["gate"] = cache.get(m)
    gone = [m for m, w in watch.items() if w["ok"] and m not in rows]
    if gone:  # a coin that vanishes is the most important row of all: say so instead of going silent
        _extra(t, k="gone", mints=gone)
    _jsave(wp, watch)
    _jsave(gp, cache)
    return list(rows.values()), ps, results


def _gate_moves(old, new, t):
    """What the big wallets did since the coin's last reading. The hourly holder lists are in the side
    stream, but only a number on the row reaches the autopsy. A first reading has nothing to compare."""
    old = old or {}
    out = {f"{k}_chg": round(new[k] - old[k], 6) for k in ("top10", "creator", "insider")
           if new.get(k) is not None and old.get(k) is not None}
    if new.get("holders") and old.get("holders"):
        out["holders_chg"] = round(new["holders"] / old["holders"] - 1, 4)
    if out:
        out["chg_h"] = round((t - old["at"]) / 3600, 2)
    return out


def _data_path(t):
    os.makedirs(os.path.join(STATE, "data"), exist_ok=True)
    day = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")
    return os.path.join(STATE, "data", day + ".jsonl")


def read_day(day):
    """A day's dataset lines, from the plain file or its gzipped copy."""
    return _lines(os.path.join(STATE, "data", day + ".jsonl"))[0]


def _lines(base):
    """(parsed lines, how many were unreadable) from a dataset file or its gzipped copy. A crash
    mid-write leaves one torn line; that loses the line, not the day."""
    if os.path.exists(base):
        raw = list(open(base))
    elif os.path.exists(base + ".gz"):
        with gzip.open(base + ".gz", "rt") as f:
            raw = list(f)
    else:
        return [], 0
    good = []
    for x in raw:
        try:
            good.append(json.loads(x))
        except ValueError:
            pass
    return good, len(raw) - len(good)


def week_ago(t):
    """Each coin's price about 7 days before t (first row of that day), for v-dip. Empty until the
    dataset is a week old, so v-dip can't trade before then."""
    day = datetime.datetime.fromtimestamp(t - 7 * 86400, datetime.timezone.utc).strftime("%Y-%m-%d")
    out = {}
    for x in read_day(day):
        if "mint" in x:
            out.setdefault(x["mint"], x["px"])
    return out


def _roll_data(path):
    """Gzip finished days. Today's file stays plain text: git stores appends as small deltas, while
    a gzip file would be stored whole on every push."""
    for f in glob.glob(os.path.join(os.path.dirname(path), "*.jsonl")):
        if f != path:
            with open(f, "rb") as src, gzip.open(f + ".gz", "wb") as dst:
                dst.write(src.read())
            os.remove(f)


def _desk(url, raw=False):
    """Read the private desk. The token reaches curl on stdin, so it's never in a process list or log."""
    kind = "raw+json" if raw else "json"
    cfg = (f'header = "Authorization: Bearer {os.environ["DESK_TOKEN"]}"\n'
           f'header = "Accept: application/vnd.github.{kind}"\n')
    out = subprocess.run(["curl", "-sf", "-m", "20", "-A", "memepaper/1.0", "-K", "-", url],
                         input=cfg, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _utc(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()


def _post_ts(n):
    """An X post's number carries the time it was posted."""
    return ((n >> 22) + 1288834974657) / 1000


def _whole(x):
    return x is None or (type(x) is int and x >= 0)


_X_URL = re.compile(r"^https://(?:x|twitter)\.com/(\w{1,15})/status/(\d{15,20})$")
_X_POST = {"url", "handle", "followers", "account_age_days", "posted_at", "matched", "first_words"}
_X_POST2 = _X_POST | {"text", "kind", "likes", "reposts"}  # scout v2


def _check_post(p, run, where, v2=False):
    if not isinstance(p, dict) or set(p) != (_X_POST2 if v2 else _X_POST):
        return [f"{where}: wrong fields"]
    if v2 and (not isinstance(p["text"], str) or p["kind"] not in ("original", "reply", "quote", "repost")
               or not _whole(p["likes"]) or not _whole(p["reposts"])):
        return [f"{where}: bad text, kind, likes or reposts"]
    m = _X_URL.match(str(p["url"]))
    if not m:
        return [f"{where}: bad link"]
    bad = []
    if m[1].lower() != str(p["handle"]).lower():
        bad.append(f"{where}: handle isn't the one in the link")
    if not _whole(p["followers"]) or not _whole(p["account_age_days"]):
        bad.append(f"{where}: followers and account age must be whole numbers or null")
    if p["matched"] not in ("mint", "ticker") or not isinstance(p["first_words"], str) or len(p["first_words"]) > 60:
        bad.append(f"{where}: bad matched or first_words")
    try:
        at = _utc(p["posted_at"])
    except (TypeError, ValueError):
        return bad + [f"{where}: bad time"]
    if abs(_post_ts(int(m[2])) - at) > SCOUT_TIME_SLACK_S:
        bad.append(f"{where}: the link's number disagrees with the stated time, so it wasn't copied from X")
    if not run - 4 * 3600 - SCOUT_TIME_SLACK_S <= at <= run + SCOUT_TIME_SLACK_S:
        bad.append(f"{where}: outside the 4-hour window")
    return bad


def scout_check(d):
    """Everything wrong with a scout file's shape, as a list. Empty means it's the fixed shape."""
    if not isinstance(d, dict) or set(d) != {"scout", "run_at", "watchlist_at", "window_hours", "coins", "errors"}:
        return ["top-level fields are wrong"]
    try:
        run = _utc(d["run_at"])
    except (TypeError, ValueError):
        return ["bad run_at"]
    if d["scout"] not in ("v1", "v2") or d["window_hours"] != 4:
        return ["scout must be v1 or v2 and window_hours 4"]
    v2 = d["scout"] == "v2"
    if not isinstance(d["coins"], list) or len(d["coins"]) > SCOUT_MAX_COINS or not isinstance(d["errors"], list):
        return [f"coins must be a list of at most {SCOUT_MAX_COINS}, errors a list"]
    if not d["coins"] and not (len(d["errors"]) == 1 and d["errors"][0] in ("cannot read", "incomplete", "empty")):
        return ["no coins needs exactly one failure reason"]
    bad, seen = [], set()
    for c in d["coins"]:
        if not isinstance(c, dict) or set(c) != {"mint", "symbol", "status", "posts", *(["searches"] if v2 else [])} or not isinstance(c["posts"], list):
            bad.append("coin fields are wrong")
            continue
        if v2 and not (isinstance(c["searches"], list) and c["searches"] and all(
                isinstance(q, dict) and set(q) == {"query", "results"} and isinstance(q["query"], str) and type(q["results"]) is int
                for q in c["searches"])):
            bad.append(f"{str(c['symbol'])[:12]}: searches must list each query and its result count")
        where = str(c["symbol"])[:12]
        if c["status"] not in ("ok", "none", "failed") or (c["status"] == "ok") != bool(c["posts"]):
            bad.append(f"{where}: status doesn't fit its posts")
        if len(c["posts"]) > SCOUT_MAX_POSTS:
            bad.append(f"{where}: over {SCOUT_MAX_POSTS} posts")
        for i, p in enumerate(c["posts"], 1):
            bad += _check_post(p, run, f"{where} post {i}", v2)
            if isinstance(p, dict):
                if (c["mint"], str(p.get("url"))) in seen:
                    bad.append(f"{where} post {i}: repeated")
                seen.add((c["mint"], str(p.get("url"))))
    return bad


def _on_topic(c, r):
    """Does this X post really mention the coin? Common tickers are common words ($GATO is "gato",
    Spanish for cat), so the post must hold the mint, in its text or a link, or the exact cashtag."""
    text = (r.get("text") or "") + " ".join(u.get("expanded_url") or "" for u in (r.get("entities") or {}).get("urls") or [])
    return c["mint"] in text or re.search(rf"\${re.escape(str(c['symbol']))}\b", text, re.I) is not None


def scout_verify(pairs):
    """Look up a random sample of (coin, post) on X's public embed data: does each post exist, by
    that account, saying that, about that coin? A retweet comes back as the original, so it's
    compared with the account it quotes. Returns (found, not found, contradicted). Follower counts
    aren't in that data."""
    found, missing, wrong = 0, 0, 0
    for c, p in random.sample(pairs, min(SCOUT_SAMPLE, len(pairs))):
        n = _X_URL.match(p["url"])[2]
        try:
            r = get(f"https://cdn.syndication.twimg.com/tweet-result?id={n}&token=a")
        except Exception:
            missing += 1
            continue
        who = ((r or {}).get("user") or {}).get("screen_name")
        rt = re.match(r"RT @(\w+): ?(.*)", p["first_words"], re.S)
        author, words = (rt[1], rt[2]) if rt else (p["handle"], p["first_words"])
        if not who:
            missing += 1
        elif who.lower() == author.lower() and norm(words)[:20] in norm(r.get("text")) and _on_topic(c, r):
            found += 1
        else:
            wrong += 1
    return found, missing, wrong


def _x_metrics(posts, before):
    """The counts the arms and the report use. Scout only copies; every number here is ours."""
    known = [p for p in posts if p["followers"] is not None and p["account_age_days"] is not None]
    dated = [p for p in posts if p["account_age_days"] is not None]
    small = [p for p in known if p["followers"] < X_SMALL_FOLLOWERS and p["account_age_days"] >= X_NEW_DAYS]
    kol = {p["handle"].lower() for p in posts if (p["followers"] or 0) >= X_KOL_FOLLOWERS}
    words = [norm(p["first_words"])[:40] for p in posts]
    times = [_utc(p["posted_at"]) for p in posts]
    before = before or {"posts": len(posts), "kol": len(kol)}  # no earlier run: nothing has risen
    return {"posts": len(posts), "before": before["posts"], "accounts": len({p["handle"].lower() for p in posts}),
            "new_share": round(sum(p["account_age_days"] < X_NEW_DAYS for p in dated) / len(dated), 3) if dated else None,
            "small_share": round(len(small) / len(known), 3) if known else None,
            "kol": len(kol), "kol_before": before["kol"], "repeats": len(words) - len(set(words)),
            "retweets": sum(p["first_words"].startswith("RT @") for p in posts),
            "span_min": round((max(times) - min(times)) / 60) if times else None,
            "engagement": sum(p["likes"] + p["reposts"] for p in posts) if posts and "likes" in posts[0] else None,
            "originals": sum(p["kind"] == "original" for p in posts) if posts and "kind" in posts[0] else None}


def scout_update(t):
    """Fetch the newest scout file if there's a new one, judge it and keep only numbers. Returns the
    metrics by mint with `trusted` set, for the rows. A failure here only leaves the X arms idle."""
    path = os.path.join(STATE, "scout.json")
    s = _jload(path, {"file": None, "run_ts": 0, "clean": 0, "verdict": "no file yet", "coins": {}})
    was = s["clean"] >= SCOUT_TRUST_RUNS
    if not os.environ.get("DESK_TOKEN"):
        s["verdict"] = "not connected: no DESK_TOKEN"
    else:
        try:
            names = [e["name"] for e in _desk(DESK_SCOUT) if e["name"].endswith(".json")]
            new = max(names, default=None)
            if new and new != s["file"]:
                s["file"] = new
                _judge(s, _desk(f"{DESK_SCOUT}/{urllib.parse.quote(new)}", raw=True))
        except Exception as e:  # the folder not existing yet is an error too; nothing changes
            s["last_error"] = f"{now()} {e.__class__.__name__}"
    fresh = t - s["run_ts"] < SCOUT_MAX_AGE_H * 3600
    trusted = s["clean"] >= SCOUT_TRUST_RUNS
    if trusted != was:
        notify("memepaper: X scout " + ("trusted, X arms on" if trusted else "not trusted, X arms off"), s["verdict"], "default", "mag")
    _jsave(path, s)
    return {m: {**x, "trusted": trusted and fresh} for m, x in s["coins"].items()} if fresh else {}


def _judge(s, d):
    """Update the scout state `s` with a new file: the verdict, the clean count and the metrics."""
    bad = scout_check(d)
    if bad:
        s.update(clean=0, verdict="rejected: " + bad[0])
        return
    posts = [(c, p) for c in d["coins"] for p in c["posts"]]
    before = s["coins"]
    s.update(run_ts=_utc(d["run_at"]), coins={c["mint"]: _x_metrics(c["posts"], before.get(c["mint"]))
                                              for c in d["coins"] if c["status"] != "failed"})
    if not posts:  # a quiet run or a failure file proves nothing either way
        s["verdict"] = "no posts: " + ", ".join(d["errors"]) if d["errors"] else "no posts"
        return
    found, missing, wrong = scout_verify(posts)
    if wrong or found < missing:
        s.update(clean=0, verdict=f"not verified: {found} posts found on X, {missing} not found, {wrong} contradicted")
    else:
        s["clean"] += 1
        s["verdict"] = f"clean: {found} posts found on X, {missing} not found"


def write_watchlist(rows, t):
    """What Scout searches: coins held in any book, then gate passes by 24h volume. The file is
    public, so Scout needs no token, and symbols are cut to letters and digits."""
    coins = {m: x["symbol"] for p in [BOOK, CONTROL] + other_arms() for m, x in load(p)["positions"].items()}
    for r in sorted((r for r in rows if _passed(r)), key=lambda r: -r["vol_h24"]):
        coins.setdefault(r["mint"], r["symbol"])
    d = os.path.join(STATE, "grok")
    os.makedirs(d, exist_ok=True)
    at = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [f"{m} {''.join(ch for ch in str(y) if ch.isalnum())[:12] or 'UNKNOWN'}" for m, y in list(coins.items())[:SCOUT_MAX_COINS]]
    with open(os.path.join(d, "watchlist.txt"), "w") as f:
        f.write("\n".join([f"WATCHLIST {at}", *lines, "END"]) + "\n")
    live = sorted((r for r in rows if r["eligible"]), key=lambda r: r["h1"])
    moved = {r["mint"]: r for r in live[-5:] + live[:5]}.values()  # what Grok's story routine explains
    with open(os.path.join(d, "movers.txt"), "w") as f:
        f.write("\n".join([f"MOVERS {at}", *[f"{r['mint']} {''.join(ch for ch in str(r['symbol']) if ch.isalnum())[:12] or 'UNKNOWN'} {r['h1']:+.0f}%"
                                             for r in moved], "END"]) + "\n")


# The reading layer (phase 3b). Raw facts go to the dataset exactly as sources gave them; every
# score below is worked out from them, so a better formula later can be re-run over old days.
def _day(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")


def _extra(t, **line):
    """One line in the side stream: data/extra/<day>.jsonl. Everything that isn't a coin's row."""
    if not STATE:
        return
    d = os.path.join(STATE, "data", "extra")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, _day(t) + ".jsonl")
    with open(path, "a") as f:
        f.write(json.dumps({"t": t, **line}) + "\n")
    _roll_data(path)


def read_extra(day, kind=None):
    xs = _lines(os.path.join(STATE, "data", "extra", day + ".jsonl"))[0]
    return [x for x in xs if kind is None or x.get("k") == kind]


def held_coins():
    return {m: x for p in [BOOK, CONTROL] + other_arms() for m, x in load(p)["positions"].items()}


def _orders(mint):
    """What was paid for on this coin and when (boosts, profiles). None if the call failed."""
    try:
        return get(f"https://api.dexscreener.com/orders/v1/solana/{mint}")
    except Exception:
        return None


def _mech_copy(b, mint):
    """Factor 49: mech.json holds every Claude buy to the mechanical exits only, so Claude's
    judgement sells can be priced against simply not making them. Never traded by hand."""
    path = os.path.join(BOOKS, "mech.json")
    new = [mint] if os.path.exists(path) else [k for k, x in b["positions"].items() if x.get("v") == 2]
    m = load(path)
    for k in new:  # the first copy takes in what's already open, so the comparison starts whole
        m["positions"][k] = copy.deepcopy(b["positions"][k])
        m["cash_sol"] -= b["positions"][k]["cost_sol"]
    save(m, path)


def _gt_targets(rows, t):
    """Tell gt_work what to fetch, most useful first: 0 Claude's holdings, 1 any book's, 2 gate
    passes, 3 the rest of the universe, 4 everything else recorded."""
    path = os.path.join(STATE, "gt.json")
    s = _jload(path, {})
    mine, held, was = load()["positions"], held_coins(), s.get("coins", {})
    coins = {}
    for r in rows:
        if r.get("pool"):
            m = r["mint"]
            tier = 0 if m in mine else 1 if m in held else 2 if _passed(r) else 3 if r["eligible"] else 4
            coins[m] = {**was.get(m, {}), "pool": r["pool"], "tier": tier}
    s.update(coins=coins, flow_due=sorted(coins, key=lambda m: coins[m]["tier"]))
    _jsave(path, s)


def _gt_jobs(s, t):
    """The calls worth making now, in order, longest-waiting first within each group. Falling behind
    on the universe loses nothing: a fetch returns 50 hours of candles and only new ones are kept."""
    every, coins = CYCLE_MIN * 60, s.get("coins", {})

    def due(job, tiers, gap):
        ms = [m for m, c in coins.items() if c["tier"] in tiers and t - c.get(job + "_at", 0) >= gap]
        return [(job, m) for m in sorted(ms, key=lambda m: coins[m].get(job + "_at", 0))]
    return ([("trending", None)] if t - s.get("trending_at", 0) >= every else []) + ([("flow", None)] if s.get("flow_due") else []) \
        + due("c15", (0,), every) + due("c5", (0,), every) + due("trades", (0,), every) \
        + due("c15", (1, 2), every) + due("c5", (1,), every) + due("c15", (3, 4), 4 * every)


class GtRefused(Exception):
    pass


class FeedRefused(Exception):
    pass


def _gt(path):
    """GeckoTerminal, which needs a version header. Unlike get(), this tells a refusal (back off)
    from a pool it doesn't know (skip that coin): curl -f reports both the same way."""
    p = subprocess.run(["curl", "-s", "-m", "20", "-A", "memepaper/1.0", "-H", "Accept: application/json;version=20230302",
                        "-w", "\n%{http_code}", GT + path], capture_output=True, text=True, check=True)
    body, code = p.stdout.rsplit("\n", 1)
    if code == "429":
        raise GtRefused()
    if code != "200":
        raise ValueError(f"geckoterminal {code}")
    return json.loads(body)


def _gt_job(s, job, m, t):
    if job == "trending":
        pools = _gt("/trending_pools?duration=1h").get("data") or []
        mints = [x["relationships"]["base_token"]["data"]["id"].split("_", 1)[1] for x in pools]
        s.update(free=[x for x in mints if x.endswith("pump")], trending_at=t)
        _extra(t, k="trending", mints=mints)
    elif job == "flow":
        take, s["flow_due"] = s["flow_due"][:GT_CHUNK], s["flow_due"][GT_CHUNK:]
        by_pool = {s["coins"][x]["pool"]: x for x in take if x in s["coins"]}
        out = {}
        for x in _gt("/pools/multi/" + ",".join(by_pool)).get("data") or []:
            a = x["attributes"]
            out[by_pool.get(a["address"], a["address"])] = {
                "tx": a.get("transactions"), "vol": a.get("volume_usd"), "chg": a.get("price_change_percentage"),
                "reserve": a.get("reserve_in_usd"), "locked": a.get("locked_liquidity_percentage")}
        _extra(t, k="flow", coins=out)
    elif job in ("c15", "c5"):
        c, mins = s["coins"][m], 15 if job == "c15" else 5
        n = GT_FIRST_CANDLES if job + "_ts" not in c and c.get("tier", 4) <= 3 else 200
        got = _gt(f"/pools/{c['pool']}/ohlcv/minute?aggregate={mins}&limit={n}&include_empty_intervals=true")
        new = [x for x in sorted(got["data"]["attributes"]["ohlcv_list"])
               if x[0] > c.get(job + "_ts", 0) and x[0] + mins * 60 <= t]  # closed candles only
        if new:
            _extra(t, k="candles", mint=m, tf=mins, rows=new)
            c[job + "_ts"] = new[-1][0]
        c[job + "_at"] = t
    else:
        c = s["coins"][m]
        got = sorted((x["attributes"] for x in _gt(f"/pools/{c['pool']}/trades").get("data") or []), key=lambda a: a["block_timestamp"])
        new = [[a["block_timestamp"], a["kind"], round(float(a.get("volume_in_usd") or 0), 2), a.get("tx_from_address")]
               for a in got if a["block_timestamp"] > c.get("trades_ts", "")]
        if new:
            _extra(t, k="trades", mint=m, rows=new)
            c["trades_ts"] = new[-1][0]
        c["trades_at"] = t


def gt_work(t):
    """A few GeckoTerminal calls each minute, so candles never slow the exits. A refusal backs off
    and the count is kept: the true limit from this host is something to measure, not assume."""
    path = os.path.join(STATE, "gt.json")
    s = _jload(path, {})
    if t < s.get("blocked_until", 0):
        return 0
    n, jobs = 0, _gt_jobs(s, t)
    for i, (job, m) in enumerate(jobs[:GT_PER_TICK]):
        if i:
            time.sleep(GT_GAP_S)
        try:
            _gt_job(s, job, m, t)
            n += 1
            s["calls"] = s.get("calls", 0) + 1
        except GtRefused:
            s.update(refused=s.get("refused", 0) + 1, blocked_until=t + GT_BACKOFF_S)
            break
        except Exception:  # one bad coin goes to the back of the queue instead of blocking it
            s["failed"] = s.get("failed", 0) + 1
            (s["coins"].get(m, {}) if m else s)[job + "_at"] = t
    s["behind"] = max(0, len(jobs) - n)
    _jsave(path, s)
    return n


def _ws_open():
    """A websocket to the launch stream, by hand: the script stays stdlib-only."""
    ca = "/etc/ssl/cert.pem"  # the python.org build on the Mac has no CA bundle; Linux's default works
    ctx = ssl.create_default_context(cafile=ca if os.path.exists(ca) else None)
    s = ctx.wrap_socket(socket.create_connection((PP_HOST, 443), 15), server_hostname=PP_HOST)
    s.settimeout(FEED_QUIET_S)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall(f"GET {PP_PATH} HTTP/1.1\r\nHost: {PP_HOST}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
              f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nUser-Agent: memepaper/1.0\r\n\r\n".encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        c = s.recv(4096)
        if not c:
            raise ConnectionError("closed during the handshake")
        buf += c
    head, rest = buf.split(b"\r\n\r\n", 1)
    if head.split()[1:2] != [b"101"]:
        s.close()
        raise FeedRefused(head[:80].decode("latin-1"))
    return s, rest


def _ws_send(s, data, op=1):
    mask, n = os.urandom(4), len(data)
    head = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n))
    s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


def _ws_frames(buf):
    """The whole frames at the front of buf, as ([(opcode, payload)], what's left over)."""
    out = []
    while len(buf) >= 2:
        n, i = buf[1] & 127, 2
        if n >= 126:
            i = 4 if n == 126 else 10
            if len(buf) < i:
                break
            n = struct.unpack(">H" if n == 126 else ">Q", buf[2:i])[0]
        if n > FEED_MAX_FRAME:
            raise ConnectionError(f"frame of {n} bytes")
        if len(buf) < i + n:
            break
        out.append((buf[0] & 15, buf[i:i + n]))
        buf = buf[i + n:]
    return out, buf


def _feed_path():
    return os.environ.get("MEMEPAPER_FEED") or None


def _feed_db(path):
    db = sqlite3.connect(path, timeout=10)
    db.execute("PRAGMA journal_mode=WAL")  # the loop reads while this writes
    db.execute("CREATE TABLE IF NOT EXISTS launches (mint TEXT PRIMARY KEY, t INTEGER, creator TEXT, first_buy_sol REAL, mc_sol REAL, symbol TEXT)")
    db.execute("CREATE INDEX IF NOT EXISTS launches_creator ON launches (creator)")
    db.execute("CREATE INDEX IF NOT EXISTS launches_t ON launches (t)")
    db.execute("CREATE TABLE IF NOT EXISTS grads (mint TEXT PRIMARY KEY, t INTEGER, pool TEXT)")
    db.execute("CREATE INDEX IF NOT EXISTS grads_t ON grads (t)")
    return db


def _feed_store(db, x, t):
    """One event from the stream. Its text is data: bound as parameters and cut short, never run."""
    mint, kind = x.get("mint"), x.get("txType")
    num = lambda k: x[k] if type(x.get(k)) in (int, float) else None
    if not isinstance(mint, str) or not 32 <= len(mint) <= 64:
        return False
    with db:
        if kind == "create" and isinstance(x.get("traderPublicKey"), str):
            db.execute("INSERT OR IGNORE INTO launches VALUES (?,?,?,?,?,?)",
                       (mint, t, x["traderPublicKey"][:64], num("solAmount"), num("marketCapSol"), str(x.get("symbol"))[:32]))
        elif kind == "migrate":
            db.execute("INSERT OR IGNORE INTO grads VALUES (?,?,?)", (mint, t, str(x.get("pool"))[:32]))
        else:
            return False
    return True


def _feed_session(db, end=None):
    """One connection, until it drops or `end`."""
    s, buf = _ws_open()
    try:
        for m in ("subscribeNewToken", "subscribeMigration"):
            _ws_send(s, json.dumps({"method": m}).encode())
        while end is None or clock() < end:
            frames, buf = _ws_frames(buf)
            for op, d in frames:
                if op == 9:
                    _ws_send(s, d, 10)
                elif op == 8:
                    raise ConnectionError("the server closed the stream")
                elif op == 1:
                    try:
                        x = json.loads(d)
                    except ValueError:
                        continue
                    if isinstance(x, dict):
                        _feed_store(db, x, round(clock()))
            c = s.recv(65536)
            if not c:
                raise ConnectionError("the stream ended")
            buf += c
    finally:
        s.close()


def feed(seconds=None):
    """Keep the launch stream in a local file for good. One connection only: PumpPortal bans more."""
    path = _feed_path()
    if not path:
        sys.exit("feed needs MEMEPAPER_FEED: a sqlite file outside the state folder")
    if STATE and os.path.abspath(path).startswith(os.path.abspath(STATE) + os.sep):
        sys.exit("feed: that file is inside the state folder, and the loop would commit it")
    lock = open(path + ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("feed: one is already connected, and a second could get this address banned")
    db, wait = _feed_db(path), FEED_RETRY_S[0]
    end = clock() + seconds if seconds else None
    while end is None or clock() < end:
        t0 = clock()
        try:
            _feed_session(db, end)
            nap = 0
        except FeedRefused as e:
            print(f"feed refused, waiting {FEED_BAN_S // 60} min: {e}")
            nap = FEED_BAN_S
        except OSError as e:
            wait = FEED_RETRY_S[0] if clock() - t0 >= FEED_STEADY_S else min(wait * 2, FEED_RETRY_S[1])
            print(f"feed dropped, retrying in {wait}s: {e.__class__.__name__}: {str(e)[:200]}")
            nap = wait
        time.sleep(nap)


def _feed_ro():
    p = _feed_path()
    return sqlite3.connect(f"file:{urllib.parse.quote(p)}?mode=ro", uri=True, timeout=5) if p and os.path.exists(p) else None


def feed_read(mints, t):
    """What the stream knows about these coins, counting only what had happened by t. The creator's
    counts start when the feed did, so a 0 in its first weeks means none seen, not none."""
    out, db = {}, None
    try:
        db = _feed_ro()
        for m in mints if db else ():
            x = db.execute("SELECT creator, first_buy_sol FROM launches WHERE mint=?", (m,)).fetchone()
            if x:
                n, g = db.execute("SELECT COUNT(*), COUNT(g.mint) FROM launches l LEFT JOIN grads g ON g.mint=l.mint AND g.t<=? "
                                  "WHERE l.creator=? AND l.mint<>? AND l.t<=?", (t, x[0], m, t)).fetchone()
                out[m] = {"creator": x[0], "first_buy_sol": x[1], "launches": n, "grads": g}
    except sqlite3.Error as e:  # a bad read costs these columns, never the snapshot
        print(f"feed read failed: {str(e)[:200]}")
    finally:
        if db:
            db.close()
    return out


def feed_grads(t):
    """Graduates just reaching the universe's age: found by the stream, not by anyone paying for a
    listing. About 1,300 graduate a day and most die at once, so waiting for that age keeps them from
    flooding WATCH_MAX before they could ever qualify. Their early candles come with the first fetch."""
    db = None
    try:
        db = _feed_ro()
        return [x[0] for x in db.execute("SELECT mint FROM grads WHERE t>? AND t<=?", (t - (UNIVERSE_MIN_AGE_H + FEED_GRAD_H) * 3600, t - UNIVERSE_MIN_AGE_H * 3600))] if db else []
    except sqlite3.Error as e:
        print(f"feed read failed: {str(e)[:200]}")
        return []
    finally:
        if db:
            db.close()


def feed_watch(t):
    """Say so once when the stream goes quiet, so the columns don't just stop without a word."""
    if not _feed_path():
        return
    path = os.path.join(STATE, "feed.json")
    s, db = _jload(path, {}), _feed_ro()
    try:
        last, day = db.execute("SELECT MAX(t), SUM(t>?) FROM launches", (t - 86400,)).fetchone() if db else (None, 0)
        grads = db.execute("SELECT COUNT(*) FROM grads WHERE t>?", (t - 86400,)).fetchone()[0] if db else 0
    finally:
        if db:
            db.close()
    quiet = not last or t - last > FEED_STALE_MIN * 60
    if quiet != s.get("quiet", False):
        notify("memepaper: launch feed " + ("quiet" if quiet else "back"), f"last launch recorded {t - (last or t):.0f}s ago", "default", "warning" if quiet else "ok")
    _jsave(path, {"quiet": quiet, "last": last, "launches": day or 0, "grads": grads})


def _jup(q):
    key = os.environ.get("JUP_API_KEY")
    url = (JUP_KEYED if key else JUP) + "?" + urllib.parse.urlencode(q)
    p = subprocess.run(["curl", "-sf", "-m", "8", "-A", "memepaper/1.0"] + (["-H", f"x-api-key: {key}"] if key else []) + [url],
                       capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def _paper_trip(p, su):
    """What a paper round trip of MAX_POS_SOL charges right now, as a share of the stake."""
    mev = SANDWICH_USD / su
    back = (MAX_POS_SOL * (1 - FEE) - mev) / (1 + impact(MAX_POS_SOL, p, su))
    return (back * (1 - FEE) * (1 - impact(back, p, su)) - mev) / MAX_POS_SOL - 1


def quotes(t, rows, ps, su):
    """Ask Jupiter what buying and selling straight back would really return, beside what the paper
    fills charge. It leaves out priority fees and sandwiches, so it flatters the real trip a little:
    if the paper trip is still kinder than this, the book's results are too good. No fill reads it."""
    held = held_coins()
    coins = sorted((r for r in rows if r["mint"] in ps and (r["mint"] in held or _passed(r, True))),
                   key=lambda r: (r["mint"] not in held, -r["vol_h24"], r["mint"]))
    stake, fails = round(MAX_POS_SOL * 1e9), 0
    for r in coins[:JUP_COINS if os.environ.get("JUP_API_KEY") else JUP_COINS_KEYLESS]:
        try:
            a = _jup({"inputMint": SOL_MINT, "outputMint": r["mint"], "amount": stake, "slippageBps": JUP_BPS})
            b = _jup({"inputMint": r["mint"], "outputMint": SOL_MINT, "amount": a["outAmount"], "slippageBps": JUP_BPS})
            _extra(t, k="quote", mint=r["mint"], liq=r["liq"], real=round(int(b["outAmount"]) / stake - 1, 5), paper=round(_paper_trip(ps[r["mint"]], su), 5),
                   impact=float(a.get("priceImpactPct") or 0), route=[(x.get("swapInfo") or {}).get("label") for x in a.get("routePlan") or []])
        except Exception as e:
            fails += 1
            print(f"quote failed: {e.__class__.__name__}: {str(e)[:120]}")
            if fails >= JUP_STOP_AFTER:
                break


def market(t, rows):
    """The room's mood, once a cycle; slower-moving things hourly. Each source fails alone."""
    path = os.path.join(STATE, "market.json")
    s = _jload(path, {})
    up = [r["h24"] > 0 for r in rows if r["eligible"]]
    line = {"coins": len(up), "up_share": round(sum(up) / len(up), 3) if up else None}
    try:
        p = pairs([SOL_MINT]).get(SOL_MINT) or {}
        line.update(sol_usd=float(p["priceUsd"]) if p.get("priceUsd") else None, sol_h24=(p.get("priceChange") or {}).get("h24"))
    except Exception:
        pass
    if t - s.get("hourly_at", 0) >= 3600:
        s["hourly_at"] = t
        try:
            line["fear_greed"] = int(get("https://api.alternative.me/fng/?limit=1")["data"][0]["value"])
        except Exception:
            pass
        try:
            line["themes"] = _themes()
        except Exception:
            pass
        try:
            line["takeovers"] = [x["tokenAddress"] for x in get("https://api.dexscreener.com/community-takeovers/latest/v1") or []
                                 if x.get("chainId") == "solana"]
        except Exception:
            pass
    _extra(t, k="market", **line)
    _jsave(path, s)


def _themes():
    """DexScreener's themes are cross-chain, so each one's Solana share is worked out from its pairs."""
    out, end = [], clock() + 20
    for x in get("https://api.dexscreener.com/metas/trending/v1") or []:
        y = {k: x.get(k) for k in ("slug", "volume", "marketCap", "tokenCount", "marketCapChange")}
        if clock() < end:
            try:
                ps = [q for q in get(f"https://api.dexscreener.com/metas/meta/v1/{x['slug']}").get("pairs") or [] if q.get("chainId") == "solana"]
                y.update(sol_pairs=len(ps), sol_vol=sum((q.get("volume") or {}).get("h24") or 0 for q in ps),
                         sol_mints=[q["baseToken"]["address"] for q in ps[:20]])
            except Exception:
                pass
        out.append(y)
    return out


def _recent(t, days=2):
    """Candles and rows by coin from the last few days, oldest first."""
    candles, rows = {}, {}
    for i in range(days, -1, -1):
        day = _day(t - i * 86400)
        for x in read_extra(day, "candles"):
            if x["tf"] == 15:
                candles.setdefault(x["mint"], []).extend(x["rows"])
        for x in read_day(day):
            if "mint" in x:
                rows.setdefault(x["mint"], []).append(x)
    return candles, rows


def read_all(rows, t):
    """Every coin's reading this cycle, kept in reads.json for the report and the briefing."""
    candles, hist = _recent(t, 1)
    out = {}
    for r in rows:
        x = read_coin(candles.get(r["mint"], []), hist.get(r["mint"], []) + [r])
        if x:
            out[r["mint"]] = x
    _jsave(os.path.join(STATE, "reads.json"), out)
    return out


def _sell_share(r):
    n = (r.get("buys_h1") or 0) + (r.get("sells_h1") or 0)
    return r["sells_h1"] / n if n else None


def _trade_size(r):
    n = (r.get("buys_h1") or 0) + (r.get("sells_h1") or 0)
    return r["vol_h1"] / n if n and r.get("vol_h1") else None


def _worse(rows, f, higher):
    """Is the last hour's f on the bad side of this coin's own normal? None until there's a normal."""
    last, old = [f(r) for r in rows[-4:]], [f(r) for r in rows[:-4]]
    last, old = [x for x in last if x is not None], [x for x in old if x is not None]
    if len(old) < 12 or not last:
        return None
    return median(last) > median(old) * 1.25 if higher else median(last) < median(old) * 0.75


def read_coin(c, rows=()):
    """How a coin looks against its own history. `c` is 15-minute candles [t, o, h, l, close, volume],
    `rows` its dataset rows, both oldest first. Pure, so it can be re-run over any past day.

    swing: its normal 15-minute range, as a share of price. paid: the average price paid since this
    run began (its low before the peak), weighted by volume: above it most recent buyers are winning,
    below it most are losing. unease: how many of five warning signs are on, out of `known`."""
    bars = sorted({x[0]: x for x in c if x[4] > 0}.values())[-READ_WINDOW:]  # a candle fetched twice counts once
    traded = [x for x in bars if x[5] > 0]
    if len(traded) < READ_MIN_CANDLES:
        return None
    swing = median([(x[2] - x[3]) / x[4] for x in traded])
    top = max(range(len(bars)), key=lambda i: bars[i][2])
    run = bars[min(range(top + 1), key=lambda i: bars[i][3]):]
    vol, close = sum(x[5] for x in run), bars[-1][4]
    paid = sum((x[2] + x[3] + x[4]) / 3 * x[5] for x in run) / vol if vol else close
    recent, before = max(x[2] for x in bars[-4:]), max(x[2] for x in bars[-12:-4])
    rows = list(rows)
    quote = [r["liq_quote"] for r in rows[-8:] if r.get("liq_quote")]
    signs = {"under_paid": close < paid, "failed_high": recent < before and close < recent,
             "sellers": _worse(rows, _sell_share, True), "smaller_trades": _worse(rows, _trade_size, False),
             "sol_leaving": quote[-1] < 0.9 * max(quote) if len(quote) >= 4 else None}
    known = [v for v in signs.values() if v is not None]
    return {"swing": round(swing, 4), "paid": paid, "vs_paid": round(close / paid - 1, 4), "off_peak": round(close / bars[top][2] - 1, 4),
            "accel": round((close / bars[-5][4] - 1) - (bars[-5][4] / bars[-9][4] - 1), 4), "candles": len(bars),
            "unease": sum(known), "known": len(known), "signs": sorted(k for k, v in signs.items() if v)}


def _case_key(x):
    return f"{x['book']}:{x['mint']}:{x['closed']}"


def casebook(t, ps):
    """Every closed trade in every book becomes a case, and 24 hours later we note what the coin did
    after we left. That second number is the one that teaches: was the exit right?"""
    path = os.path.join(STATE, "cases.jsonl")
    old = _lines(path)[0]
    seen = {_case_key(x) for x in old if "book" in x}
    after = {x["after"] for x in old if "after" in x}
    lines = []
    for p in [BOOK, CONTROL] + other_arms():
        book = os.path.basename(p)[:-5]
        for x in load(p)["closed"]:
            c = {"book": book, "mint": x["mint"], "symbol": x["symbol"], "opened": x["opened"], "closed": x["closed"],
                 "pnl_pct": round(x["pnl_pct"], 4), "peak": round(x["peak_px"] / x["entry_px"] - 1, 4), "exit": x["exit_reason"],
                 "thesis": x["thesis"], "entry": x.get("at_entry"), "reentry": x.get("reentry"), "since_loss_h": x.get("since_loss_h"),
                 "exit_px": x.get("exit_px")}
            if x.get("v") == 2 and _case_key(c) not in seen:
                lines.append(c)
    for x in old:
        if "book" in x and _case_key(x) not in after and t - _ts(x["closed"]) >= 86400 and x["mint"] in ps:
            px = float(ps[x["mint"]]["priceUsd"])
            lines.append({"after": _case_key(x), "h": 24, "px": px, "vs_exit": round(px / x["exit_px"] - 1, 4) if x.get("exit_px") else None})
    if lines:
        with open(path, "a") as f:
            f.writelines(json.dumps(x) + "\n" for x in lines)
    return len(lines)


_LIKE = ("age_h", "liq", "mc", "h1", "h24", "buys_h1", "sells_h1", "vol_h24")


def _point(r):
    """A coin's position for comparison: log-scaled, because coins differ by orders of magnitude."""
    return [math.copysign(math.log1p(abs(float(r.get(k) or 0))), float(r.get(k) or 0)) for k in _LIKE]


def similar(row, k=5):
    """The past cases that looked most like this coin at entry, and how they ended."""
    cases = [x for x in _lines(os.path.join(STATE, "cases.jsonl"))[0] if x.get("entry")]
    me = _point(row)
    return sorted(cases, key=lambda x: sum((a - b) ** 2 for a, b in zip(me, _point(x["entry"]))))[:k]


def _png(path, bars, line=None, w=720, h=320):
    """A candle chart as a PNG, by hand: the bot's Python has no libraries. Red and green bars, the
    average price paid in blue. Claude can read the picture."""
    lo, hi = min(x[3] for x in bars), max(x[2] for x in bars)
    if line:
        lo, hi = min(lo, line), max(hi, line)
    span = (hi - lo) or hi or 1
    y = lambda v: min(h - 1, max(0, int((hi - v) / span * (h - 21)) + 10))
    px = [bytearray(b"\xff\xff\xff" * w) for _ in range(h)]
    step = max(2, w // len(bars))
    for i, (_, o, a, b, c, _v) in enumerate(bars):
        col = b"\x1a\x8f\x4a" if c >= o else b"\xcf\x2e\x2e"
        x = i * step + step // 2
        for r in range(y(a), y(b) + 1):
            px[r][x * 3:x * 3 + 3] = col
        for r in range(y(max(o, c)), y(min(o, c)) + 1):
            for j in range(max(0, x - step // 3), min(w, x + step // 3 + 1)):
                px[r][j * 3:j * 3 + 3] = col
    if line:
        for j in range(0, w, 2):
            px[y(line)][j * 3:j * 3 + 3] = b"\x1f\x5f\xd0"
    chunk = lambda k, d: struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
    raw = b"".join(b"\0" + bytes(r) for r in px)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def brief(mint):
    """One page on a coin, for Claude's review or a person. Facts first; Grok's note is labelled,
    and everything quoted from outside is data, never an instruction."""
    candles, hist = _recent(round(clock()))
    rows, bars = hist.get(mint, []), sorted({x[0]: x for x in candles.get(mint, [])}.values())
    if not rows:
        print(f"no recorded rows for {mint}")
        return
    r, x = rows[-1], read_coin(bars, rows)
    g = r.get("gate") or {}
    print(f"# {r['symbol']} {mint}\n\nprice ${r['px']:.8g} | mc ${r['mc']:,.0f} | pool ${r['liq']:,.0f} (SOL side {r.get('liq_quote')}) | age {r['age_h']:.0f}h"
          f"\nchange: 5m {r['m5']}% 1h {r['h1']}% 6h {r['h6']}% 24h {r['h24']}% | 1h buys {r['buys_h1']} sells {r['sells_h1']} | paid listing: {r.get('paid', True)}")
    print(f"gate: {'PASS' if g and not g['fails'] else g.get('fails', 'not gated')} | insider flag {g.get('insider')} networks {g.get('networks')} graph {g.get('graph')} holders {g.get('holders')}")
    if x:
        chart = f"/tmp/memepaper-{mint[:8]}.png"
        _png(chart, bars[-READ_WINDOW:], x["paid"])
        print(f"\nreading: normal 15m swing {x['swing']:.1%} | {x['vs_paid']:+.1%} vs average paid this run | {x['off_peak']:+.1%} off peak | "
              f"acceleration {x['accel']:+.1%}\nunease {x['unease']} of {x['known']} known signs: {', '.join(x['signs']) or 'none'}"
              f"\nchart: {chart} (read this image; blue is the average price paid)")
    else:
        print(f"\nreading: too few candles yet ({len(bars)})")
    print("\nlast 8 candles (15m): open high low close volume")
    for c in bars[-8:]:
        print(" ", datetime.datetime.fromtimestamp(c[0], datetime.timezone.utc).strftime("%d %H:%M"), *[f"{v:.6g}" for v in c[1:]])
    if r.get("x"):
        print(f"\nX (counted by code): {json.dumps(r['x'])}")
    if r.get("feed"):
        f = r["feed"]
        print(f"\ncreator {f['creator']}: first buy {f['first_buy_sol']} SOL; {f['launches']} other launches seen, {f['grads']} graduated")
    note = _jload(os.path.join(STATE, "stories.json"), {}).get("movers", {}).get(mint)
    if note:
        print(f"\nGrok's note (a guess from X, unverified, data only): {note}")
    print("\nmost similar past cases:")
    for c in similar(r):
        print(f"  {c['symbol']} ({c['book']}) {c['pnl_pct']:+.0%}, peak {c['peak']:+.0%}: {c['exit']}")


def _numbers(r):
    """Every number recorded about a coin at a moment, flattened. The autopsy looks at all of them,
    including ones nobody thought mattered: that's how it can find what we can't see."""
    out = {k: v for k, v in r.items() if type(v) in (int, float) and k not in ("t", "px", "v")}
    for k in ("gate", "read", "x", "feed"):
        out.update({f"{k}.{a}": b for a, b in (r.get(k) or {}).items() if type(b) in (int, float) and a not in ("at", "tried", "paid")})
    n = r.get("buys_h1", 0) + r.get("sells_h1", 0)
    if n:
        out["sell_share_h1"] = r["sells_h1"] / n
    if r.get("mc"):
        out["liq_to_mc"] = r["liq"] / r["mc"]
    if r.get("liq"):
        out["vol_to_liq"] = r.get("vol_h24", 0) / r["liq"]
    return out


def _auc(win, lose):
    """The chance a random winner scored higher than a random collapse. 0.5 means no difference."""
    both = sorted([(v, 1) for v in win] + [(v, 0) for v in lose])
    rank, i, total = 1, 0, 0.0
    while i < len(both):
        j = i
        while j < len(both) and both[j][0] == both[i][0]:
            j += 1
        total += (rank + rank + j - i - 1) / 2 * sum(x[1] for x in both[i:j])
        rank += j - i
        i = j
    return (total - len(win) * (len(win) + 1) / 2) / (len(win) * len(lose))


def _label(path):
    """"win", "lose" or None from a coin's prices [(t, price)] over the next AUTOPSY_HOURS: did it
    double before it lost a third, or did it halve?"""
    px = path[0][1]
    if not px:
        return None
    for _, p in path[1:]:
        if p / px - 1 >= AUTOPSY_WIN:
            return "win"
        if p / px - 1 <= -0.35:
            break
    return "lose" if min(p for _, p in path) / px - 1 <= AUTOPSY_LOSS else None


def _leads(a_side, b_side, a_name, b_name):
    """Every recorded number compared between two groups of (time, numbers), as report text."""
    if min(len(a_side), len(b_side)) < AUTOPSY_MIN:
        return f"\nToo few to read: {AUTOPSY_MIN} of each are needed.\n"
    cut, res = median([x[0] for x in a_side + b_side]), []
    for k in sorted({k for _, n in a_side + b_side for k in n}):
        def vals(side, early=None):
            return [n[k] for at, n in side if n.get(k) is not None and (early is None or (at < cut) == early)]
        a, b, halves = vals(a_side), vals(b_side), [(vals(a_side, e), vals(b_side, e)) for e in (True, False)]
        if min(len(a), len(b)) >= AUTOPSY_MIN and min(len(x) for h in halves for x in h) >= 5:
            res.append((abs(_auc(a, b) - 0.5), k, _auc(a, b), _auc(*halves[0]), _auc(*halves[1]), median(a), median(b)))
    steady = [x for x in sorted(res, reverse=True) if (x[3] - 0.5) * (x[4] - 0.5) > 0]
    return (f"\n{len(res)} numbers compared; {len(steady)} point the same way in both halves. Chance alone would give about half.\n"
            f"0.50 means no difference. These are leads to test, not rules.\n\n| Number | Score | Each half | {a_name} median | {b_name} median |\n|---|---|---|---|---|\n"
            + "\n".join(f"| {k} | {auc:.2f} | {s1:.2f} / {s2:.2f} | {ma:.4g} | {mb:.4g} |" for _, k, auc, s1, s2, ma, mb in steady[:15]) + "\n")


def autopsy(t, days=AUTOPSY_DAYS):
    """What separated the coins that doubled from the coins that halved, one sample per coin per day,
    then the coins that crashed from the rest. Everything recorded is compared, so most results here will be luck: a number only counts if it
    points the same way in both halves of the period. Written to autopsy.md."""
    paths, samples, gone = {}, {}, {}
    for i in range(days, -1, -1):
        day = _day(t - i * 86400)
        for x in read_day(day):
            if "mint" in x:  # the path keeps every row: a coin that stops qualifying is the collapse we're after
                paths.setdefault(x["mint"], []).append((x["t"], x["px"]))
                if x.get("eligible"):
                    samples.setdefault((x["mint"], day), (x["t"], _numbers(x)))
        for x in read_extra(day, "gone"):
            for m in x["mints"]:
                gone.setdefault(m, []).append(x["t"])
    for m, times in gone.items():  # gone and never back is a zero; a coin that returned wasn't
        after = [g for g in times if m in paths and g > paths[m][-1][0]]
        if after:
            paths[m].append((min(after), 0.0))
    win, lose, crash, safe = [], [], [], []
    for (m, _d), (at, nums) in samples.items():
        path = [p for p in paths[m] if at <= p[0] <= at + AUTOPSY_HOURS * 3600]
        if len(path) <= 8 or at + AUTOPSY_HOURS * 3600 > t or not path[0][1]:
            continue
        kind = _label(path)
        if kind:
            (win if kind == "win" else lose).append((at, nums))
        (crash if min(p for _, p in path) / path[0][1] - 1 <= AUTOPSY_CRASH else safe).append((at, nums))
    out = f"# Autopsy\n\nLast {days} days: {len(win)} coins doubled, {len(lose)} halved, within {AUTOPSY_HOURS}h of being sampled.\n"
    out += _leads(win, lose, "Winners'", "Collapses'")
    out += (f"\n## Danger check\n\nThe same comparison for the coins to stay away from: {len(crash)} fell {-AUTOPSY_CRASH:.0%} or more "
            f"within {AUTOPSY_HOURS}h of being sampled, {len(safe)} did not.\n" + _leads(crash, safe, "Crashes'", "Others'"))
    os.makedirs(os.path.join(STATE, "grok"), exist_ok=True)
    for f in ("autopsy.md", os.path.join("grok", "autopsy.md")):  # the second is for Grok's weekly second opinion
        with open(os.path.join(STATE, f), "w") as fh:
            fh.write(out)
    return out


def datacheck(day):
    """How complete a day of the dataset is."""
    lines, bad = _lines(os.path.join(STATE, "data", day + ".jsonl"))
    extra, bad2 = _lines(os.path.join(STATE, "data", "extra", day + ".jsonl"))
    cycles = [x["cycle"] for x in lines if "cycle" in x]
    rows = [x for x in lines if "mint" in x]
    kinds = {}
    for x in extra:
        kinds[x.get("k")] = kinds.get(x.get("k"), 0) + 1
    null = {k: round(sum(r.get(k) is None for r in rows) / len(rows), 3) for k in ("liq_quote", "buys_m5", "pool", "links")} if rows else {}
    return {"day": day, "cycles": len(cycles), "biggest_gap_min": round(max([(b - a) / 60 for a, b in zip(cycles, cycles[1:])], default=0)),
            "rows": len(rows), "coins": len({r["mint"] for r in rows}), "unpaid_rows": sum(1 for r in rows if not r.get("paid", True)),
            "torn_lines": bad + bad2, "null_share": null, "extra": kinds}


def _fingerprints():
    """Finished days never change. Record each one's hash once, and report any that later differs."""
    d = os.path.join(STATE, "data")
    path = os.path.join(d, "MANIFEST.json")
    known, damaged = _jload(path, {}), []
    for f in sorted(glob.glob(os.path.join(d, "*.gz")) + glob.glob(os.path.join(d, "extra", "*.gz"))):
        k = os.path.relpath(f, d)
        with gzip.open(f, "rb") as z:  # the contents: gzip stamps a time into the wrapper
            h = hashlib.sha256(z.read()).hexdigest()
        if known.setdefault(k, h) != h:
            damaged.append(k)
    damaged += [k for k in known if not os.path.exists(os.path.join(d, k))]
    _jsave(path, known)
    return damaged


def _insider_tally():
    """Settles the report's open question: does RugCheck's per-wallet flag fire when its own graph
    finds insiders? If not, the gate's 15% test is reading nothing and the review should know."""
    g = list(_jload(os.path.join(STATE, "gate.json"), {}).values())
    found = [x for x in g if x.get("graph")]
    return {"gated": len(g), "graph_found": len(found), "flag_fired": sum(1 for x in found if x.get("flagged")),
            "creator_null": sum(1 for x in g if "creator_raw" in x and x["creator_raw"] is None)}


def daily(t):
    """Once a day: check yesterday, fingerprint finished days, run the autopsy, and say so if the
    dataset has a hole. A dataset that fails silently teaches the wrong lessons."""
    path = os.path.join(STATE, "daily.json")
    s = _jload(path, {})
    if s.get("day") == _day(t):
        return False
    first, check, damaged = "day" not in s, datacheck(_day(t - 86400)), _fingerprints()  # the first day is partial
    size = sum(os.path.getsize(os.path.join(a, f)) for a, _, fs in os.walk(os.path.join(STATE, "data")) for f in fs) / 1e6
    problems = [f"damaged or missing: {', '.join(damaged[:5])}"] if damaged else []
    if not first and check["cycles"] < DATA_MIN_CYCLES:
        problems.append(f"{check['day']} has {check['cycles']} of 96 snapshots, biggest gap {check['biggest_gap_min']} min")
    if check["torn_lines"]:
        problems.append(f"{check['torn_lines']} torn lines on {check['day']}")
    if size > DATA_MAX_MB:
        problems.append(f"dataset is {size:.0f} MB: move old days out of the repo")
    q = read_extra(_day(t - 86400), "quote")
    s.update(day=_day(t), check=check, size_mb=round(size, 1), problems=problems, insiders=_insider_tally(),
             fills={"n": len(q), "real": median([x["real"] for x in q]), "paper": median([x["paper"] for x in q])})
    _jsave(path, s)
    if problems:
        notify("memepaper: dataset problem", "; ".join(problems), "high", "warning")
    autopsy(t)
    return True


def _desk_latest(url, last):
    """The newest JSON file in a desk folder, if it's new: (name, contents), else (last, None).
    A folder Grok hasn't written to yet is simply nothing new."""
    try:
        new = max((e["name"] for e in _desk(url) if e["name"].endswith(".json")), default=None)
        return (new, _desk(f"{url}/{urllib.parse.quote(new)}", raw=True)) if new and new != last else (last, None)
    except Exception:
        return last, None


def _short(x):
    return re.sub(r"\s+", " ", str(x))[:STORY_MAX_CHARS]


def story_update(t):
    """Grok's notes on why coins move, and its weekly second opinion. Kept for people and for
    Claude's briefing, cut short and labelled as data. No arm, gate or exit ever reads them."""
    if not os.environ.get("DESK_TOKEN"):
        return
    path = os.path.join(STATE, "stories.json")
    s = _jload(path, {"file": None, "opinion_file": None, "movers": {}, "themes": [], "opinion": []})
    s["file"], d = _desk_latest(DESK_STORIES, s["file"])
    if isinstance(d, dict) and d.get("stories") == "v1":
        s["movers"] = {str(x.get("mint")): _short(x.get("why")) for x in d.get("movers") or [] if isinstance(x, dict)}
        s["themes"] = [{"name": _short(x.get("name"))[:60], "why": _short(x.get("why")), "mints": [str(m) for m in x.get("mints") or []][:20]}
                       for x in d.get("themes") or [] if isinstance(x, dict)][:20]
        _extra(t, k="story", movers=s["movers"], themes=s["themes"])
    s["opinion_file"], d = _desk_latest(DESK_OPINION, s["opinion_file"])
    if isinstance(d, dict) and d.get("opinion") == "v1":
        s["opinion"] = [_short(x) for x in d.get("points") or []][:10]
        _extra(t, k="opinion", points=s["opinion"])
    _jsave(path, s)


def _read_md(b):
    """The report's section on coin readings and the dataset's condition."""
    reads = _jload(os.path.join(STATE, "reads.json"), {})
    rows = [f"| {x['symbol']} | {reads[m]['swing']:.1%} | {reads[m]['vs_paid']:+.0%} | {reads[m]['off_peak']:+.0%} | {reads[m]['unease']} of {reads[m]['known']} | "
            f"{-x['stop'] / reads[m]['swing']:.1f} |" for m, x in b["positions"].items() if m in reads and reads[m]["swing"]]
    d, g = _jload(os.path.join(STATE, "daily.json"), {}), _jload(os.path.join(STATE, "gt.json"), {})
    fd, q, out = _jload(os.path.join(STATE, "feed.json"), {}), d.get("fills") or {}, ""
    if rows:
        out += ("\n## Reading the coins\n\nEach coin against its own normal. Information only: no rule on this book reads it.\n\n"
                "| Coin | Normal 15m swing | vs average paid | Off peak | Unease | Stop, in swings |\n|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n")
    if d or g:
        c, i = d.get("check") or {}, d.get("insiders") or {}
        out += (f"\n## Dataset\n\nLast check {c.get('day', 'none yet')}: {c.get('cycles', '?')} of 96 snapshots, {c.get('rows', '?')} rows, {c.get('coins', '?')} coins, {d.get('size_mb', '?')} MB. "
                f"{'; '.join(d.get('problems') or []) or 'No problems.'}\n\nGeckoTerminal: {g.get('calls', 0)} calls, {g.get('refused', 0)} refused, {g.get('failed', 0)} failed, {g.get('behind', 0)} waiting. "
                f"Insider flag fired on {i.get('flag_fired', '?')} of {i.get('graph_found', '?')} coins where RugCheck's graph found insiders.\n")
        if q.get("n"):
            out += f"\nFills: a round trip on Jupiter returned {q['real']:+.1%} (median of {q['n']} quotes, before priority fees); paper charged {q['paper']:+.1%}.\n"
        if fd:
            out += f"\nLaunch feed: {'QUIET' if fd.get('quiet') else 'running'}, {fd.get('launches', 0)} launches and {fd.get('grads', 0)} graduations in the last day.\n"
    ln = _jload(os.path.join(STATE, "learn.json"), {})
    if ln:
        out += f"\nLearning run {ln.get('day')}: {ln.get('summary')} Detail: LEARNING.md on `state`. No rule on this book reads it.\n"
    return out


def cycle():
    """Every CYCLE_MIN: snapshot the universe, record gate results, read the X scout, let each arm
    sell on X signals and buy at most one coin, append it all to the dataset. Returns the coins recorded."""
    t = round(clock())
    rows, ps, results = snapshot(t)
    if results:
        b = load()
        _ingest_gate(b, results, t)
        save(b)
    x = scout_update(t)
    reads, fed = read_all(rows, t), feed_read([r["mint"] for r in rows], t)
    for r in rows:
        r["x"], r["read"], r["feed"] = x.get(r["mint"]), reads.get(r["mint"]), fed.get(r["mint"])
    week, su, views = week_ago(t), sol_usd(), {}
    for name, a in live_arms().items():
        path = os.path.join(BOOKS, name + ".json")
        bk = load(path)
        for m in list(bk["positions"]) if a.get("x_exit") else []:
            if m in ps and _x_burst(x.get(m)):
                _sell(bk, m, 1.0, "x exit: large accounts piling in", ps[m], su)
        for m in list(bk["positions"]) if a.get("unease_exit") else []:
            if m in ps and (reads.get(m) or {}).get("unease", 0) >= UNEASE_EXIT:
                _sell(bk, m, 1.0, f"unease exit: {reads[m]['unease']} of 5 signs", ps[m], su)
        v = views[name] = view(bk, t)
        r = pick(name, rows, v, week, a)
        if r:
            _open(bk, r["mint"], a.get("sol", MAX_POS_SOL), f"{name} rule", _arm_stop(a, r), a.get("tp1", 1.0), ps[r["mint"]], su)
            r["arms"].append(name)
        save(bk, path)
    write_watchlist(rows, t)
    _gt_targets(rows, t)
    path = _data_path(t)
    with open(path, "a") as f:
        f.write(json.dumps({"cycle": t, "v": SCHEMA, "code": os.environ.get("GITHUB_SHA", "local")[:7], "views": views, "week": {r["mint"]: week[r["mint"]] for r in rows if r["mint"] in week}}) + "\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")
    _roll_data(path)
    for job in (lambda: market(t, rows), lambda: casebook(t, ps), lambda: postmortem(t), lambda: story_update(t), lambda: quotes(t, rows, ps, su),
                lambda: feed_watch(t), lambda: daily(t), lambda: learn(t)):
        try:  # none of these may cost the snapshot that's already safely written
            job()
        except Exception as e:
            print(f"cycle extra failed: {e.__class__.__name__}: {str(e)[:200]}")
    return len(rows)


def replay(day):
    """Re-run every arm's pick over a recorded day and compare with what the arm did live. Entries
    only: exits run every 60 s and the dataset is 15-minute rows. Returns the differences."""
    diffs, n, cycles, known = [], 0, [], VARIANTS.keys() | _registry()["added"].keys()
    for x in read_day(day):
        if "cycle" in x:
            cycles.append((x, []))
        else:
            cycles[-1][1].append(x)
    for x, rows in cycles:
        for name in known & x["views"].keys():  # arms added later have no history here
            n += 1
            r = pick(name, rows, x["views"][name], x["week"])
            live = [y["mint"] for y in rows if name in y["arms"]]
            if (r["mint"] if r else None) != (live[0] if live else None):
                diffs.append(f"{x['cycle']} {name}: replay {r['mint'] if r else None}, live {live}")
    print(f"replayed {n} arm decisions on {day}: {len(diffs)} differences")
    for d in diffs:
        print(" ", d)
    return diffs


def label(c, vs_exit=None):
    """Why a closed trade ended as it did: (label, reason). Mechanical, from the fixed list; anything
    it can't place is `other`, with the exit reason kept so a person can look."""
    e, pnl, peak, entry = c["exit"].lower(), c["pnl_pct"], c["peak"], c.get("entry") or {}
    if "rugged" in e or pnl <= -0.9:
        return "rug", c["exit"][:80]
    if "liquidity down" in e:
        return "liquidity-pulled", c["exit"][:80]
    if pnl > 0:
        return ("won-trailed" if "trailing" in e else "won-held"), f"{pnl:+.0%}, peak {peak:+.0%}"
    if "stop-loss" in e and vs_exit is not None and vs_exit >= STOP_RECOVERED:
        return "stop-too-tight", f"stopped at {pnl:+.0%}, then {vs_exit:+.0%} from the exit in a day"
    if peak < SPIKE_PEAK and ((entry.get("h24") or 0) >= SPIKE_H24 or (entry.get("m5") or 0) >= SPIKE_M5):
        return "bought-spike", f"up {entry.get('h24') or 0:.0f}% in 24h at entry, peak {peak:+.0%}"
    if (_ts(c["closed"]) - _ts(c["opened"])) / 3600 >= BLEED_H:
        return "slow-bleed", f"{pnl:+.0%} over {(_ts(c['closed']) - _ts(c['opened'])) / 3600:.0f}h"
    return "other", c["exit"][:80]


def _lesson(f):
    os.makedirs(os.path.join(STATE, "lessons"), exist_ok=True)
    return os.path.join(STATE, "lessons", f)


def postmortem(t):
    """Label every closed trade a day after it closes, in any book, and rewrite the lessons when
    there's something new. Returns how many were labelled."""
    cases = _lines(os.path.join(STATE, "cases.jsonl"))[0]
    path = _lesson("postmortems.jsonl")
    done = {x["key"] for x in _lines(path)[0]}
    after = {x["after"]: x for x in cases if "after" in x}
    lines = []
    for c in cases:
        k = _case_key(c) if "book" in c else None
        if k is None or k in done or (k not in after and t - _ts(c["closed"]) < LABEL_WAIT_H * 3600):
            continue
        lab, why = label(c, after.get(k, {}).get("vs_exit"))
        lines.append({"key": k, "book": c["book"], "symbol": c["symbol"], "mint": c["mint"], "closed": c["closed"], "label": lab,
                      "why": why, "pnl_pct": c["pnl_pct"], "at": t})
    if lines:
        with open(path, "a") as f:
            f.writelines(json.dumps(x) + "\n" for x in lines)
        write_lessons()
    return len(lines)


# What each repeated loss suggests testing: a change to the leading arm's numbers, inside the bounds.
LESSON_TESTS = {
    "stop-too-tight": ("widen the stop by 5 points", lambda a: {"stop": a.get("stop", -0.35) - 0.05}),
    "bought-spike": ("skip coins already up a lot in 24h", lambda a: {"max_h24": a.get("max_h24", 400) * 0.75}),
    "slow-bleed": ("take profit sooner", lambda a: {"tp1": a.get("tp1", 1.0) * 0.75}),
    "liquidity-pulled": ("ask for a deeper pool", lambda a: {"min_liq": a.get("min_liq", UNIVERSE_MIN_LIQ) * 1.5}),
    "rug": ("ask for an older coin", lambda a: {"min_age_h": a.get("min_age_h", UNIVERSE_MIN_AGE_H) * 2}),
}


def lesson_ideas():
    """Loss labels seen LESSON_REPEAT times or more, commonest first."""
    n = {}
    for x in _lines(_lesson("postmortems.jsonl"))[0]:
        n[x["label"]] = n.get(x["label"], 0) + 1
    return [k for k, v in sorted(n.items(), key=lambda kv: (-kv[1], kv[0])) if k in LESSON_TESTS and v >= LESSON_REPEAT]


def write_lessons():
    """LESSONS.md: the top patterns with counts and examples, small enough to read before a decision."""
    by = {}
    for x in _lines(_lesson("postmortems.jsonl"))[0]:
        by.setdefault(x["label"], []).append(x)
    out = ["# Lessons", "", f"{sum(map(len, by.values()))} closed trades labelled, every book. Written by the bot.", ""]
    for k, xs in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        ex = "; ".join(f"{x['symbol']} ({x['book']}): {x['why']}" for x in xs[-2:])
        out.append(f"- **{k}**: {len(xs)} trades, mean {statistics.fmean(x['pnl_pct'] for x in xs):+.0%}. {ex}")
    ideas = lesson_ideas()
    if ideas:
        out += ["", "To test: " + "; ".join(f"{k}: {LESSON_TESTS[k][0]}" for k in ideas) + "."]
    text = "\n".join(out) + "\n"
    with open(os.path.join(STATE, "LESSONS.md"), "w") as f:
        f.write(text.encode()[:LESSONS_MAX].decode(errors="ignore"))


def trial(t, name, kind, params, why, **res):
    """One line in the trial registry, never deleted. The number of things tried is what deflates the
    results, so a variant counts here whether or not it ever went live."""
    with open(os.path.join(STATE, "trials.jsonl"), "a") as f:
        f.write(json.dumps({"t": t, "name": name, "kind": kind, "params": params, "why": why, **res}) + "\n")


def _arm_numbers(a):
    return {k: a[k] for k in PARAM_KEYS if k in a}


def _trials():
    return _lines(os.path.join(STATE, "trials.jsonl"))[0]


def trials_sync(t):
    """Every live arm, with the numbers it runs on, has a line in the registry."""
    seen = {(x["name"], json.dumps(x["params"], sort_keys=True)) for x in _trials()}
    for n, a in live_arms().items():
        if (n, json.dumps(_arm_numbers(a), sort_keys=True)) not in seen:
            trial(t, n, "arm", _arm_numbers(a), "live arm")


def dsr(xs, srs, n):
    """Deflated Sharpe (Bailey and Lopez de Prado): the chance the true Sharpe of these returns is above
    what the best of `n` tries would show by luck. `srs` are the Sharpes of everything tried."""
    T = len(xs)
    sd = statistics.pstdev(xs) if T > 2 else 0
    if not sd:
        return 0.0
    m = statistics.fmean(xs)
    sr = m / sd
    skew = sum((x - m) ** 3 for x in xs) / T / sd ** 3
    kurt = sum((x - m) ** 4 for x in xs) / T / sd ** 4
    nd = statistics.NormalDist()
    sr0 = 0.0
    if n > 1:
        spread = statistics.pvariance(srs) ** 0.5 if len(srs) > 1 else (1 / (T - 1)) ** 0.5
        g = 0.5772156649
        sr0 = spread * ((1 - g) * nd.inv_cdf(1 - 1 / n) + g * nd.inv_cdf(1 - 1 / (n * math.e)))
    den = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    return nd.cdf((sr - sr0) * (T - 1) ** 0.5 / den ** 0.5) if den > 0 else 0.0


def n_eff(n, m):
    """Trials that move together count as fewer: n shrinks towards 1 as the arms' block P&L correlates."""
    rs = []
    for a, b in itertools.combinations(m.values(), 2):
        try:
            rs.append(statistics.correlation(a, b))
        except (statistics.StatisticsError, ValueError):
            pass
    rho = max(0.0, statistics.fmean(rs)) if rs else 0.0
    return max(1.0, rho + (1 - rho) * n)


def pbo(m, s=LEARN_SPLITS):
    """Probability of backtest overfitting: over every way to split `s` time blocks in half, how often
    the best arm of one half lands in the bottom half of the arms on the other. `m` maps arm -> P&L per
    block. None when there's nothing to compare."""
    arms = sorted(m)
    if len(arms) < 2:
        return None
    over = tries = 0
    for c in itertools.combinations(range(s), s // 2):
        o = [i for i in range(s) if i not in c]
        best = max(arms, key=lambda a: (sum(m[a][i] for i in c), a))
        rank = sorted(arms, key=lambda a: (sum(m[a][i] for i in o), a)).index(best) + 1
        over += rank / (len(arms) + 1) <= 0.5
        tries += 1
    return over / tries


def _blocks(closed, t0, t1, s=LEARN_SPLITS):
    out = [0.0] * s
    for x in closed:
        out[min(s - 1, int((_ts(x["closed"]) - t0) / (t1 - t0) * s))] += x["pnl_sol"]
    return out


def _drawdown(xs):
    peak = total = worst = 0.0
    for x in xs:
        total += x
        peak = max(peak, total)
        worst = max(worst, peak - total)
    return worst


def beat(xs, base, n=1):
    """Mean and median both ahead of the control, on at least n trades."""
    return bool(len(xs) >= n and base and statistics.fmean(xs) > statistics.fmean(base) and median(xs) > median(base))


def score(closed, ctrl, t0, t1):
    """One arm against control over the window: the numbers, and whether it beat control overall and
    in each half, so one lucky coin can't carry it."""
    pc = [x["pnl_pct"] for x in closed]
    cc = [x["pnl_pct"] for x in ctrl]
    mid = (t0 + t1) / 2
    half = lambda xs, early: [x["pnl_pct"] for x in xs if (_ts(x["closed"]) < mid) == early]
    ahead = lambda a, b: bool(a and b and statistics.fmean(a) > statistics.fmean(b))
    return {"n": len(pc), "mean": statistics.fmean(pc) if pc else None, "median": median(pc), "drawdown_sol": round(_drawdown(x["pnl_sol"] for x in closed), 4),
            "beats_control": beat(pc, cc), "beats_halves": ahead(half(closed, True), half(ctrl, True)) and ahead(half(closed, False), half(ctrl, False))}


def promotable(c, overfit):
    """The four-part test: enough trades, ahead of control overall and in each half, and still ahead
    after deflating for every try and for overfitting. A minimum bar, not proof of an edge."""
    return bool(c["n"] >= LEARN_MIN_TRADES and c["beats_control"] and c["beats_halves"] and c["dsr"] >= DSR_MIN and overfit is not None and overfit <= PBO_MAX)


def _sim_sell(b, m, frac, r, su, t, why):
    """The same money as _sell, on a replayed position. r None is a rug marked to zero."""
    p = b["pos"][m]
    qty = p["tokens"] * frac
    if r:
        pair = {"priceUsd": r["px"], "liquidity": {"usd": r["liq"]}}
        gross = qty * r["px"] / su
        got = gross * (1 - FEE) * (1 - impact(gross, pair, su))
        got -= min(got, SANDWICH_USD / su)
    else:
        got = 0.0
    p["tokens"] -= qty
    p["got"] += got
    b["cash"] += got
    if frac >= 0.999:
        b["trades"].append({"mint": m, "pnl_pct": p["got"] / p["sol"] - 1, "pnl_sol": p["got"] - p["sol"], "why": why})
        b["recent"][m] = t
        del b["pos"][m]


def _sim_exits(b, a, by, t, su):
    """_apply_exits at 15-minute steps, plus the arms' own exits from cycle()."""
    for m in list(b["pos"]):
        p, r = b["pos"][m], by.get(m)
        if not r:
            if t - p["seen"] >= RUG_BACKSTOP_H * 3600:
                _sim_sell(b, m, 1.0, None, su, t, "gone")
            continue
        p["seen"], p["peak"] = t, max(p["peak"], r["px"])
        ret = r["px"] / p["entry"] - 1
        if p["liq"] and r["liq"] <= p["liq"] * (1 - EVENT_LIQ_DROP):
            _sim_sell(b, m, 1.0, r, su, t, "liquidity")
        elif r["m5"] <= EVENT_M5_DROP:
            _sim_sell(b, m, 1.0, r, su, t, "m5")
        elif a.get("x_exit") and _x_burst(r.get("x")):
            _sim_sell(b, m, 1.0, r, su, t, "x")
        elif a.get("unease_exit") and (r.get("read") or {}).get("unease", 0) >= UNEASE_EXIT:
            _sim_sell(b, m, 1.0, r, su, t, "unease")
        elif not p["half"] and ret >= p["tp1"]:
            p["half"] = True
            _sim_sell(b, m, 0.5, r, su, t, "tp1")
        elif not p["half"] and ret <= p["stop"]:
            _sim_sell(b, m, 1.0, r, su, t, "stop")
        elif p["half"] and r["px"] <= p["peak"] * 0.6:
            _sim_sell(b, m, 1.0, r, su, t, "trail")
        elif not p["half"] and (t - p["at"]) / 3600 >= TIME_STOP_H and ret < TIME_STOP_MIN_GAIN:
            _sim_sell(b, m, 1.0, r, su, t, "time")


def _sim_buy(b, a, r, t, su):
    sol = a.get("sol", MAX_POS_SOL)
    fill = r["px"] * (1 + impact(sol, {"priceUsd": r["px"], "liquidity": {"usd": r["liq"]}}, su))
    b["cash"] -= sol
    b["pos"][r["mint"]] = {"sol": sol, "tokens": (sol * (1 - FEE) - SANDWICH_USD / su) * su / fill, "entry": fill, "peak": fill, "got": 0.0, "half": False,
                           "stop": _arm_stop(a, r), "tp1": a.get("tp1", 1.0), "liq": r["liq"], "at": t, "seen": t}


def sim(cfgs, days, su):
    """Replay rule sets over recorded days, entries and exits, in one pass: the dataset is big, and this
    runs inside the loop. Exits are seen every 15 minutes, not every minute, so this is an estimate:
    good for comparing rule sets on the same days, not for predicting P&L. Returns name -> closed trades."""
    books = {n: {"cash": START_SOL, "pos": {}, "trades": [], "recent": {}} for n in cfgs}
    for day in days:
        cycles = []
        for x in read_day(day):
            if "cycle" in x:
                cycles.append((x, []))
            elif cycles:
                cycles[-1][1].append(x)
        for x, rows in cycles:
            t, by = x["cycle"], {r["mint"]: r for r in rows}
            for r in rows:  # the control's random draw, the same every replay
                r["_draw"] = hashlib.sha256(f"{t}{r['mint']}".encode()).hexdigest()
            for n, a in cfgs.items():
                b = books[n]
                _sim_exits(b, a, by, t, su)
                v = {"cash": b["cash"], "held": sorted(b["pos"]), "recent": [m for m, c in b["recent"].items() if t - c < ARM_COOLDOWN_H * 3600]}
                r = pick(n, rows, v, x["week"], a)
                if r:
                    _sim_buy(b, a, r, t, su)
    return {n: b["trades"] for n, b in books.items()}


def challengers(a, ideas):
    """One-step changes to the leader's numbers: fixes from the lessons first, then a small move either way."""
    out = [(LESSON_TESTS[k][0], LESSON_TESTS[k][1](a)) for k in ideas]
    stop, tp = a.get("stop", -0.35), a.get("tp1", 1.0)
    out += [("tighter stop", {"stop": stop + 0.05}), ("wider stop", {"stop": stop - 0.05}), ("sooner take-profit", {"tp1": tp * 0.75}), ("later take-profit", {"tp1": tp * 1.25})]
    return out[:4]


def _days_back(t, n):
    return [_day(t - i * 86400) for i in range(n, 0, -1)]


def _changelog(t, line):
    with open(os.path.join(STATE, "CHANGELOG.md"), "a") as f:
        f.write(f"- {_day(t)}: {line}\n")
    notify("memepaper: learning run", line)


def learn(t, force=False):
    """The weekly learning run, Sundays UTC. Scores every arm on its last LEARN_DAYS against control,
    applies the four-part promotion test, replays challengers, and writes LEARNING.md. Before LEARN_FROM
    it only proposes. After it, it may retire the worst arm and add one challenger, numbers only and
    inside the bounds. It never touches the picks, the control, the gate or the bounds."""
    path = os.path.join(STATE, "learn.json")
    s = _jload(path, {})
    when = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    week = "%d-W%02d" % when.isocalendar()[:2]
    if not force and (when.weekday() != 6 or s.get("week") == week):
        return None
    trials_sync(t)
    t0, arms, su = t - LEARN_DAYS * 86400, live_arms(), sol_usd()
    window = lambda p: [x for x in load(p)["closed"] if x.get("v") == 2 and _ts(x["closed"]) >= t0]
    ctrl, closed = window(CONTROL), {n: window(os.path.join(BOOKS, n + ".json")) for n in arms}
    scores = {n: score(xs, ctrl, t0, t) for n, xs in closed.items()}
    blocks = {n: _blocks(xs, t0, t) for n, xs in closed.items() if xs}
    tried = {(x["name"], json.dumps(x["params"], sort_keys=True)) for x in _trials()}
    n = n_eff(len(tried), blocks)
    srs = [statistics.fmean(p) / statistics.pstdev(p) for p in ([x["pnl_pct"] for x in xs] for xs in closed.values()) if len(p) > 2 and statistics.pstdev(p)]
    overfit = pbo(blocks)
    for name, c in scores.items():
        c["dsr"] = round(dsr([x["pnl_pct"] for x in closed[name]], srs, n), 4)
        c["promoted"] = promotable(c, overfit)
    ready = [x for x in scores if scores[x]["n"] >= LEARN_MIN_TRADES]
    leader = max(ready, key=lambda x: (scores[x]["mean"], x), default=None)
    cmean = statistics.fmean(x["pnl_pct"] for x in ctrl) if ctrl else None
    worst = min([x for x in ready if cmean is not None and scores[x]["mean"] < cmean], key=lambda x: (scores[x]["mean"], x), default=None)
    # A challenger needs a leader to change and room to run: 14 arms went live, so this waits for retirements.
    best, tests = None, []
    if leader and len(arms) - bool(worst) < LEARN_MAX_ARMS:
        cands = {}
        for i, (why, change) in enumerate(challengers(arms[leader], lesson_ideas())):
            change = _clamped(leader, {k: round(v, 4) for k, v in change.items()}, alert=False)
            if any(arms[leader].get(k) != v for k, v in change.items()):  # at a bound, a change may be no change
                cands[f"try-{i}"] = (why, change, {**arms[leader], **change})
        res = sim({"control": {"rule": lambda r, wk: True, "rank": "_draw"}, **{k: v[2] for k, v in cands.items()}}, _days_back(t, LEARN_SIM_DAYS), su)
        base = [x["pnl_pct"] for x in res["control"]]
        for k, (why, change, a) in cands.items():
            xs = [x["pnl_pct"] for x in res[k]]
            ok = beat(xs, base, LEARN_MIN_TRADES)
            tests.append({"why": why, "change": change, "n": len(xs), "mean": statistics.fmean(xs) if xs else None, "median": median(xs), "beat_control": ok})
            trial(t, f"{leader}+{why}", "replay", _arm_numbers(a), why, n=len(xs), mean=tests[-1]["mean"], passed=ok)
        best = max((x for x in tests if x["beat_control"]), key=lambda x: x["mean"], default=None)
    acting, did = t >= _ts(LEARN_FROM), []
    if acting and (worst or best):
        reg = _registry()
        if worst:
            reg["retired"].append(worst)
            did.append(f"retired {worst}: mean {scores[worst]['mean']:+.1%} over {scores[worst]['n']} trades, under control's {cmean:+.1%}")
        if best:
            name = f"v-c{len(reg['added']) + 1}"
            root = reg["added"].get(leader, {}).get("base", leader)
            reg["added"][name] = {"base": root, **_arm_numbers(arms[leader]), **best["change"]}
            did.append(f"added {name}: {leader} with {best['why']}, replay mean {best['mean']:+.1%} over {best['n']} trades")
            trial(t, name, "arm", _arm_numbers(arm_cfg(leader)) | best["change"], best["why"])
        os.makedirs(os.path.join(STATE, "params"), exist_ok=True)
        _jsave(os.path.join(STATE, "params", "arms.json"), reg)
        for line in did:
            _changelog(t, line)
    champs = sorted(x for x in scores if scores[x]["promoted"])
    summary = (f"{len(ready)} of {len(arms)} arms have {LEARN_MIN_TRADES}+ trades. Promoted: {', '.join(champs) or 'none'}. "
               + ("; ".join(did) + "." if did else ("Proposes only until 2026-11-30." if not acting else "No change.")))
    s.update(week=week, day=_day(t), summary=summary, leader=leader, worst=worst, promoted=champs, pbo=overfit, trials=len(tried), n_eff=round(n, 1),
             propose={"retire": worst, "add": best}, done=did)
    _jsave(path, s)
    rows = "\n".join(f"| {k} | {c['n']} | {'' if c['mean'] is None else format(c['mean'], '+.1%')} | {'' if c['median'] is None else format(c['median'], '+.1%')} | "
                     f"{c['drawdown_sol']} | {'yes' if c['beats_control'] else 'no'} | {'yes' if c['beats_halves'] else 'no'} | {c['dsr']:.2f} | {'yes' if c['promoted'] else 'no'} |"
                     for k, c in sorted(scores.items(), key=lambda kv: -(kv[1]["mean"] or -9)))
    with open(os.path.join(STATE, "LEARNING.md"), "w") as f:
        f.write(f"# Learning run {_day(t)}\n\n{summary}\n\nTrials so far: {len(tried)} ({n:.1f} effective). PBO: {'not enough to compare' if overfit is None else format(overfit, '.0%')}. "
                f"Control: {len(ctrl)} trades, mean {'n/a' if cmean is None else format(cmean, '+.1%')}.\n\n"
                f"| Arm | Trades | Mean | Median | Drawdown SOL | Beats control | Both halves | Deflated Sharpe | Promoted |\n|---|---|---|---|---|---|---|---|---|\n{rows}\n\n"
                f"Proposed retirement: {worst or 'none'}. Replayed on {LEARN_SIM_DAYS} days:\n\n"
                + ("\n".join(f"- {x['why']}: {x['n']} trades, mean {'n/a' if x['mean'] is None else format(x['mean'], '+.1%')}, {'beat' if x['beat_control'] else 'did not beat'} control" for x in tests) or "- nothing to replay yet")
                + "\n\nPassing is a minimum bar, not proof of profit. Gate value is in the report.\n")
    return s


def merge_refusals(diff):
    """Why this diff can't merge without Jackson: the reasons, or nothing. Code merges alone only inside
    MERGE_PATHS, and never when it touches a safety limit, this guard or anything near a wallet."""
    no, f, fn = [], None, None
    for x in diff.splitlines():
        if x.startswith("diff --git "):
            f, fn = x.split(" b/", 1)[1], None
            if f in MERGE_NEVER or not (f == MERGE_PATHS[0] or f.startswith(MERGE_PATHS[1:])):
                no.append(f"{f}: outside what merges alone")
            continue
        if x.startswith(("--- ", "+++ ")):
            continue
        body = x.split("@@")[-1].lstrip() if x.startswith("@@") else x[1:]  # git names the function a hunk starts in
        if x.startswith("@@") or body[:1].strip():  # anything at the top level ends a function
            d = re.match(r"def (\w+)\(", body)
            fn = d[1] if d else None
        if x[:1] in ("+", "-"):
            if fn in GUARDED_FUNCS:
                no.append(f"{f}: changes {fn}()")
            no += [f"{f}: changes {g}" for g in GUARDED if re.search(rf"\b{g}\b", x)]
            if x[0] == "+" and NO_WALLET.search(x):
                no.append(f"{f}: adds wallet code: {x[1:80].strip()}")
    return list(dict.fromkeys(no))


def guard(h):
    """Server only. New code that stays healthy for GUARD_S becomes the version to go back to. If it
    fails ERRORS_ALERT ticks in a row before then, go back, hold that commit out of the next pull, and
    stop: systemd restarts the loop on the good code."""
    if os.environ.get("MEMEPAPER_BY") != "server":
        return
    git = lambda *a: subprocess.run(["git", "-C", HERE, *a], capture_output=True, text=True)
    head, path = git("rev-parse", "HEAD").stdout.strip(), os.path.join(STATE, "guard.json")
    s = _jload(path, {})
    if head and head not in (s.get("good"), s.get("new")):
        s.update(new=head, since=clock())
    if s.get("new") == head:
        if clock() - s["since"] >= GUARD_S:
            s.update(good=head, new=None)
        elif s.get("good") and h.get("errors_in_a_row", 0) >= ERRORS_ALERT:
            git("reset", "-q", "--hard", s["good"])
            with open(os.path.join(os.path.dirname(HERE), "memepaper.hold"), "w") as f:
                f.write(head)
            s.update(new=None, rolled_back=head)
            _jsave(path, s)
            notify("memepaper: rolled back", f"{head[:7]} failed {ERRORS_ALERT} ticks in its first hour. Back on {s['good'][:7]}: it stays out until a newer commit.", "high", "warning")
            sys.exit(0)
    _jsave(path, s)


def notify(title, msg, priority="default", tags=""):
    """Push an alert to Jackson's phone with ntfy. The topic name is the only secret (a GitHub
    secret, masked in the public logs); without it the alert only prints. Never raises."""
    if os.environ.get("MEMEPAPER_SHADOW"):
        title = "[shadow] " + title
    print(f"alert: {title}: {msg}")
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    try:
        subprocess.run(["curl", "-sf", "-m", "10", "-H", f"Title: {title}", "-H", f"Priority: {priority}",
                        "-H", f"Tags: {tags}", "--data-binary", msg[:3000], "https://ntfy.sh/" + topic],
                       capture_output=True, check=True)
        return True
    except Exception:
        return False


def _git(*a):
    return subprocess.run(["git", "-C", STATE, *a], capture_output=True, text=True)


def _branch():
    return os.environ.get("MEMEPAPER_BRANCH", "state")


def pull():
    """Fetch new order files. Only this loop writes books, so a rebase never meets a conflict;
    if one fails anyway (network), carry on ticking and try again next minute."""
    if _git("pull", "-q", "--rebase", "--autostash", "origin", _branch()).returncode:
        _git("rebase", "--abort")
        return False
    return True


def push(msg):
    """Commit everything in the state folder and push, rebasing over new orders up to 3 times."""
    _git("add", "-A")
    if _git("diff", "--cached", "--quiet").returncode == 0:
        return True
    _git("commit", "-qm", msg)
    for _ in range(3):
        if _git("push", "-q", "origin", "HEAD:" + _branch()).returncode == 0:
            return True
        _git("pull", "-q", "--rebase", "origin", _branch())
    return False


def _ping(url):
    subprocess.run(["curl", "-fsS", "-m", "10", "-o", "/dev/null", url], capture_output=True)


def _health_path():
    return os.path.join(STATE, "health.json")


def _logs():
    return {p: len(load(p)["log"]) for p in (BOOK, CONTROL)}


def loop_once(h):
    """One minute of the hot loop: tick, then record health and send alerts. Never raises, so one
    bad API answer can't stop the loop. Returns whether the tick changed anything material."""
    before, material = _logs(), False
    try:
        material = tick()
    except BaseException as e:  # SystemExit too: nothing a tick does may end the loop
        if isinstance(e, KeyboardInterrupt):
            raise
        h["errors_in_a_row"] = h.get("errors_in_a_row", 0) + 1
        h["last_error"] = f"{now()} {e.__class__.__name__}: {str(e)[:200]}"
        print("tick failed:", h["last_error"])
        if h["errors_in_a_row"] == ERRORS_ALERT:
            notify("memepaper: ticks failing", f"{ERRORS_ALERT} ticks in a row failed. Last: {h['last_error']}",
                   "high", "warning")
    else:
        if h.get("errors_in_a_row", 0) >= ERRORS_ALERT:
            notify("memepaper: recovered", f"ticking again after {h['errors_in_a_row']} failed ticks", "default", "ok")
        h["errors_in_a_row"] = 0
        h["last_ok"], h["last_ok_ts"] = now(), clock()
        url = os.environ.get("HEALTHCHECK_URL")  # an outside clock: if these stop, it alerts, whatever died
        if url and clock() - h.get("ping_ts", 0) >= HEALTH_PING_S:
            _ping(url)
            h["ping_ts"] = clock()
        if clock() - h.get("last_cycle_ts", 0) >= CYCLE_MIN * 60:
            try:
                n = cycle()
                print(f"cycle: {n} coins recorded")
                h["last_cycle"], h["last_cycle_ts"], h["cycle_errors"], material = now(), clock(), 0, True
            except Exception as e:  # a failed snapshot never stops the exits: try again next tick
                h["cycle_errors"] = h.get("cycle_errors", 0) + 1
                h["last_cycle_error"] = f"{now()} {e.__class__.__name__}: {str(e)[:200]}"
                print("cycle failed:", h["last_cycle_error"])
                if h["cycle_errors"] == ERRORS_ALERT:
                    notify("memepaper: snapshots failing", h["last_cycle_error"], "default", "warning")
        try:
            gt_work(round(clock()))
        except Exception as e:
            print(f"gt work failed: {e.__class__.__name__}: {str(e)[:200]}")
    h["last_tick"], h["last_tick_ts"] = now(), clock()
    h["ticks"] = h.get("ticks", 0) + 1
    try:
        lines = [f"{'pick' if p == BOOK else 'control'}: {x}"
                 for p, n in before.items() for x in load(p)["log"][n:]]
    except Exception:
        lines = []
    if lines:
        hot = any(w in x for x in lines for w in ("event exit", "rugged", "stop-loss"))
        notify("memepaper: trade", "\n".join(lines), "high" if hot else "default", "chart_with_downwards_trend" if hot else "moneybag")
    with open(_health_path() + ".tmp", "w") as f:
        json.dump(h, f, indent=2)
    os.replace(_health_path() + ".tmp", _health_path())
    return material


def loop(minutes=55, every=60):
    """The hot loop: pull new orders, tick, push on anything material or every PUSH_EVERY_S.
    GitHub Actions starts one every 30 minutes and queues the next, so a run lasting 55 minutes
    leaves no gap. Ends with a push so the next run starts from everything this one did."""
    h = json.load(open(_health_path())) if os.path.exists(_health_path()) else {}
    h.update(run=os.environ.get("GITHUB_RUN_ID", "local"), code=os.environ.get("GITHUB_SHA", "local")[:7],
             started=now(), shadow=bool(os.environ.get("MEMEPAPER_SHADOW")))
    end, last_push, push_fails = clock() + minutes * 60, clock(), 0
    while True:
        t0 = clock()
        pull()
        material = loop_once(h)
        guard(h)
        if material or clock() - last_push >= PUSH_EVERY_S or clock() + every >= end:
            if push(f"tick {now()}{' (trade)' if material else ''}"):
                last_push, push_fails = clock(), 0
            else:
                push_fails += 1
                if push_fails == ERRORS_ALERT:
                    notify("memepaper: can't push", f"{ERRORS_ALERT} pushes in a row failed; ticking continues locally", "high", "warning")
        if clock() + every >= end:
            break
        time.sleep(max(1.0, every - (clock() - t0)))


def watchdog(now_ts=None):
    """Alert when the loop's last tick is more than STALE_MIN minutes old, at most once an hour
    (watchdog.json remembers; only the watchdog writes it). Runs as its own scheduled workflow."""
    t = now_ts or clock()
    try:
        last = json.load(open(_health_path())).get("last_tick_ts", 0)
    except Exception:
        last = 0
    wp = os.path.join(STATE, "watchdog.json")
    w = json.load(open(wp)) if os.path.exists(wp) else {}
    age, was = (t - last) / 60, dict(w)
    if age <= STALE_MIN and w.get("alerted"):
        notify("memepaper: loop back", f"ticking again (last tick {age:.0f} min ago)", "default", "ok")
        w = {"alerted": 0}
    elif age > STALE_MIN and t - w.get("alerted", 0) >= 3600:
        notify("memepaper: loop stale", f"no tick for {age:.0f} min. Check Actions: hot loop.", "urgent", "rotating_light")
        w = {"alerted": t}
    if w != was:  # written only when the alert state changes, so a healthy loop costs no commits
        with open(wp, "w") as f:
            json.dump(w, f, indent=2)
    return age


def status(done=10):
    """Read-only view for Claude's runs: the report, pending orders and the last results."""
    if os.path.exists(REPORT):
        print(open(REPORT).read())
    pending = sorted(f for f in os.listdir(ORDERS) if f.endswith(".json")) if ORDERS else []
    print(f"pending orders: {len(pending)}" + "".join(f"\n  {f[:-5]}" for f in pending))
    d = os.path.join(ORDERS, "done") if ORDERS else None
    if d and os.path.isdir(d):
        print("last results:")
        for f in sorted(x for x in os.listdir(d) if x.endswith(".json"))[-done:]:
            o = json.load(open(os.path.join(d, f)))
            print(f"  {o.get('applied_at', '?')}  {o.get('kind')}  {o.get('mint', '')[:6]}  {o.get('result')}")
    try:
        h = json.load(open(os.path.join(STATE, "health.json")))
        print(f"loop: last tick {h.get('last_tick')}, {h.get('errors_in_a_row', 0)} failed in a row; "
              f"last snapshot {h.get('last_cycle')}, {h.get('cycle_errors', 0)} failed in a row")
    except Exception:
        print("loop: no health.json yet")


def equity(bk, ps, su):
    return bk["cash_sol"] + sum(x["tokens"] * (float(ps[m]["priceUsd"]) if m in ps else x["entry_px"]) / su
                                for m, x in bk["positions"].items())


def migrate(src, dst, force=False):
    """Copy the legacy books (book.json, control.json beside the code) into a state folder and prove
    nothing changed: same positions, same cash and the same equity to 1e-9 SOL at one set of prices."""
    use_state(dst)
    if os.path.exists(BOOK) and not force:
        sys.exit(f"{BOOK} exists; pass --force to overwrite")
    old_b = json.load(open(os.path.join(src, "book.json")))
    old_c = json.load(open(os.path.join(src, "control.json")))
    save(copy.deepcopy(old_b), BOOK)
    save(copy.deepcopy(old_c), CONTROL)
    if os.path.exists(os.path.join(src, ".sol_usd")):
        open(SOL_CACHE, "w").write(open(os.path.join(src, ".sol_usd")).read())
    new_b, new_c = load(), load(CONTROL)
    su = sol_usd()
    mints = list(dict.fromkeys(list(old_b["positions"]) + list(old_c["positions"])))
    ps = pairs(mints) if mints else {}
    for name, a, z in (("claude", old_b, new_b), ("control", old_c, new_c)):
        ea, ez = equity(a, ps, su), equity(z, ps, su)
        if abs(ea - ez) > 1e-9 or a["positions"] != z["positions"] or a["cash_sol"] != z["cash_sol"] or a["closed"] != z["closed"]:
            sys.exit(f"migration check FAILED for {name}: {ea!r} vs {ez!r}")
        print(f"{name}: {len(z['positions'])} open, {len(z['closed'])} closed, cash {z['cash_sol']:.9f}, "
              f"equity {ez:.9f} SOL both sides")
    print("migration check passed")


def arm(bk, ps, su, v2_only):
    """(closed count, wins, P&L SOL incl. open marks, SOL deployed) for the v2 test."""
    cl = [x for x in bk["closed"] if not v2_only or x.get("v") == 2]
    op = [(m, x) for m, x in bk["positions"].items() if not v2_only or x.get("v") == 2]
    pnl = sum(x["pnl_sol"] for x in cl)
    for m, x in op:
        p = ps.get(m)
        px = float(p["priceUsd"]) if p else x["entry_px"]
        pnl += x["tokens"] * px / su + x["realised_sol"] - x["cost_sol"]
    cost = sum(x["cost_sol"] for x in cl) + sum(x["cost_sol"] for _, x in op)
    return len(cl), sum(1 for x in cl if x["pnl_sol"] > 0), pnl, cost


def median(xs):
    xs = sorted(xs)
    return (xs[len(xs) // 2] + xs[(len(xs) - 1) // 2]) / 2 if xs else None


def write_report(b, su, ps, c=None, quiet=False):
    c = c or load(CONTROL)
    open_val = 0.0
    lines = []
    for mint, pos in b["positions"].items():
        p = ps.get(mint)
        px = float(p["priceUsd"]) if p else pos["entry_px"]
        val = pos["tokens"] * px / su
        open_val += val
        r = px / pos["entry_px"] - 1
        lines.append(f"| {pos['symbol']} | `{mint[:8]}…` | {pos['opened']} | {pos['cost_sol']:.2f} | "
                     f"${pos['entry_mc'] or 0:,.0f} | {r:+.0%} | {val + pos['realised_sol']:.3f} | {pos['thesis']} |")
    equity = b["cash_sol"] + open_val
    closed = [f"| {c['symbol']} | {c['opened']} → {c['closed']} | {c['cost_sol']:.2f} | {c['pnl_sol']:+.3f} ({c['pnl_pct']:+.0%}) | {c['exit_reason']} |"
              for c in b["closed"]]
    wins = sum(1 for c in b["closed"] if c["pnl_sol"] > 0)
    pn, pw, pp, pc = arm(b, ps, su, True)
    cn, cw, cp, cc = arm(c, ps, su, False)
    def meds_of(k):
        ms = [(d, median([r["moves"][f"{d}d"] for r in b[k].values() if f"{d}d" in r["moves"]])) for d in REJECT_DAYS]
        return ", ".join(f"{d}d {m:+.0%}" if m is not None else f"{d}d n/a" for d, m in ms)
    rej, pas = meds_of("rejects"), meds_of("passes")
    extra_usd = (SANDWICH_STRESS_USD - SANDWICH_USD) / su
    def swaps(bk, v2_only):
        return sum(x.get("swaps", 0) for x in list(bk["closed"]) + list(bk["positions"].values())
                   if not v2_only or x.get("v") == 2)
    pp_s, cp_s = pp - swaps(b, True) * extra_usd, cp - swaps(c, False) * extra_usd
    arm_rows = []
    for path in other_arms():
        bk = load(path)
        n, w, pnl, cost = arm(bk, ps, su, False)
        arm_rows.append(f"| {os.path.basename(path)[:-5]} | {n} | {w} | {len(bk['positions'])} | {pnl:+.3f} | {pnl / cost if cost else 0:+.1%} |")
    arms_md = ("\n## Mechanical arms\n\nSame gate, size, costs and exit code as the picks; rules in `CLAUDE.md`. Judged against the "
               "control, and only after enough closed trades.\n\n| Arm | Closed | Won | Open | P&L SOL (incl. open) | Return on SOL deployed |\n"
               "|---|---|---|---|---|---|\n" + "\n".join(arm_rows) + "\n" if arm_rows else "")
    sc = _jload(os.path.join(STATE, "scout.json"), None) if STATE else None
    scout_md = ""
    if sc:
        names = {r: x for bk in [b, *[load(p) for p in other_arms()]] for r, x in bk["positions"].items()}
        xrows = [f"| {names.get(m, {}).get('symbol', m[:6])} | {x['posts']} | {x['before']} | {x['accounts']} | "
                 f"{'?' if x['small_share'] is None else format(x['small_share'], '.0%')} | "
                 f"{'?' if x['new_share'] is None else format(x['new_share'], '.0%')} | {x['kol']} | {x['repeats']} |"
                 for m, x in sc["coins"].items()]
        scout_md = (f"\n## X scout\n\n{sc['verdict']}. Clean files in a row: {sc['clean']} of {SCOUT_TRUST_RUNS} needed for the X arms. "
                    "Facts copied by Grok and counted by code: information only, never a gate.\n"
                    + ("\n| Coin | Posts (4h) | Last run | Accounts | Small accounts | New accounts | Large accounts | Repeats |\n"
                       "|---|---|---|---|---|---|---|---|\n" + "\n".join(xrows) + "\n" if xrows else ""))
    read_md = _read_md(b) if STATE else ""
    orders_md = ("\n## Orders (last 15)\n\n" + "\n".join(f"- {x['at']} `{x['id']}`: {x['result']}" for x in b["applied"][-15:]) + "\n"
                 if b.get("applied") else "")
    md = f"""---
title: Memecoin paper book
created: 2026-11-01
updated: {datetime.date.today()}
area: trading
---

*Paper only: simulated fills from live DexScreener prices, {FEE:.2%} fee each side plus a size/liquidity
slippage charge. No wallet, nothing reaches the market. Written by `memepaper.py` (repo memecoin-paper); do not hand-edit.*

**Equity {equity:.3f} SOL** (start {b['start_sol']:.1f} SOL, {equity / b['start_sol'] - 1:+.1%}) · cash {b['cash_sol']:.3f} SOL ·
open {len(b['positions'])} · closed {len(b['closed'])} ({wins} won) · SOL ${su:,.2f} · marked {now()}

**Benchmark (vs just holding SOL): {equity / b['start_sol'] - 1:+.1%}.** The book is counted in SOL, so its SOL
return *is* its edge over holding SOL. In dollars: ${equity * su:,.0f} vs ${b['start_sol'] * START_SOL_USD:,.0f} at the start
({equity * su / (b['start_sol'] * START_SOL_USD) - 1:+.1%}); SOL itself moved {su / START_SOL_USD - 1:+.1%}.
Review on {REVIEW_DATE} or after 30 closed v2 trades ({pn}/30), rules unchanged until then.

## v2 test (from {V2_START})

Does picking beat a random coin that passed the same gates, after costs? Each pick opens a same-size
control position on a random gate pass (`control.json`, same mechanical exits, no judgement exits).

| Arm | Closed | Won | P&L SOL (incl. open) | Return on SOL deployed |
|---|---|---|---|---|
| Picks | {pn} | {pw} | {pp:+.3f} | {pp / pc if pc else 0:+.1%} |
| Control | {cn} | {cw} | {cp:+.3f} | {cp / cc if cc else 0:+.1%} |

Costs in every fill: {FEE:.1%} fee each side, size/liquidity slippage, and a ${SANDWICH_USD:.2f} sandwich charge per swap.
If every swap were sandwiched at the ${SANDWICH_STRESS_USD:.0f} median: picks {pp_s:+.3f} SOL, control {cp_s:+.3f} SOL.

**Gate value** (raw price moves, no costs; the gate earns its keep if passes beat rejects):
passes {len(b['passes'])} tracked, median {pas} · rejects {len(b['rejects'])} tracked, median {rej}.
Legacy v1 positions (opened before v2, 1.25% fee model, sizes to 1 SOL) stay under the same exits and are left out of this table.
{arms_md}{scout_md}{read_md}
## Open positions

| Coin | Mint | Opened | Cost SOL | Entry mcap | Move | Value SOL (incl. realised) | Thesis |
|---|---|---|---|---|---|---|---|
{chr(10).join(lines) or '| none | | | | | | | |'}

## Closed

| Coin | Held | Cost SOL | P&L SOL | Exit |
|---|---|---|---|---|
{chr(10).join(closed) or '| none | | | | |'}

## Log

{chr(10).join('- ' + l for l in b['log'][-40:])}
{orders_md}"""
    open(REPORT, "w").write(md)
    if not quiet:
        print(f"equity {equity:.3f} SOL ({equity / b['start_sol'] - 1:+.1%}), open {len(b['positions'])}, report written")


def main(a):
    if not a:
        sys.exit(__doc__)
    cmd = a[0]
    if cmd == "migrate":
        return migrate(a[1], a[2], force="--force" in a)
    if cmd == "mergecheck":  # no state needed: the auto-merge workflow runs this on main's own code
        no = merge_refusals(sys.stdin.read())
        print("\n".join(no) or "ok")
        sys.exit(1 if no else 0)
    if os.environ.get("MEMEPAPER_STATE"):
        use_state(os.environ["MEMEPAPER_STATE"])
    if cmd == "feed":  # runs for good beside the loop, so it can't take the books' lock
        return feed(float(a[2]) if a[1:2] == ["--seconds"] else None)
    lockf = open(LOCK, "w")
    fcntl.flock(lockf, fcntl.LOCK_EX)  # released when the process exits
    if cmd == "screen":
        screen(a[1:])
    elif cmd == "gate":
        gate(a[1:])
    elif cmd == "buy":
        kw = {k.lstrip("-"): float(v) for k, v in zip(a[4::2], a[5::2])}
        buy(a[1], a[2], a[3], **kw)
    elif cmd == "sell":
        sell(a[1], a[2], a[3])
    elif cmd == "mark":
        if ORDERS:
            sys.exit("state mode: only the hot loop marks the books (tick); use `status` to read them")
        mark(quiet="--quiet" in a)
    elif cmd == "status":
        status()
    elif cmd == "replay":
        sys.exit(1 if replay(a[1]) else 0)
    elif cmd == "learn":
        print(json.dumps(learn(round(clock()), force=True), indent=2))
    elif cmd == "brief":
        brief(a[1])
    elif cmd == "autopsy":
        print(autopsy(round(clock()), int(a[1]) if len(a) > 1 else AUTOPSY_DAYS))
    elif cmd == "datacheck":
        print(json.dumps(datacheck(a[1] if len(a) > 1 else _day(clock())), indent=2))
    elif cmd == "tick":
        tick(quiet="--verbose" not in a)
    elif cmd == "loop":
        kw = {k.lstrip("-"): float(v) for k, v in zip(a[1::2], a[2::2])}
        if not ORDERS:
            sys.exit("loop needs state mode: set MEMEPAPER_STATE to the state folder")
        loop(**kw)
    elif cmd == "watchdog":
        if not ORDERS:
            sys.exit("watchdog needs state mode: set MEMEPAPER_STATE to the state folder")
        watchdog()
        push(f"watchdog {now()}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
