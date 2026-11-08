# -*- coding: utf-8 -*-
"""A Command Brief publikacios retege (draft) — Python oldal.

A draftot a webes szerkeszto kezeli (web/src/lib/briefDraft.ts); a tarolasa
az ac_reports.payload.command_brief_draft kulcs alatt van (uj tabla /
kezi SQL nelkul). A Python irok (generator --restate, backfill) a teljes
payloadot ujrairjak, ezert iras ELOTT ujraolvassak az aktualis draftot es
valtozatlanul atviszik — a szerkesztett publikacios szoveg, a jovahagyas es
a kiadasok (releases) igy nem vesznek el. Az elemzoi reteget a draft nem
modositja; a draftot a Python csak egy audit-bejegyzessel egesziti ki
("rebase": az alap brief ujraepult). Hogy a jovahagyas ervenyes-e, azt a
web a generalt brief hash-ebol donti el (ujra-jovahagyas kell).
"""
from datetime import datetime, timezone

DRAFT_KEY = "command_brief_draft"


def current_draft(db, week_label):
    try:
        rows = db.select("ac_reports", {
            "select": "draft:payload->" + DRAFT_KEY,
            "week_label": "eq." + str(week_label)})
    except Exception:  # noqa: BLE001
        return None
    if not rows:
        return None
    r = rows[0]
    return r.get("draft") or (r.get("payload") or {}).get(DRAFT_KEY)


def carry_draft(db, week_label, payload, reason):
    """A tarolt draft atvitele az ujrairt payloadba (audit-bejegyzessel)."""
    d = current_draft(db, week_label)
    if not d:
        payload.pop(DRAFT_KEY, None)
        return None
    d.setdefault("audit", []).append({
        "rev": d.get("revision") or 0,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actor": "system",
        "action": "rebase",
        "note": "generated brief rebuilt: {}".format(reason)})
    payload[DRAFT_KEY] = d
    return d
