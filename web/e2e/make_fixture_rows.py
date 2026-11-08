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
out = HERE / "fixture_rows.json"
out.write_text(json.dumps(rows, ensure_ascii=False, default=str),
               encoding="utf-8")
print("wrote", out, "—", len(p["command_brief"]["page5"]["sources"]),
      "sources")
