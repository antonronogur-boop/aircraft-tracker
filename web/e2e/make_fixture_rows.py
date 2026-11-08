# -*- coding: utf-8 -*-
"""Szintetikus E2E-sorok (web/e2e/fixture_rows.json) ujrageneralasa.

  python3 web/e2e/make_fixture_rows.py

2026-W46: a szintetikus jelentes + Command Brief (a jelenlegi kodbol).
2026-W45: ugyanaz brief NELKUL (a "regi het -> 404, nem hibas fajl" teszthez).
Adatbazist nem hasznal; SYNTHETIC TEST DATA.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
os.environ.setdefault("SUPABASE_URL", "http://localhost:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "unused")

import test_command_brief as T  # noqa: E402
import ac_command_brief as B  # noqa: E402

p = T.fixture()
cov = T.coverage_for()
p["coverage"] = cov
p["command_brief"] = B.build_command_brief(json.loads(json.dumps(p)),
                                           T.COUNTRIES, coverage=cov)
legacy = T.fixture()
legacy["week_label"] = "2026-W45"
legacy["report_meta"].update({"week_label": "2026-W45",
                              "period_start": "2026-10-27",
                              "period_end": "2026-11-03"})
rows = [
    {"report_id": 2, "week_label": "2026-W46", "period_start": "2026-11-04",
     "period_end": "2026-11-10", "generated_at": "2026-11-11T05:20:00+00:00",
     "payload": p},
    {"report_id": 1, "week_label": "2026-W45", "period_start": "2026-10-27",
     "period_end": "2026-11-03", "generated_at": "2026-11-04T05:20:00+00:00",
     "payload": legacy},
]
# STRESS (2026-W40): erosebb het — 32 fuggetlen lineage, 40 publikacio + 2
# kontextus-forras. A kanonikus PDF-nek igy is 5 oldalnak kell maradnia,
# olvashato betumerettel, egyetlen bizonyitek elhagyasa nelkul.
stress = json.loads(json.dumps(p))
sb = stress["command_brief"]
pubs = ["Ministry of National Defence", "Defence24", "Militarnyi", "Aviation Week", "Janes",
        "Breaking Defense", "The Aviationist", "Defense News", "Air & Space Forces Magazine",
        "Airforce Technology", "Overt Defense", "Army Recognition"]
items = ["KJ-01", "KJ-02", "KJ-03", "p.2 Poland", "p.2 Romania", "p.2 Serbia", "p.2 Ukraine",
         "p.2 Hungary", "p.2 Slovakia", "p.3 Israel", "p.3 Algeria", "p.4 China", "p.4 Japan",
         "p.4 India", "p.4 Australia", "p.4 outlook"]
srcs, n = [], 0
for li in range(32):
    k = 1 + (2 if li % 4 == 0 else 1 if li % 3 == 0 else 0)   # 40 publikacio
    for j in range(k):
        n += 1
        srcs.append({
            "id": "S-%02d" % n, "title": "Synthetic stress publication %d on lineage %d" % (n, li + 1),
            "url": "https://example.org/stress/%d" % n, "source_name": pubs[(li + j) % len(pubs)],
            "source_type": "Ministry of defence" if j == 0 and li % 2 == 0 else "Specialist defence media",
            "tier": "Tier 1" if j == 0 and li % 2 == 0 else "Tier 3",
            "tier_rank": 1 if j == 0 and li % 2 == 0 else 3, "language": "en",
            "published": "2026-10-%02d" % (1 + (li + j) % 28), "published_basis": "feed",
            "country": "Poland", "state_controlled": False, "lineage": "L-%02d" % (li + 1),
            "evidence_role": "EVIDENCE", "role": "Corroborating", "used_by": [items[li % len(items)], "p.4 outlook"],
            "context_for": [], "supports": {}, "subject": "Capability milestone %d (stress)" % (li + 1)})
for c in range(2):
    n += 1
    srcs.append({"id": "S-%02d" % n, "title": "Context article %d" % c, "url": "https://example.org/ctx/%d" % c,
                 "source_name": "Defence Blog", "source_type": "Specialist defence media", "tier": "Tier 3",
                 "tier_rank": 3, "language": "en", "published": "2026-10-20", "published_basis": "feed",
                 "country": "Poland", "state_controlled": False, "lineage": None, "evidence_role": "CONTEXT_ONLY",
                 "role": "Context — not cited as evidence", "used_by": [], "context_for": ["p.2 Poland"], "supports": {}})
sb["page5"]["sources"] = srcs
sb["page5"]["lineages"] = B.lineage_register(srcs)
for k in ("week_label",):
    stress[k] = sb[k] = sb["meta"][k] = stress["report_meta"][k] = "2026-W40"
stress["report_meta"].update({"period_start": "2026-09-30", "period_end": "2026-10-06"})
sb["meta"].update({"period_start": "2026-09-30", "period_end": "2026-10-06"})
rows.append({"report_id": 0, "week_label": "2026-W40", "period_start": "2026-09-30",
             "period_end": "2026-10-06", "generated_at": "2026-10-07T05:20:00+00:00", "payload": stress})

out = HERE / "fixture_rows.json"
out.write_text(json.dumps(rows, ensure_ascii=False, default=str),
               encoding="utf-8")
print("wrote", out, "—", len(p["command_brief"]["page5"]["sources"]),
      "sources")
