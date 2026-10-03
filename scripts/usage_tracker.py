# -*- coding: utf-8 -*-
"""
usage_tracker.py — MENNYI TOKENT EGET EGY FUTAS?

A modell minden valaszban visszaadja, hany tokent hasznalt — es ezt a
projekt eddig MINDENHOL eldobta. Emiatt a "mire megy el a penz" kerdesre
csak becsulni lehetett, merni nem.

HASZNALAT — scriptenkent EGY sor valtozik:

    import usage_tracker as usage
    client = usage.wrap(anthropic.Anthropic())      # <- ez az egy sor
    ...
    usage.report()                                   # emberi osszegzes
    db.finish_run(run, "success", n, details=usage.summary())

A `wrap()` egy atlatszo burkolat: a hivasok, a parameterek es a
visszateresi ertek valtozatlanok, tehat egyetlen hivasi helyet sem kell
atirni. Ezert fogja a RETRY-kat is — azok ugyanugy penzbe kerulnek, es
pont azok maradnanak ki, ha kezzel szurnank be a meresi pontokat.

SOSEM DOB KIVETELT. Egy meresi hiba nem allithat meg egy pipeline-futast:
a merés a futas megfigyelese, nem a resze.

ARAK: a token a teny, a penz a szamitas. Arakat nem drotozunk a kodba —
valtoznak, es egy elavult ar rosszabb a semminel. Ha letezik a
`config/model_prices.json` fajl, a riport penzt is mond; ha nem, csak
tokent. A fajl alakja (ar millio tokenenkent, USD):

    {
      "claude-sonnet-4-6": {
        "input": 3.0, "output": 15.0,
        "cache_write": 3.75, "cache_read": 0.30
      },
      "claude-haiku-4-5-20251001": { ... }
    }

A pontos ertekeket a hivatalos arlistabol masold be — szandekosan nem
talalom ki oket.
"""
import json
import os
from collections import defaultdict
from pathlib import Path

__all__ = ["wrap", "record", "summary", "report", "reset", "self_test"]


def _price_table():
    """A `config/model_prices.json` tartalma, vagy ures dict."""
    here = Path(__file__).resolve().parent
    for parent in [here] + list(here.parents)[:4]:
        candidate = parent / "config" / "model_prices.json"
        if candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as fh:
                    return json.load(fh), str(candidate)
            except (OSError, ValueError):
                return {}, None
    return {}, None


class Tracker(object):
    """Modellenkent osszesit. A negy token-fajtat KULON tartja."""

    FIELDS = ("input", "output", "cache_write", "cache_read")

    def __init__(self):
        self.reset()

    def reset(self):
        self.by_model = defaultdict(lambda: dict(
            calls=0, input=0, output=0, cache_write=0, cache_read=0))
        self.failed_calls = 0

    def record(self, model, msg):
        """Egy valasz token-adatai. Barmilyen hiba eseten csendben kihagyja."""
        try:
            u = getattr(msg, "usage", None)
            if u is None:
                self.failed_calls += 1
                return
            key = model or getattr(msg, "model", None) or "(unknown)"
            row = self.by_model[key]
            row["calls"] += 1
            row["input"] += int(getattr(u, "input_tokens", 0) or 0)
            row["output"] += int(getattr(u, "output_tokens", 0) or 0)
            # A cache-mezok csak akkor leteznek, ha a hivas hasznalt
            # prompt-cache-t. A hianyuk NEM nulla fogyasztas, hanem "nem volt
            # cache" — a riport ezert kulon sorban mutatja.
            row["cache_write"] += int(getattr(u, "cache_creation_input_tokens", 0) or 0)
            row["cache_read"] += int(getattr(u, "cache_read_input_tokens", 0) or 0)
        except Exception:  # noqa: BLE001 — lasd a fajl fejlecet
            self.failed_calls += 1

    # ── kimenet ──────────────────────────────────────────────────────────

    def totals(self):
        out = dict(calls=0, input=0, output=0, cache_write=0, cache_read=0)
        for row in self.by_model.values():
            for k in out:
                out[k] += row[k]
        return out

    def cost(self, prices):
        """Becsult koltseg modellenkent, USD. None, ha nincs ar a modellhez."""
        result = {}
        for model, row in self.by_model.items():
            p = prices.get(model)
            # A kitoltetlen sablon (null ertekek) ugyanannyit er, mint a
            # hianyzo ar: inkabb "nincs ar", mint egy magabiztos nulla.
            if not isinstance(p, dict) or p.get("input") is None:
                result[model] = None
                continue
            p = {k: (v or 0) for k, v in p.items() if isinstance(v, (int, float))}
            usd = (
                row["input"] * p.get("input", 0)
                + row["output"] * p.get("output", 0)
                + row["cache_write"] * p.get("cache_write", p.get("input", 0))
                + row["cache_read"] * p.get("cache_read", 0)
            ) / 1_000_000.0
            # 6 tizedes, nem 4: egy futas koltsege lehet nehany ezred dollar,
            # es negy tizedesre kerekitve az osszegzeskor latszodo hiba lenne.
            # A megjelenites kulon formaz (lasd report()).
            result[model] = round(usd, 6)
        return result

    def summary(self):
        """A `pipeline_runs.details` jsonb mezobe szant alak."""
        prices, _ = _price_table()
        costs = self.cost(prices)
        known = [c for c in costs.values() if c is not None]
        return {
            "tokens_by_model": {m: dict(r) for m, r in self.by_model.items()},
            "tokens_total": self.totals(),
            "estimated_usd_by_model": costs,
            "estimated_usd_total": round(sum(known), 4) if known else None,
            "unrecorded_calls": self.failed_calls,
        }

    def report(self, title="TOKEN-FOGYASZTAS"):
        prices, price_path = _price_table()
        costs = self.cost(prices)
        t = self.totals()

        print("\n" + title)
        print("-" * 72)
        if not self.by_model:
            print("  (egyetlen modellhivas sem tortent)")
            return

        for model in sorted(self.by_model):
            r = self.by_model[model]
            print("  {}".format(model))
            print("    hivas: {:>6}   bemenet: {:>9,}   kimenet: {:>8,}".format(
                r["calls"], r["input"], r["output"]))
            if r["cache_write"] or r["cache_read"]:
                # Ez a ket szam mondja meg, MUKODIK-E a prompt-cache. Ha a
                # cache_read nulla sok hivas utan is, a cache nem lep eletbe
                # (tul rovid elotag), es a beallitas csak dekoracio.
                print("    cache iras: {:>7,}   cache olvasas: {:>9,}".format(
                    r["cache_write"], r["cache_read"]))
            usd = costs.get(model)
            if usd is not None:
                print("    becsult koltseg: ${:.4f}".format(usd))
            else:
                print("    becsult koltseg: nincs ar ehhez a modellhez")

        print("  " + "-" * 70)
        print("  OSSZESEN: {} hivas, {:,} bemeneti + {:,} kimeneti token".format(
            t["calls"], t["input"] + t["cache_write"] + t["cache_read"], t["output"]))

        known = [c for c in costs.values() if c is not None]
        if known:
            print("  BECSULT KOLTSEG: ${:.4f}  (ar: {})".format(sum(known), price_path))
        else:
            print("  Koltseg nem szamolhato: hianyzik a config/model_prices.json")
            print("  (a token-szamok fentebb attol meg pontosak)")
        if self.failed_calls:
            print("  [!] {} hivas token-adata nem volt kiolvashato".format(self.failed_calls))


# ── modul-szintu alapertelmezett tracker ────────────────────────────────
_default = Tracker()


def reset():
    _default.reset()


def record(model, msg):
    _default.record(model, msg)


def summary():
    return _default.summary()


def report(title="TOKEN-FOGYASZTAS"):
    _default.report(title)


# ── atlatszo burkolat ───────────────────────────────────────────────────

class _Messages(object):
    def __init__(self, inner, tracker):
        self._inner = inner
        self._tracker = tracker

    def create(self, *args, **kwargs):
        msg = self._inner.create(*args, **kwargs)
        self._tracker.record(kwargs.get("model"), msg)
        return msg

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _Client(object):
    def __init__(self, inner, tracker):
        self._inner = inner
        self.messages = _Messages(inner.messages, tracker)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def wrap(client, tracker=None):
    """Burkolt kliens, amely minden valasz token-adatat feljegyzi.

    Ha a burkolas barmiert nem sikerul (mas SDK-verzio, valtozott
    szerkezet), az EREDETI klienst adja vissza: a meres elmaradasa nem
    allithatja meg a futast.
    """
    try:
        return _Client(client, tracker or _default)
    except Exception:  # noqa: BLE001
        return client


# ── self-test ───────────────────────────────────────────────────────────

class _FakeUsage(object):
    def __init__(self, i, o, cw=0, cr=0):
        self.input_tokens = i
        self.output_tokens = o
        self.cache_creation_input_tokens = cw
        self.cache_read_input_tokens = cr


class _FakeMsg(object):
    def __init__(self, usage):
        self.usage = usage


class _FakeInnerMessages(object):
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return _FakeMsg(_FakeUsage(1000, 200, cw=500, cr=1500))


class _FakeInnerClient(object):
    def __init__(self):
        self.messages = _FakeInnerMessages()


def self_test():
    ok = [True]

    def check(label, cond):
        print("  {} {}".format("OK  " if cond else "BUKO", label))
        if not cond:
            ok[0] = False

    t = Tracker()
    inner = _FakeInnerClient()
    client = wrap(inner, t)

    client.messages.create(model="claude-sonnet-4-6", max_tokens=10)
    client.messages.create(model="claude-sonnet-4-6", max_tokens=10)
    client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10)

    check("a burkolat tovabbhivja az eredetit", inner.messages.calls == 3)
    check("modellenkent kulon szamol", set(t.by_model) == {
        "claude-sonnet-4-6", "claude-haiku-4-5-20251001"})
    check("a hivasokat osszegzi", t.by_model["claude-sonnet-4-6"]["calls"] == 2)
    check("a bemeneti tokent osszegzi", t.by_model["claude-sonnet-4-6"]["input"] == 2000)
    check("a cache-mezoket kulon tartja",
          t.by_model["claude-sonnet-4-6"]["cache_read"] == 3000
          and t.by_model["claude-sonnet-4-6"]["cache_write"] == 1000)
    check("az osszesites stimmel", t.totals()["calls"] == 3)

    # Koltseg: sajat arlistaval, a fajltol fuggetlenul.
    usd = t.cost({"claude-sonnet-4-6": {
        "input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30}})
    # 2000*3 + 400*15 + 1000*3.75 + 3000*0.30 = 6000+6000+3750+900 = 16650 / 1e6
    # 2026-10-03: ez a sor elobukott, es a TESZT volt a hibas, nem a kod —
    # 1e-6 toleranciat kert egy 4 tizedesre kerekitett ertektol. A kerekites
    # azota 6 tizedes (az osszegzes miatt), a tolerancia pedig ahhoz igazodik.
    check("a koltsegszamitas helyes", abs(usd["claude-sonnet-4-6"] - 0.01665) < 1e-6)
    check("ismeretlen modellre nincs kitalalt ar",
          t.cost({})["claude-haiku-4-5-20251001"] is None)

    # Hibas valasz nem dobhat kivetelt.
    t.record("x", object())
    check("a token nelkuli valasz nem szall el", t.failed_calls == 1)

    s = t.summary()
    check("a summary jsonb-be irhato", json.dumps(s) and "tokens_total" in s)

    print("\nSELF-TEST: {}".format("MINDEN RENDBEN" if ok[0] else "VAN BUKOTT ELLENORZES"))
    return 0 if ok[0] else 1


if __name__ == "__main__":
    import sys
    sys.exit(self_test())
