# -*- coding: utf-8 -*-
"""
validate_relevance_gate.py — mit dobna ki az olcso kapu?

A 'haiku_gate' forrasok mar felcimkezett cikkein (processed = relevans,
irrelevant = irrelevans) lefuttatja az ELES kaput (a scripts/process_articles.py
-bol, fajlutvonal szerint betoltve), es megmondja, hany RELEVANS cikket dobna el.
Nem ir semmit.
"""
import importlib.util
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import supabase_client as db  # noqa: E402
import source_policy  # noqa: E402
import usage_tracker as usage  # noqa: E402

ARTICLES = "ac_articles"
LIVE = HERE / "process_articles.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("_live_pa", LIVE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.cheap_relevance_gate


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 200
    half = limit // 2
    gated = [sid for sid, e in source_policy.load()["policies"].items()
             if e["policy"] == source_policy.HAIKU_GATE]
    flt = "in.({})".format(",".join(gated))
    sel = "article_id,source_id,title,short_summary"
    rel = db.select(ARTICLES, {"select": sel, "source_id": flt, "status": "eq.processed",
                               "order": "collected_date.desc", "limit": "600"})
    irr = db.select(ARTICLES, {"select": sel, "source_id": flt, "status": "eq.irrelevant",
                               "order": "collected_date.desc", "limit": "600"})
    rng = random.Random(20261003)
    rng.shuffle(rel); rng.shuffle(irr)
    rel, irr = rel[:half], irr[:half]

    import anthropic
    client = usage.wrap(anthropic.Anthropic())
    gate = load_gate()

    killed = [a for a in rel if gate(client, a) is False]
    caught = sum(1 for a in irr if gate(client, a) is False)

    print("validate_relevance_gate.py  [{}]".format(ARTICLES))
    print("=" * 72)
    print("  RELEVANS, amit a kapu eldobna:   {} / {}  ({:.1f}%)".format(
        len(killed), len(rel), 100.0 * len(killed) / max(1, len(rel))))
    print("  IRRELEVANS, amit a kapu kiszur:  {} / {}  ({:.1f}%)".format(
        caught, len(irr), 100.0 * caught / max(1, len(irr))))
    if killed:
        print("\n  A tevesen eldobott cimek (ezt kell elolvasni, nem csak a szazalekot):")
        for a in killed[:25]:
            print("   - " + (a.get("title") or "")[:100].replace("\n", " "))
    usage.report("A VALIDACIO SAJAT KOLTSEGE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
