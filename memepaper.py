#!/usr/bin/env python3
"""Memecoin paper book: screen, paper-buy, paper-sell and mark-to-market.

Paper only. No wallet, no keys, no orders: prices come from the free public
DexScreener and RugCheck APIs and every fill is simulated.

  python3 -I memepaper.py screen <mint> [<mint> ...]   # table of live stats
  python3 -I memepaper.py gate <mint> [<mint> ...]     # hard safety gates; passes unlock buy
  python3 -I memepaper.py buy <mint> <sol> "<thesis>" [--stop -0.35] [--tp1 1.0]
  python3 -I memepaper.py sell <mint> <fraction 0-1> "<reason>"
  python3 -I memepaper.py mark        # reprice, apply stops/take-profits, write the .md

Rules v2 (from 2026-11-03, Jackson's call after the playbook research): every buy needs a gate
pass from the last 2 hours, and each buy also opens a same-size position in control.json on a
random coin from the same gate-pass pool. Gate failures are tracked as shadow rejects for 7 days.
The review asks whether picks beat the control after costs.
"""
import json, sys, time, subprocess, datetime, os, fcntl, random, urllib.parse

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
MISSES_TO_ZERO = 3        # consecutive checks with no price before a coin counts as rugged
LOCK = "/tmp/memepaper.lock"  # the 2-minute watcher and manual trades never write at once


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
    return b


def save(b, path=None):
    json.dump(b, open(path or BOOK, "w"), indent=2)


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def gate_one(mint, p):
    """The playbook's hard safety gates (wiki: memecoin-trading-playbook). Returns the failures;
    an empty list is a pass. Anything that can't be checked counts as a fail."""
    try:
        r = get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report")
    except Exception as e:
        return [f"RugCheck unavailable ({e.__class__.__name__})"]
    fails = []
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
        locked = deep["lp"].get("lpLockedPct") or 0
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
    b = load()
    t = time.time()
    b["gate_pass"] = {m: s for m, s in b["gate_pass"].items() if t - s < GATE_TTL_H * 3600}
    ps = pairs(mints)
    for m in mints:
        p = ps.get(m)
        if not p:
            print(f"{m[:6]}  FAIL no pair")
            continue
        fails = gate_one(m, p)
        sym = p["baseToken"]["symbol"]
        if fails:
            b["gate_pass"].pop(m, None)
            if m not in b["rejects"]:
                b["rejects"][m] = {"symbol": sym, "at": t, "px": float(p["priceUsd"]), "fails": fails, "moves": {}}
            print(f"{sym[:10]:10} {m[:6]}  FAIL " + "; ".join(fails))
        else:
            b["gate_pass"][m] = t
            warn = "  (warning: paid boost with no profile)" if p.get("boosts") and not p.get("info") else ""
            print(f"{sym[:10]:10} {m[:6]}  PASS{warn}")
    save(b)


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
    tokens = sol * (1 - FEE) * su / fill
    score, risks = rug(mint)
    b["cash_sol"] -= sol
    b["positions"][mint] = {
        "symbol": p["baseToken"]["symbol"], "opened": now(), "cost_sol": sol, "tokens": tokens,
        "entry_px": fill, "entry_mc": p.get("marketCap"), "peak_px": fill, "stop": stop, "tp1": tp1,
        "tp1_done": False, "thesis": thesis, "rugcheck": score, "risks": risks, "realised_sol": 0.0,
        "dex": p["dexId"], "url": p.get("url"), "v": 2}
    b["log"].append(f"{now()} BUY {p['baseToken']['symbol']} {sol:.2f} SOL @ ${fill:.8g} (mc ${p.get('marketCap',0):,.0f}): {thesis}")
    print(b["log"][-1])


def buy(mint, sol, thesis, stop=-0.35, tp1=1.0):
    b = load()
    sol = min(float(sol), MAX_POS_SOL, b["cash_sol"])
    if sum(1 for q in b["positions"].values() if q.get("v") == 2) >= MAX_OPEN:
        sys.exit("max open positions reached")
    if mint in b["positions"]:
        sys.exit("already holding")
    t = time.time()
    pool = [m for m, s in b["gate_pass"].items() if t - s < GATE_TTL_H * 3600]
    if mint not in pool:
        sys.exit(f"no gate pass in the last {GATE_TTL_H}h: run `gate {mint}` first")
    su = sol_usd()
    c = load(CONTROL)
    # The control never draws the pick itself (from 2026-11-03): a control on the same coin
    # copies the pick's result and tells the review nothing.
    free = [m for m in pool if m != mint and m not in c["positions"]]
    ctl = random.SystemRandom().choice(free) if free else None
    ps = pairs([mint] + ([ctl] if ctl else []))
    _open(b, mint, sol, thesis, stop, tp1, ps[mint], su)
    save(b)
    # Control arm: same size and exits, on a coin drawn at random from the same gate passes.
    if ctl and ctl in ps:
        _open(c, ctl, sol, f"control for {ps[mint]['baseToken']['symbol']}: random pick from {len(free)} other gate passes", stop, tp1, ps[ctl], su)
        save(c, CONTROL)
    else:
        print("no control entry: no other unheld gate pass to draw from")


def _sell(b, mint, frac, reason, p, su):
    pos = b["positions"][mint]
    qty = pos["tokens"] * frac
    px = float(p["priceUsd"]) if p else 0.0
    gross_sol = qty * px / su
    proceeds = gross_sol * (1 - FEE) * (1 - impact(gross_sol, p, su) if p else 0)
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
      - a coin with no DexScreener pair on MISSES_TO_ZERO checks in a row is marked to zero
        (one miss is usually an API blip, not a rug).
    The control book gets the same rules; shadow rejects get their 1/3/7-day moves recorded."""
    b = load()
    c = load(CONTROL)
    su = sol_usd()
    t = time.time()
    due = [m for m, r in b["rejects"].items() if len(r["moves"]) < len(REJECT_DAYS)]
    want = list(dict.fromkeys(list(b["positions"]) + list(c["positions"]) + due))
    ps = pairs(want) if want else {}
    for bk in (b, c):
        _apply_exits(bk, ps, su)
    for m in due:
        r, p = b["rejects"][m], ps.get(m)
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


def _apply_exits(b, ps, su):
    for mint in list(b["positions"]):
        pos = b["positions"][mint]
        p = ps.get(mint)
        if not p:
            pos["misses"] = pos.get("misses", 0) + 1
            if pos["misses"] >= MISSES_TO_ZERO:
                _sell(b, mint, 1.0, f"no pair found on {MISSES_TO_ZERO} checks in a row: treated as rugged, marked to zero", None, su)
            continue
        pos["misses"] = 0
        px = float(p["priceUsd"])
        pos["peak_px"] = max(pos["peak_px"], px)
        r = px / pos["entry_px"] - 1
        if not pos["tp1_done"] and r >= pos["tp1"]:
            pos["tp1_done"] = True
            _sell(b, mint, 0.5, f"take-profit at {r:+.0%}: half sold, cost recovered", p, su)
        elif not pos["tp1_done"] and r <= pos["stop"]:
            _sell(b, mint, 1.0, f"stop-loss at {r:+.0%}", p, su)
        elif pos["tp1_done"] and px <= pos["peak_px"] * 0.6:
            _sell(b, mint, 1.0, f"trailing stop: 40% off peak, {r:+.0%} from entry", p, su)
        elif not pos["tp1_done"] and held_hours(pos) >= TIME_STOP_H and r < TIME_STOP_MIN_GAIN:
            _sell(b, mint, 1.0, f"time stop: {held_hours(pos):.0f}h held, {r:+.0%}, no take-profit", p, su)


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
    meds = [(d, median([r["moves"][f"{d}d"] for r in b["rejects"].values() if f"{d}d" in r["moves"]])) for d in REJECT_DAYS]
    rej = ", ".join(f"{d}d {m:+.0%}" if m is not None else f"{d}d n/a" for d, m in meds)
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

Shadow rejects (gate failures, scored as if bought): {len(b['rejects'])} tracked; median move {rej}.
Legacy v1 positions (opened before v2, 1.25% fee model, sizes to 1 SOL) stay under the same exits and are left out of this table.

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
"""
    open(REPORT, "w").write(md)
    if not quiet:
        print(f"equity {equity:.3f} SOL ({equity / b['start_sol'] - 1:+.1%}), open {len(b['positions'])}, report written")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd = a[0]
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
        mark(quiet="--quiet" in a)
    else:
        sys.exit(__doc__)
