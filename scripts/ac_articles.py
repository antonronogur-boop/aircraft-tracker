# -*- coding: utf-8 -*-
"""Cikk-betolto a hivatkozott cikkekhez — modellfuggoseg (anthropic) nelkul.

A generator (generate_weekly_report.py) es a backfill
(backfill_command_brief.py) ugyanezt hasznalja, igy a backfill nem huzza be
a generator modell-importjait.
"""

FIELDS = ("article_id,title,url,source_id,publish_date,collected_date,"
          "short_summary")


def load_articles(db, article_ids):
    """Csak a hivatkozott cikkek (cim, URL, PUBLIKACIOS datum, gyujtesi
    datum, rovid osszefoglalo) — 100-as csomagokban, nem a teljes tabla."""
    ids = sorted({a for a in article_ids if a})
    out = {}
    for i in range(0, len(ids), 100):
        chunk = ",".join('"{}"'.format(x.replace('"', '')) for x in
                         ids[i:i + 100])
        for a in db.select("ac_articles", {
                "select": FIELDS,
                "article_id": "in.({})".format(chunk)}):
            out[a["article_id"]] = a
    return out
