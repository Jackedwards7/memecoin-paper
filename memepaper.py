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
  python3 -I memepaper.py migrate <old repo dir> <state dir>   # one-time move of the books
  python3 -I memepaper.py loop [--minutes 55] [--every 60]     # the hot loop (GitHub Actions)
  python3 -I memepaper.py watchdog    # alert if the loop's health.json is stale

Alerts go to ntfy when NTFY_TOPIC is set (a GitHub secret); otherwise they only print.

Rules v2 (from 2026-11-03, Jackson's call after the playbook research): every buy needs a gate
pass from the last 2 hours, and each buy also opens a same-size position in control.json on a
random coin from the same gate-pass pool. Gate failures are tracked as shadow rejects for 7 days.
The review asks whether picks beat the control after costs.
"""
import json, sys, time, subprocess, datetime, os, fcntl, random, urllib.parse, copy, gzip, glob, re

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
LOCK = "/tmp/memepaper.lock"  # the 2-minute watcher and manual trades never write at once
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
    info.update(score=r.get("score_normalised"), holders=r.get("totalHolders"))
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
        info.update(insider=ins, creator=(r.get("creatorBalance") or 0) / supply,
                    top=max([h.get("amount", 0) / supply for h in r.get("topHolders") or []
                             if h.get("owner") not in pools and h.get("address") not in pools], default=0))
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
        "entry_liq": (p.get("liquidity") or {}).get("usd") or 0}
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
                            "pnl_pct": pnl / pos["cost_sol"], "exit_reason": reason})
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
        ctl = "control opened" if len(c["positions"]) > n else "no control"
        return f"bought {pos['symbol']} {pos['cost_sol']:.2f} SOL @ ${pos['entry_px']:.8g}; {ctl}"
    if kind == "sell":
        m, frac = o.get("mint"), float(o.get("fraction", 0))
        if m not in b["positions"]:
            return "refused: not held"
        if not 0 < frac <= 1:
            return f"refused: fraction {frac} not in (0, 1]"
        _sell(b, m, frac, str(o.get("reason", "")), pairs([m]).get(m), sol_usd())
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
}


def _x_ok(r):
    """X data the arms may use: a trusted scout, recent, with this coin in it."""
    return bool(r.get("x") and r["x"]["trusted"])


def _x_organic(r):
    """Posts rising, mostly from small accounts over X_NEW_DAYS old."""
    x = r.get("x") or {}
    return _x_ok(r) and x["posts"] > x["before"] and (x["small_share"] or 0) >= 0.5


def _passed(r):
    """A row an arm may buy: in the universe with a clean gate result from the last GATE_TTL_H."""
    g = r.get("gate")
    return bool(r["eligible"] and g and not g["fails"] and r["t"] - g["at"] < GATE_TTL_H * 3600)


def view(bk, t):
    """All pick() needs to know about a book. Saved in the dataset, so a day can be replayed exactly."""
    cut = t - ARM_COOLDOWN_H * 3600
    recent = [x["mint"] for x in bk["closed"] if _ts(x["closed"]) >= cut]
    return {"cash": round(bk["cash_sol"], 9), "held": sorted(bk["positions"]), "recent": sorted(set(recent))}


def pick(name, rows, v, week=None):
    """The row this arm buys this cycle, or None. Pure: same inputs, same answer, live or replayed."""
    arm_ = VARIANTS[name]
    if v["cash"] <= ARM_CASH_FLOOR or len(v["held"]) >= MAX_OPEN:
        return None
    ok = [r for r in rows if _passed(r) and r["mint"] not in v["held"] and r["mint"] not in v["recent"]
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
    h1, h24 = tx.get("h1") or {}, tx.get("h24") or {}
    trades = (h24.get("buys") or 0) + (h24.get("sells") or 0)
    age = (t * 1000 - (p.get("pairCreatedAt") or t * 1000)) / 3.6e6
    return {"t": t, "mint": mint, "symbol": p["baseToken"].get("symbol"), "px": float(p["priceUsd"]),
            "liq": _liq(p), "mc": p.get("marketCap") or 0, "dex": p.get("dexId"), "age_h": round(age, 2),
            "vol_h1": vol.get("h1") or 0, "vol_h24": vol.get("h24") or 0,
            "buys_h1": h1.get("buys") or 0, "sells_h1": h1.get("sells") or 0,
            "buys_h24": h24.get("buys") or 0, "sells_h24": h24.get("sells") or 0, "trades_h24": trades,
            "avg_trade": round((vol.get("h24") or 0) / trades, 2) if trades else 0,
            "m5": pc.get("m5") or 0, "h1": pc.get("h1") or 0, "h6": pc.get("h6") or 0, "h24": pc.get("h24") or 0,
            "eligible": age >= UNIVERSE_MIN_AGE_H and _liq(p) >= UNIVERSE_MIN_LIQ, "gate": gate_, "arms": [], "x": None}


def snapshot(t):
    """Price the watch list, gate what's due (longest wait first, inside CYCLE_BUDGET_S) and return
    (rows, pairs, new gate results). Rows cover every coin that has ever qualified, so one that
    collapses stays in the data: a dataset of only the living would flatter every rule."""
    wp, gp = os.path.join(STATE, "watch.json"), os.path.join(STATE, "gate.json")
    watch, cache = _jload(wp, {}), _jload(gp, {})
    for m in candidates():
        watch.setdefault(m, {"ok": False})["t"] = t
    live = [(m, w) for m, w in watch.items() if t - w["t"] < (WATCH_DAYS * 86400 if w["ok"] else WATCH_FRESH_H * 3600)]
    watch = dict(sorted(live, key=lambda x: (not x[1]["ok"], -x[1]["t"]))[:WATCH_MAX])
    ps, rows = pairs(list(watch)), {}
    for m, w in watch.items():
        p = ps.get(m)
        if p and p.get("priceUsd") and p.get("dexId"):  # DexScreener lists some pairs with no price yet
            r = make_row(m, p, None, t)
            if r["eligible"]:
                w.update(ok=True, t=t)
            if w["ok"]:
                rows[m] = r
    due = [m for m, r in rows.items() if r["eligible"]
           and t - cache.get(m, {}).get("tried", 0) >= GATE_REFRESH_MIN * 60]
    due.sort(key=lambda m: cache.get(m, {}).get("tried", 0))
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
        cache[m] = {"at": t, "tried": t, "fails": fails, **info}
        results[m] = {"symbol": rows[m]["symbol"], "px": rows[m]["px"], "fails": fails}
    cache = {m: g for m, g in cache.items() if t - g["tried"] < 2 * 86400}
    for m, r in rows.items():
        r["gate"] = cache.get(m)
    _jsave(wp, watch)
    _jsave(gp, cache)
    return list(rows.values()), ps, results


def _data_path(t):
    os.makedirs(os.path.join(STATE, "data"), exist_ok=True)
    day = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")
    return os.path.join(STATE, "data", day + ".jsonl")


def read_day(day):
    """A day's dataset lines, from the plain file or its gzipped copy."""
    base = os.path.join(STATE, "data", day + ".jsonl")
    if os.path.exists(base):
        return [json.loads(x) for x in open(base)]
    if os.path.exists(base + ".gz"):
        with gzip.open(base + ".gz", "rt") as f:
            return [json.loads(x) for x in f]
    return []


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


def _check_post(p, run, where):
    if not isinstance(p, dict) or set(p) != _X_POST:
        return [f"{where}: wrong fields"]
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
    if d["scout"] != "v1" or d["window_hours"] != 4:
        return ["scout must be v1 and window_hours 4"]
    if not isinstance(d["coins"], list) or len(d["coins"]) > SCOUT_MAX_COINS or not isinstance(d["errors"], list):
        return [f"coins must be a list of at most {SCOUT_MAX_COINS}, errors a list"]
    if not d["coins"] and not (len(d["errors"]) == 1 and d["errors"][0] in ("cannot read", "incomplete", "empty")):
        return ["no coins needs exactly one failure reason"]
    bad, seen = [], set()
    for c in d["coins"]:
        if not isinstance(c, dict) or set(c) != {"mint", "symbol", "status", "posts"} or not isinstance(c["posts"], list):
            bad.append("coin fields are wrong")
            continue
        where = str(c["symbol"])[:12]
        if c["status"] not in ("ok", "none", "failed") or (c["status"] == "ok") != bool(c["posts"]):
            bad.append(f"{where}: status doesn't fit its posts")
        if len(c["posts"]) > SCOUT_MAX_POSTS:
            bad.append(f"{where}: over {SCOUT_MAX_POSTS} posts")
        for i, p in enumerate(c["posts"], 1):
            bad += _check_post(p, run, f"{where} post {i}")
            if isinstance(p, dict):
                if (c["mint"], str(p.get("url"))) in seen:
                    bad.append(f"{where} post {i}: repeated")
                seen.add((c["mint"], str(p.get("url"))))
    return bad


def scout_verify(posts):
    """Look up a random sample on X's public embed data: does each post exist, by that account,
    saying that? Returns (found, not found, contradicted). Follower counts aren't in that data."""
    found, missing, wrong = 0, 0, 0
    for p in random.sample(posts, min(SCOUT_SAMPLE, len(posts))):
        n = _X_URL.match(p["url"])[2]
        try:
            r = get(f"https://cdn.syndication.twimg.com/tweet-result?id={n}&token=a")
        except Exception:
            missing += 1
            continue
        who = ((r or {}).get("user") or {}).get("screen_name")
        if not who:
            missing += 1
        elif who.lower() == p["handle"].lower() and norm(p["first_words"])[:20] in norm(r.get("text")):
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
    before = before or {"posts": len(posts), "kol": len(kol)}  # no earlier run: nothing has risen
    return {"posts": len(posts), "before": before["posts"], "accounts": len({p["handle"].lower() for p in posts}),
            "new_share": round(sum(p["account_age_days"] < X_NEW_DAYS for p in dated) / len(dated), 3) if dated else None,
            "small_share": round(len(small) / len(known), 3) if known else None,
            "kol": len(kol), "kol_before": before["kol"], "repeats": len(words) - len(set(words))}


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
    posts = [p for c in d["coins"] for p in c["posts"]]
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
    for r in rows:
        r["x"] = x.get(r["mint"])
    week, su, views = week_ago(t), sol_usd(), {}
    for name, a in VARIANTS.items():
        path = os.path.join(BOOKS, name + ".json")
        bk = load(path)
        for m in list(bk["positions"]) if a.get("x_exit") else []:
            c = x.get(m)
            if c and c["trusted"] and m in ps and c["kol"] >= X_KOL_BURST and c["kol"] > c["kol_before"]:
                _sell(bk, m, 1.0, "x exit: large accounts piling in", ps[m], su)
        v = views[name] = view(bk, t)
        r = pick(name, rows, v, week)
        if r:
            _open(bk, r["mint"], MAX_POS_SOL, f"{name} rule", a.get("stop", -0.35), a.get("tp1", 1.0), ps[r["mint"]], su)
            r["arms"].append(name)
        save(bk, path)
    write_watchlist(rows, t)
    path = _data_path(t)
    with open(path, "a") as f:
        f.write(json.dumps({"cycle": t, "views": views, "week": {r["mint"]: week[r["mint"]] for r in rows if r["mint"] in week}}) + "\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")
    _roll_data(path)
    return len(rows)


def replay(day):
    """Re-run every arm's pick over a recorded day and compare with what the arm did live. Entries
    only: exits run every 60 s and the dataset is 15-minute rows. Returns the differences."""
    diffs, n, cycles = [], 0, []
    for x in read_day(day):
        if "cycle" in x:
            cycles.append((x, []))
        else:
            cycles[-1][1].append(x)
    for x, rows in cycles:
        for name in VARIANTS.keys() & x["views"].keys():  # arms added later have no history here
            n += 1
            r = pick(name, rows, x["views"][name], x["week"])
            live = [y["mint"] for y in rows if name in y["arms"]]
            if (r["mint"] if r else None) != (live[0] if live else None):
                diffs.append(f"{x['cycle']} {name}: replay {r['mint'] if r else None}, live {live}")
    print(f"replayed {n} arm decisions on {day}: {len(diffs)} differences")
    for d in diffs:
        print(" ", d)
    return diffs


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
{arms_md}{scout_md}
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
    if os.environ.get("MEMEPAPER_STATE"):
        use_state(os.environ["MEMEPAPER_STATE"])
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
