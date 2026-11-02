#!/usr/bin/env python3
"""Memecoin paper book: screen, paper-buy, paper-sell and mark-to-market.

Paper only. No wallet, no keys, no orders: prices come from the free public
DexScreener and RugCheck APIs and every fill is simulated.

  python3 -I memepaper.py screen <mint> [<mint> ...]   # table of live stats
  python3 -I memepaper.py buy <mint> <sol> "<thesis>" [--stop -0.35] [--tp1 1.0]
  python3 -I memepaper.py sell <mint> <fraction 0-1> "<reason>"
  python3 -I memepaper.py mark        # reprice, apply stops/take-profits, write the .md
"""
import json, sys, time, subprocess, datetime, os, fcntl

HERE = os.path.dirname(os.path.abspath(__file__))
BOOK = os.path.join(HERE, "book.json")
REPORT = os.path.join(HERE, "book.md")

START_SOL = 10.0
FEE = 0.0125        # pump.fun/PumpSwap fee ~1% + priority/tip, each side
SLIP_K = 0.5        # extra slippage: size / liquidity * SLIP_K (rough constant-product impact)
MAX_POS_SOL = 1.0   # no single position above 10% of the starting book
MAX_OPEN = 6
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


def load():
    if os.path.exists(BOOK):
        return json.load(open(BOOK))
    return {"start_sol": START_SOL, "cash_sol": START_SOL, "positions": {}, "closed": [], "log": []}


def save(b):
    json.dump(b, open(BOOK, "w"), indent=2)


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


def buy(mint, sol, thesis, stop=-0.35, tp1=1.0):
    b = load()
    sol = min(float(sol), MAX_POS_SOL, b["cash_sol"])
    if len(b["positions"]) >= MAX_OPEN:
        sys.exit("max open positions reached")
    if mint in b["positions"]:
        sys.exit("already holding")
    su = sol_usd()
    p = pairs([mint])[mint]
    px = float(p["priceUsd"])
    fill = px * (1 + impact(sol, p, su))
    tokens = sol * (1 - FEE) * su / fill
    score, risks = rug(mint)
    b["cash_sol"] -= sol
    b["positions"][mint] = {
        "symbol": p["baseToken"]["symbol"], "opened": now(), "cost_sol": sol, "tokens": tokens,
        "entry_px": fill, "entry_mc": p.get("marketCap"), "peak_px": fill, "stop": stop, "tp1": tp1,
        "tp1_done": False, "thesis": thesis, "rugcheck": score, "risks": risks, "realised_sol": 0.0,
        "dex": p["dexId"], "url": p.get("url")}
    b["log"].append(f"{now()} BUY {p['baseToken']['symbol']} {sol:.2f} SOL @ ${fill:.8g} (mc ${p.get('marketCap',0):,.0f}): {thesis}")
    save(b)
    print(b["log"][-1])


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
    write_report(b, su, {})


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
        (one miss is usually an API blip, not a rug)."""
    b = load()
    su = sol_usd()
    ps = pairs(list(b["positions"])) if b["positions"] else {}
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
    b["last_mark"] = now()
    save(b)
    write_report(b, su, pairs(list(b["positions"])) if b["positions"] else {}, quiet=quiet)


def write_report(b, su, ps, quiet=False):
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
    elif cmd == "buy":
        kw = {k.lstrip("-"): float(v) for k, v in zip(a[4::2], a[5::2])}
        buy(a[1], a[2], a[3], **kw)
    elif cmd == "sell":
        sell(a[1], a[2], a[3])
    elif cmd == "mark":
        mark(quiet="--quiet" in a)
    else:
        sys.exit(__doc__)
