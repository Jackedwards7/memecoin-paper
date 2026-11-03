"""Offline tests for memepaper.py. No network: every API call is served from tests/fixtures
or from a fake market the test controls. Run from the repo root:

    python3 -I -m unittest discover -s tests -t . -v

Regenerate the replay golden file only on purpose, after a rule change you meant to make:

    REGEN_GOLDEN=1 python3 -I -m unittest discover -s tests -t . -k test_replay_matches_golden
"""
import copy, datetime, io, json, os, subprocess, sys, tempfile, time, unittest
from contextlib import redirect_stdout
from unittest import mock

import memepaper as mp

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SU = 100.0  # fixed SOL price in every test


def fx(name):
    return json.load(open(os.path.join(FIX, name)))


NAMES = ("gato", "cbucks", "rico", "wasted")
RC = {n: fx(f"rc_{n}.json") for n in NAMES}
MINT = {n: RC[n]["mint"] for n in NAMES}


def best_pair(n):
    return max(fx(f"pair_{n}.json"), key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)


def fake_pair(mint, px, liq=200_000, symbol=None, name=None):
    return {"baseToken": {"address": mint, "symbol": symbol or mint[:4], "name": name or mint[:4]},
            "priceUsd": str(px), "liquidity": {"usd": liq}, "dexId": "pumpswap", "marketCap": px * 1e9,
            "txns": {"h1": {"buys": 10, "sells": 5}}, "priceChange": {"m5": 0, "h1": 1, "h24": 2},
            "pairCreatedAt": 0, "url": "https://example.invalid"}


class Env(unittest.TestCase):
    """Each test gets a temp folder for the books and a fake API. `self.market` maps mint -> pair
    (delete a mint to make it vanish); `self.rc` maps mint -> RugCheck report."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.patches = [mock.patch.object(mp, k, os.path.join(d, v)) for k, v in
                        (("BOOK", "book.json"), ("CONTROL", "control.json"), ("REPORT", "book.md"),
                         ("SOL_CACHE", ".sol_usd"))]
        self.patches += [mock.patch.object(mp, "get", self.fake_get),
                         mock.patch.object(mp, "sol_usd", lambda: SU)]
        for p in self.patches:
            p.start()
        self.reset()

    def reset(self):
        """Fresh fixtures and empty books, inside one test."""
        for f in (mp.BOOK, mp.CONTROL, mp.REPORT):
            if os.path.exists(f):
                os.remove(f)
        self.market, self.rc, self.search, self.fail_urls = {}, {}, {}, []
        for n in NAMES:
            self.market[MINT[n]] = best_pair(n)
            self.rc[MINT[n]] = copy.deepcopy(RC[n])
            self.search[MINT[n]] = fx(f"search_{n}.json")
        self.out = io.StringIO()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def fake_get(self, url):
        if any(f in url for f in self.fail_urls):
            raise subprocess.CalledProcessError(22, ["curl", url])
        if "/tokens/v1/solana/" in url:
            return [self.market[m] for m in url.rsplit("/", 1)[1].split(",") if m in self.market]
        if "rugcheck.xyz" in url:
            m = url.split("/tokens/")[1].split("/")[0]
            r = self.rc[m]
            if url.endswith("/summary"):
                return {"score_normalised": r.get("score_normalised"), "risks": r.get("risks", [])}
            return r
        if "/latest/dex/search" in url:
            q = url.split("q=")[1]
            for m, r in self.rc.items():
                if mp.urllib.parse.quote(r["tokenMeta"]["name"]) == q:
                    return self.search.get(m, {"pairs": []})
            return {"pairs": []}
        raise subprocess.CalledProcessError(22, ["curl", url])

    def run_quiet(self, f, *a, **kw):
        with redirect_stdout(self.out):
            return f(*a, **kw)

    def add_fake(self, mint, px, **kw):
        """A coin that passes the gate: GATO's clean report under a new mint and name."""
        self.market[mint] = fake_pair(mint, px, **kw)
        r = copy.deepcopy(RC["gato"])
        r["mint"] = mint
        r["tokenMeta"] = {"name": f"Fake {mint}", "symbol": mint[:4]}
        self.rc[mint] = r

    def hold(self, mint, entry=1.0, sol=0.25, path=None, **extra):
        """Put an open position straight into a book, bypassing the gate."""
        b = mp.load(path)
        b["cash_sol"] -= sol
        b["positions"][mint] = {"symbol": mint[:4], "opened": mp.now(), "cost_sol": sol,
                                "tokens": sol * SU / entry, "entry_px": entry, "entry_mc": 0,
                                "peak_px": entry, "stop": -0.35, "tp1": 1.0, "tp1_done": False,
                                "thesis": "test", "rugcheck": 1, "risks": [], "realised_sol": 0.0,
                                "dex": "pumpswap", "url": "", "v": 2, **extra}
        mp.save(b, path)

    def price(self, mint, px, liq=200_000):
        self.market[mint] = {**self.market.get(mint, fake_pair(mint, px)), "priceUsd": str(px),
                             "liquidity": {"usd": liq}}


# --- costs ---------------------------------------------------------------------------------

class TestCosts(Env):
    def test_impact(self):
        p = fake_pair("X", 1.0, liq=200_000)  # one side = $100k = 1000 SOL
        self.assertAlmostEqual(mp.impact(0.25, p, SU), mp.SLIP_K * 0.25 / 1000)
        self.assertEqual(mp.impact(1, fake_pair("X", 1.0, liq=0), SU), 0.5)
        self.assertEqual(mp.impact(10_000, p, SU), 0.5)  # capped

    def test_buy_fill_and_round_trip(self):
        self.add_fake("A", 1.0)
        self.add_fake("B", 1.0)
        self.run_quiet(mp.gate, ["A", "B"])
        self.run_quiet(mp.buy, "A", "0.25", "t")
        pos = mp.load()["positions"]["A"]
        imp = mp.impact(0.25, self.market["A"], SU)
        self.assertAlmostEqual(pos["entry_px"], 1.0 * (1 + imp))
        self.assertAlmostEqual(pos["tokens"], 0.25 * (1 - mp.FEE) * SU / pos["entry_px"])
        self.run_quiet(mp.sell, "A", "1", "t")
        c = mp.load()["closed"][0]
        self.assertLess(c["pnl_sol"], 0)  # a flat round trip always loses the costs
        self.assertGreater(c["pnl_sol"], -0.25 * 0.05)
        self.assertAlmostEqual(mp.load()["cash_sol"], 10 - 0.25 + c["realised_sol"])

    def test_fee_and_size_constants(self):
        self.assertEqual(mp.FEE, 0.015)
        self.assertEqual(mp.MAX_POS_SOL, 0.25)
        self.assertEqual(mp.MAX_OPEN, 6)


class TestSolPrice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(mp, "SOL_CACHE", os.path.join(self.tmp.name, ".sol_usd"))
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_fallbacks(self):
        dex = [{"baseToken": {"address": mp.SOL_MINT}, "quoteToken": {"symbol": "USDC"},
                "liquidity": {"usd": 5e6}, "priceUsd": "91.5"}]

        def gecko_down(url):
            if "coingecko" in url:
                raise subprocess.CalledProcessError(22, "curl")
            return dex
        with mock.patch.object(mp, "get", gecko_down):
            self.assertEqual(mp.sol_usd(), 91.5)

        def all_down(url):
            raise subprocess.CalledProcessError(22, "curl")
        with mock.patch.object(mp, "get", all_down):
            self.assertEqual(mp.sol_usd(), 91.5)  # from the cache written above
            open(mp.SOL_CACHE, "w").write(f"91.5 {time.time() - 7 * 3600}")
            with self.assertRaises(RuntimeError):
                mp.sol_usd()

    def test_rejects_absurd_price(self):
        with mock.patch.object(mp, "get", lambda url: {"solana": {"usd": 0.0}}):
            with self.assertRaises(RuntimeError):
                mp.sol_usd()


# --- exits ---------------------------------------------------------------------------------

class TestExits(Env):
    def mark(self):
        self.run_quiet(mp.mark, quiet=True)
        return mp.load()

    def test_hard_stop(self):
        self.hold("A")
        self.price("A", 0.66)  # -34%: holds
        self.assertIn("A", self.mark()["positions"])
        self.price("A", 0.64)  # -36%: stopped
        b = self.mark()
        self.assertNotIn("A", b["positions"])
        self.assertIn("stop-loss", b["closed"][0]["exit_reason"])

    def test_take_profit_then_trailing(self):
        self.hold("A")
        self.price("A", 2.0)
        b = self.mark()
        pos = b["positions"]["A"]
        self.assertTrue(pos["tp1_done"])
        self.assertAlmostEqual(pos["tokens"], 0.25 * SU / 1.0 / 2)
        self.price("A", 3.0)
        self.mark()
        self.price("A", 1.81)  # just above 60% of the 3.0 peak
        self.assertIn("A", self.mark()["positions"])
        self.price("A", 1.79)
        b = self.mark()
        self.assertNotIn("A", b["positions"])
        self.assertIn("trailing stop", b["closed"][0]["exit_reason"])
        self.assertGreater(b["closed"][0]["pnl_sol"], 0)

    def test_no_hard_stop_after_take_profit(self):
        self.hold("A")
        self.price("A", 2.0)
        self.mark()
        self.price("A", 1.25)  # 37.5% off the 2.0 peak: under the trail, and the hard stop is off
        self.assertIn("A", self.mark()["positions"])

    def test_time_stop(self):
        old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=49)).strftime("%Y-%m-%d %H:%M UTC")
        young = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=47)).strftime("%Y-%m-%d %H:%M UTC")
        self.hold("A", opened=old)
        self.hold("B", opened=old)
        self.hold("C", opened=young)
        for m, px in (("A", 1.10), ("B", 1.25), ("C", 1.10)):
            self.price(m, px)
        b = self.mark()
        self.assertNotIn("A", b["positions"])  # 49h, +10%: out
        self.assertIn("B", b["positions"])     # 49h, +25%: above the +20% bar
        self.assertIn("C", b["positions"])     # 47h: too early
        self.assertIn("time stop", b["closed"][0]["exit_reason"])

    def test_missing_price_marks_to_zero_on_third_miss(self):
        self.hold("A")
        self.market.pop("A", None)
        self.assertIn("A", self.mark()["positions"])
        self.assertIn("A", self.mark()["positions"])
        b = self.mark()
        self.assertNotIn("A", b["positions"])
        self.assertEqual(b["closed"][0]["realised_sol"], 0)

    def test_one_miss_then_price_resets_counter(self):
        self.hold("A")
        self.market.pop("A", None)
        self.mark()
        self.mark()
        self.price("A", 1.0)
        self.assertEqual(self.mark()["positions"]["A"]["misses"], 0)

    def test_control_book_gets_same_exits(self):
        self.hold("A", path=mp.CONTROL)
        self.price("A", 0.5)
        self.mark()
        c = mp.load(mp.CONTROL)
        self.assertNotIn("A", c["positions"])
        self.assertIn("stop-loss", c["closed"][0]["exit_reason"])


# --- gate ----------------------------------------------------------------------------------

class TestGate(Env):
    def fails(self, n="gato", mutate=None):
        m = MINT[n]
        if mutate:
            mutate(self.rc[m])
        return mp.gate_one(m, self.market[m])

    def test_fixture_outcomes(self):
        self.assertEqual(self.fails("gato"), [])
        self.assertEqual(self.fails("rico"), [])
        self.assertEqual(self.fails("cbucks"), ["a wallet holds 15% of supply"])
        self.assertEqual(len(self.fails("wasted")), 1)
        self.assertTrue(self.fails("wasted")[0].startswith("copycat"))

    def assertFailsWith(self, mutate, text):
        f = self.fails(mutate=mutate)
        self.assertTrue(any(text in x for x in f), f"expected '{text}' in {f}")

    def test_authorities(self):
        self.assertFailsWith(lambda r: r.update(mintAuthority="X"), "authority")
        self.assertFailsWith(lambda r: r.update(freezeAuthority="X"), "authority")

    def test_token2022(self):
        for k in ("permanentDelegate", "transferHook", "nonTransferable"):
            self.reset()
            self.assertFailsWith(lambda r, k=k: r["token_extensions"].update({k: {"x": 1}}), k)
        self.reset()
        self.assertFailsWith(lambda r: r.update(transferFee={"pct": 5}), "transfer fee")
        self.reset()
        self.assertEqual(self.fails(mutate=lambda r: r.update(transferFee={"pct": 2})), [])

    def test_rugcheck_flags(self):
        self.assertFailsWith(lambda r: r.update(rugged=True), "rugged")
        self.reset()
        self.assertFailsWith(lambda r: r.update(risks=[{"name": "Creator history of rugged tokens", "level": "danger"}]),
                             "Creator history")
        self.reset()
        self.assertEqual(self.fails(mutate=lambda r: r.update(risks=[{"name": "Low amount of LP", "level": "warn"}])), [])

    def deepest(self, r):
        return max(r["markets"], key=lambda m: (m["lp"].get("quoteUSD") or 0) + (m["lp"].get("baseUSD") or 0))

    def test_pool(self):
        self.assertFailsWith(lambda r: self.deepest(r).update(marketType="meteoraDlmm"), "not a graduation pool")
        self.reset()
        self.assertFailsWith(lambda r: self.deepest(r)["lp"].update(lpLockedPct=50), "LP only 50% locked")
        self.reset()
        self.assertFailsWith(lambda r: r.update(markets=[]), "no pool data")

    def test_holders(self):
        def insider(r):
            s = r["token"]["supply"]
            r["topHolders"][0].update(insider=True, amount=int(s * 0.04))
            r["topHolders"][1].update(insider=True, amount=int(s * 0.04))
            r["topHolders"][3].update(insider=True, amount=int(s * 0.04))
            r["topHolders"][4].update(insider=True, amount=int(s * 0.04))
        self.assertFailsWith(insider, "insider wallets hold 16%")
        self.reset()
        self.assertFailsWith(lambda r: r.update(creatorBalance=int(r["token"]["supply"] * 0.11)), "creator holds 11%")
        self.reset()
        self.assertFailsWith(lambda r: r["token"].update(supply=0), "no supply data")

    def test_pool_wallet_is_not_a_holder(self):
        # The pool's own token account can hold a lot; it must not count as a whale.
        def pool_whale(r):
            pool = self.deepest(r)["pubkey"]
            r["topHolders"][0].update(owner=pool, amount=int(r["token"]["supply"] * 0.30))
        self.assertEqual(self.fails(mutate=pool_whale), [])

    def test_cant_check_means_fail(self):
        self.fail_urls = ["rugcheck.xyz"]
        self.assertTrue(self.fails()[0].startswith("RugCheck unavailable"))
        self.fail_urls = ["/latest/dex/search"]
        self.assertTrue(any("copycat check failed" in x for x in self.fails()))

    def test_copycat_ignores_dead_same_name_launches(self):
        m = MINT["wasted"]
        earlier = [q for q in self.search[m]["pairs"] if q["baseToken"]["address"] != m]
        for q in earlier:
            q["liquidity"] = {"usd": mp.COPY_MIN_LIQ - 1}
        self.assertEqual(self.fails("wasted"), [])

    def test_gate_records_passes_and_rejects(self):
        self.run_quiet(mp.gate, [MINT["gato"], MINT["cbucks"], "NOPAIR"])
        b = mp.load()
        self.assertIn(MINT["gato"], b["gate_pass"])
        self.assertNotIn(MINT["cbucks"], b["gate_pass"])
        r = b["rejects"][MINT["cbucks"]]
        self.assertEqual(r["fails"], ["a wallet holds 15% of supply"])
        self.assertEqual(r["moves"], {})
        self.assertNotIn("NOPAIR", b["rejects"])

    def test_old_passes_are_pruned_and_a_fail_revokes_a_pass(self):
        b = mp.load()
        b["gate_pass"] = {"OLD": time.time() - 3 * 3600, MINT["cbucks"]: time.time()}
        mp.save(b)
        self.run_quiet(mp.gate, [MINT["cbucks"]])
        self.assertEqual(mp.load()["gate_pass"], {})


# --- buy and control -----------------------------------------------------------------------

class TestBuy(Env):
    def setUp(self):
        super().setUp()
        for m in ("A", "B", "C"):
            self.add_fake(m, 1.0)

    def test_needs_fresh_gate_pass(self):
        with self.assertRaises(SystemExit):
            self.run_quiet(mp.buy, "A", "0.25", "t")
        b = mp.load()
        b["gate_pass"]["A"] = time.time() - (mp.GATE_TTL_H * 3600 + 1)
        mp.save(b)
        with self.assertRaises(SystemExit):
            self.run_quiet(mp.buy, "A", "0.25", "t")

    def test_size_cap_and_control(self):
        self.run_quiet(mp.gate, ["A", "B", "C"])
        self.run_quiet(mp.buy, "A", "1.0", "t")
        b, c = mp.load(), mp.load(mp.CONTROL)
        self.assertEqual(b["positions"]["A"]["cost_sol"], 0.25)
        self.assertEqual(b["positions"]["A"]["v"], 2)
        self.assertEqual(len(c["positions"]), 1)
        ctl = next(iter(c["positions"]))
        self.assertIn(ctl, ("B", "C"))  # never the pick itself
        self.assertEqual(c["positions"][ctl]["cost_sol"], 0.25)

    def test_control_never_the_pick(self):
        for _ in range(20):
            self.reset()
            for m in ("A", "B"):
                self.add_fake(m, 1.0)
            self.run_quiet(mp.gate, ["A", "B"])
            self.run_quiet(mp.buy, "A", "0.25", "t")
            self.assertEqual(list(mp.load(mp.CONTROL)["positions"]), ["B"])

    def test_no_control_when_pick_is_the_only_pass(self):
        self.run_quiet(mp.gate, ["A"])
        self.run_quiet(mp.buy, "A", "0.25", "t")
        self.assertEqual(mp.load(mp.CONTROL)["positions"], {})
        self.assertIn("no control entry", self.out.getvalue())

    def test_control_skips_coins_it_already_holds(self):
        self.hold("B", path=mp.CONTROL)
        self.run_quiet(mp.gate, ["A", "B", "C"])
        self.run_quiet(mp.buy, "A", "0.25", "t")
        self.assertEqual(sorted(mp.load(mp.CONTROL)["positions"]), ["B", "C"])

    def test_already_holding(self):
        self.run_quiet(mp.gate, ["A", "B"])
        self.run_quiet(mp.buy, "A", "0.25", "t")
        with self.assertRaises(SystemExit):
            self.run_quiet(mp.buy, "A", "0.25", "t")

    def test_max_open_counts_v2_only(self):
        for i in range(4):
            self.hold(f"L{i}", v=None)  # legacy v1 positions
            b = mp.load()
            b["positions"][f"L{i}"].pop("v")
            mp.save(b)
        for i in range(mp.MAX_OPEN - 1):
            self.hold(f"V{i}")
        self.run_quiet(mp.gate, ["A", "B"])
        self.run_quiet(mp.buy, "A", "0.25", "t")  # 6th v2 position: allowed despite 4 legacy
        with self.assertRaises(SystemExit):
            self.run_quiet(mp.buy, "B", "0.25", "t")


# --- shadow rejects and the report ---------------------------------------------------------

class TestRejects(Env):
    def test_scored_on_schedule(self):
        t0 = time.time()
        b = mp.load()
        b["rejects"] = {"R": {"symbol": "R", "at": t0 - 1.5 * 86400, "px": 1.0, "fails": ["x"], "moves": {}},
                        "G": {"symbol": "G", "at": t0 - 4.5 * 86400, "px": 1.0, "fails": ["x"], "moves": {}}}
        mp.save(b)
        self.price("R", 0.5)
        self.run_quiet(mp.mark, quiet=True)
        r = mp.load()["rejects"]
        self.assertEqual(r["R"]["moves"], {"1d": -0.5})       # 1.5 days: only the 1-day score
        self.assertEqual(r["G"]["moves"], {"1d": -1.0, "3d": -1.0})  # gone, a day past due: dead

    def test_not_scored_while_missing_but_not_overdue(self):
        b = mp.load()
        b["rejects"] = {"R": {"symbol": "R", "at": time.time() - 1.5 * 86400, "px": 1.0, "fails": ["x"], "moves": {}}}
        mp.save(b)
        self.run_quiet(mp.mark, quiet=True)
        self.assertEqual(mp.load()["rejects"]["R"]["moves"], {})


class TestReport(Env):
    def test_arms_and_report(self):
        for m in ("A", "B"):
            self.add_fake(m, 1.0)
        self.run_quiet(mp.gate, ["A", "B"])
        self.run_quiet(mp.buy, "A", "0.25", "t")
        self.price("A", 2.0)
        self.run_quiet(mp.mark, quiet=True)
        b, c = mp.load(), mp.load(mp.CONTROL)
        n, w, pnl, cost = mp.arm(b, self.market, SU, True)
        self.assertEqual((n, cost), (0, 0.25))
        self.assertGreater(pnl, 0)
        md = open(mp.REPORT).read()
        for s in ("## v2 test", "| Picks |", "| Control |", "Shadow rejects", "## Open positions"):
            self.assertIn(s, md)

    def test_median(self):
        self.assertIsNone(mp.median([]))
        self.assertEqual(mp.median([3, 1, 2]), 2)
        self.assertEqual(mp.median([1, 2, 3, 4]), 2.5)


# --- replay: a fixed price path must give exactly the recorded trades -----------------------

GOLDEN = os.path.join(FIX, "replay_golden.json")
PATH = {  # price per tick for each coin
    "UP": [1.0, 1.3, 2.1, 2.6, 3.2, 2.4, 1.85, 1.7],     # take-profit, then trailing stop
    "DOWN": [1.0, 0.9, 0.8, 0.7, 0.62, 0.6, 0.6, 0.6],   # hard stop
    "FLAT": [1.0, 1.05, 0.98, 1.02, 1.0, 1.01, 0.99, 1.0],  # holds
    "GONE": [1.0, 1.1, None, None, None, None, None, None],  # vanishes: zero on the 3rd miss
}


class TestReplay(Env):
    def run_path(self):
        for m in PATH:
            self.add_fake(m, 1.0)
        self.run_quiet(mp.gate, list(PATH))
        for m in PATH:
            self.run_quiet(mp.buy, m, "0.25", "replay")
        for tick in range(1, len(PATH["UP"])):
            for m, ps in PATH.items():
                if ps[tick] is None:
                    self.market.pop(m, None)
                else:
                    self.price(m, ps[tick])
            self.run_quiet(mp.mark, quiet=True)
        b = mp.load()
        return {"cash_sol": round(b["cash_sol"], 9),
                "open": sorted(b["positions"]),
                "closed": [(x["mint"], x["exit_reason"], round(x["pnl_sol"], 9)) for x in b["closed"]]}

    def test_replay_matches_golden(self):
        got = self.run_path()
        if os.environ.get("REGEN_GOLDEN"):
            json.dump(got, open(GOLDEN, "w"), indent=2)
        want = json.load(open(GOLDEN))
        self.assertEqual(got["open"], want["open"])
        self.assertEqual([tuple(x) for x in want["closed"]], [tuple(x) for x in got["closed"]])
        self.assertAlmostEqual(got["cash_sol"], want["cash_sol"], places=9)

    def test_books_add_up(self):
        self.run_path()
        for path in (None, mp.CONTROL):
            b = mp.load(path)
            spent = sum(x["cost_sol"] for x in b["closed"]) + sum(x["cost_sol"] for x in b["positions"].values())
            got_back = sum(x["realised_sol"] for x in b["closed"]) + sum(x["realised_sol"] for x in b["positions"].values())
            self.assertAlmostEqual(b["cash_sol"], b["start_sol"] - spent + got_back, places=9)
            for x in b["closed"]:
                self.assertAlmostEqual(x["pnl_sol"], x["realised_sol"] - x["cost_sol"], places=9)


# --- rules text and code agree --------------------------------------------------------------

class TestRulesText(unittest.TestCase):
    def test_claude_md_matches_code(self):
        t = open(os.path.join(os.path.dirname(FIX), "..", "CLAUDE.md")).read()
        self.assertIn("0.25 SOL", t)
        self.assertIn("1.5% fee", t)
        self.assertIn("No wallet, no keys, no real orders", t)


if __name__ == "__main__":
    unittest.main()
