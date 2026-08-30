# -*- coding: utf-8 -*-
"""Generate the weekly AIR POWER DEVELOPMENT INTELLIGENCE BRIEF -> ac_reports.

v3 — a W33/W34 osszehasonlitas alapjan javitott valtozat.

Ami a v2-ben mar helyes volt es marad:
  * az EVENT_DATE alapjan valogat, es kizarja a periodus utani datumokat;
  * ertektipusonkent osszegez (firm / ceiling / DSCA-max kulon), arfolyam-evvel;
  * darabszamot kepesseg-domainenkent bont;
  * a fo terméket a KEPESSEG-VALTOZAS koré epiti;
  * automatikus analitikai QA-t futtat, atirat, es visszatart.

Ami v3-ban UJ — mindegyik egy konkret, a ket jelentesben azonositott hibara:

  1. PROGRAMME-REteg. Egy ujabb cikk ugyanarrol a programrol nem ad hozza
     darabszamot. (Lengyel AH-64E 190 -> 284 -> 286.)
  2. WoW A PUBLIKALT ELOZO ERTEKBOL. A W33 18-at irt, a W34 "22 (+0 WoW)"-t;
     ket egymast koveto het ugyanazon metrikaja +4. Az ok: a W34 ujraszamolta
     az elozo hetet a sajat, kesobbi adatallapotabol. Most a publikalt szam az
     osszehasonlitasi alap, es a drift LATHATO.
  3. STADIUM-VISSZAIRAS. Az elemzoi downgrade visszahat az esemenyekre, igy az
     ORBAT nem irhat "Contract signed x24"-et arra, amit a szoveg
     negotiationnek nevez.
  4. VARIANS-BIZTOS ORBAT es programme-tudatos baseline.
  5. SINCE LAST WEEK — longitudinalis diff az elozo publikalt jelentesbol.
  6. BRIEFING VIEW — 4 slide-os szobeli briefinghez, a 13 oldalas jelentes
     mellett (az marad a reference product).

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ANTHROPIC_API_KEY
Usage: python scripts\\generate_weekly_report.py [--dry-run]
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402
import ac_intel  # noqa: E402
import ac_programmes as acprog  # noqa: E402

DAY = timedelta(days=1)
METHODOLOGY_VERSION = "v3.0"


def load_events(since_iso):
    """Szeles betoltes a gyujtes ideje szerint; az idobeli besorolast utana az
    event_date vegzi (a friss cikk nem tesz egy regi esemenyt hetive)."""
    return db.select("ac_events", {
        "select": "*", "review_status": "neq.rejected",
        "created_at": "gte." + since_iso, "order": "created_at.desc"})


def load_prior_report(current_week):
    """Az elozo PUBLIKALT jelentes + annak rogzitett metrikai.

    Ez a WoW-osszehasonlitas alapja. Ha nincs elozo jelentes, a WoW nem
    szamolhato — es ezt ki is irjuk, nem +0-nak mutatjuk.
    """
    try:
        rows = db.select("ac_reports", {
            "select": "week_label,period_start,period_end,payload",
            "week_label": "neq." + current_week,
            "order": "period_end.desc", "limit": "1"})
    except Exception as exc:  # noqa: BLE001
        print("  [warn] prior report unavailable: {}".format(str(exc)[:120]))
        return None, None
    if not rows:
        return None, None
    prior = rows[0]
    payload = prior.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            payload = None
    metrics = None
    try:
        m = db.select("ac_report_metrics", {
            "select": "*", "week_label": "eq." + str(prior.get("week_label"))})
        metrics = m[0] if m else None
    except Exception:  # noqa: BLE001
        metrics = None
    if payload is not None:
        payload.setdefault("week_label", prior.get("week_label"))
    return payload, metrics


def resolve_programmes(events, programmes):
    """Az esemenyek programhoz kotese es a programallapot frissitese.

    Ez a fuggveny NEM ir adatbazisba — a jelentes idejere allitja elo a
    konzisztens kepet, es visszaadja a javasolt program-patcheket, hogy a
    kulon futtatando reconcile-script alkalmazhassa oket.
    """
    by_id = {p.get("programme_id"): dict(p) for p in (programmes or [])}
    proposed, unlinked = {}, []
    for e in events:
        if e.get("programme_id") and e["programme_id"] in by_id:
            continue
        found, why = acprog.find_programme(e, list(by_id.values()))
        if found:
            e["programme_id"] = found.get("programme_id")
            continue
        # Nincs meglevo program: javaslunk egyet, de NEM hozunk letre.
        if not (e.get("country_id") and e.get("type_id")):
            unlinked.append({"event_id": e.get("event_id"), "reason": why})
            continue
        kind = acprog.kind_from_event(e)
        year = None
        d = ac_intel.parse_day(e.get("event_date"))
        if d:
            year = d.year
        key = acprog.programme_key(
            e.get("country_id"), e.get("type_id"), e.get("variant_raw"),
            e.get("service"), kind, year)
        e["programme_id"] = key
        e["_programme_proposed"] = True
        proposed.setdefault(key, {
            "programme_id": key, "country_id": e.get("country_id"),
            "type_id": e.get("type_id"),
            "variant": e.get("variant_raw"), "service": e.get("service"),
            "programme_kind": kind, "lifecycle_stage": None,
            "canonical_quantity": None, "review_status": "active",
            "title": "{} {}{}".format(
                (e.get("country_id") or "?").upper(),
                e.get("variant_raw") or e.get("type_id") or "?",
                " ({})".format(acprog.PROGRAMME_KINDS.get(kind, kind))
                if kind != "acquisition" else ""),
            "_events": [],
        })
        proposed[key]["_events"].append(e.get("event_id"))
        by_id[key] = proposed[key]

    # A baseline-delta minden esemenyre kiszamol — ALAPERTELMEZESBEN 0.
    # A programot MINDIG atadjuk: program nelkul az on_order_delta 0-t ad,
    # mert egy nem kotott esemenyrol nem tudjuk, ujramondas-e.
    deltas = []
    for e in events:
        prog = by_id.get(e.get("programme_id") or "")
        delta, why = acprog.on_order_delta(e, prog, e.get("summary"))
        e["on_order_delta"] = delta
        e["on_order_delta_reason"] = why
        if e.get("quantity_claimed") in (None, "") and e.get("quantity"):
            e["quantity_claimed"] = e.get("quantity")
        if delta:
            deltas.append((e.get("event_id"), e.get("programme_id"), delta))
    return by_id, proposed, unlinked, deltas


def main(dry_run=False):
    run = None if dry_run else db.start_run("ac_weekly_report")
    try:
        now = datetime.now(timezone.utc)
        naive_now = now.replace(tzinfo=None)
        wk_start = naive_now - 7 * DAY
        trend_start = naive_now - 35 * DAY
        week_label = "{}-W{:02d}".format(*now.isocalendar()[:2])

        # A gyujtesi ablak szelesebb (60 nap), mert egy most beerkezett cikk
        # regebbi esemenyrol is szolhat — azt viszont NEM e hetinek soroljuk be.
        raw = load_events((now - 60 * DAY).isoformat())

        countries = {c["country_id"]: c for c in db.select(
            "ac_countries", {"select": "country_id,name,region"})}
        types = {t["type_id"]: t for t in db.select(
            "ac_aircraft_types", {"select": "type_id,name,category"})}
        articles = {a["article_id"]: a for a in db.select(
            "ac_articles", {"select": "article_id,title,url,source_id,"
                                      "publish_date"})}
        fleets = db.select("ac_fleets", {
            "select": "country_id,type_id,fleet_status,quantity,variant,"
                      "service,baseline_scope"})
        try:
            programmes = db.select("ac_programmes", {"select": "*"})
        except Exception as exc:  # noqa: BLE001
            programmes = []
            print("  [warn] ac_programmes unavailable ({}) — run "
                  "supabase/add_programme_layer.sql; falling back to "
                  "event-only mode".format(str(exc)[:100]))

        def day(e):
            return ac_intel.effective_day(e)

        this_week, prev_week, prev_4wk, future_dated, undated = [], [], [], [], []
        for e in raw:
            d = day(e)
            if d is None:
                undated.append(e)
                continue
            if d > naive_now:
                future_dated.append(e)
            elif d >= wk_start:
                this_week.append(e)
            elif d >= trend_start:
                prev_4wk.append(e)
                if d >= naive_now - 14 * DAY:
                    prev_week.append(e)

        if future_dated:
            print("  Excluded {} event(s) dated beyond the period end.".format(
                len(future_dated)))

        # ------------------------------------------------------------------
        # EVIDENCIA-IDOREND: a regi esemeny UJ IGAZOLASA nem e heti esemeny
        # ------------------------------------------------------------------
        # A W34-ben a 2025-ben elvesztett A-100LL a het "capability
        # development"-jekent jelent meg. Ez nem feltetlenul hiba — 2026-W34-ben
        # jott az uj, vizualis megerosites —, de MEG KELL KULONBOZTETNI.
        confirmations = []
        for e in raw:
            occurred = ac_intel.parse_day(e.get("event_date"))
            fresh = (ac_intel.parse_day(e.get("new_evidence_at"))
                     or ac_intel.parse_day(e.get("created_at")))
            if not occurred or not fresh:
                continue
            if occurred < wk_start and fresh >= wk_start:
                e["evidence_kind"] = e.get("evidence_kind") or "new_confirmation"
                e["_occurred_year"] = occurred.year
                if e not in this_week:
                    confirmations.append(e)
        if confirmations:
            print("  {} older event(s) carry NEW evidence this period — "
                  "presented as confirmations, not as this week's "
                  "events.".format(len(confirmations)))
            this_week.extend(confirmations)

        # Datum nelkuli esemeny: a gyujtes napja szerint kerulhet be, de
        # jeloljuk — a temporal integritas resze, hogy ez latszik.
        for e in undated:
            d = ac_intel.parse_day(e.get("created_at"))
            if d and d >= wk_start:
                e["_undated"] = True
                this_week.append(e)
        if undated:
            print("  {} event(s) without an event_date (dated by collection "
                  "time).".format(sum(1 for e in this_week if e.get("_undated"))))

        # ------------------------------------------------------------------
        # PROGRAMME-REteg: kotes, allapot, baseline-delta
        # ------------------------------------------------------------------
        programmes_by_id, proposed, unlinked, deltas = resolve_programmes(
            this_week, programmes)
        if proposed:
            print("  {} new programme(s) proposed (not yet written — run "
                  "scripts/reconcile_programmes.py):".format(len(proposed)))
            for k, p in list(proposed.items())[:8]:
                print("    + {}  [{}]".format(k, p.get("programme_kind")))
        if deltas:
            print("  {} event(s) move the on-order baseline:".format(len(deltas)))
            for eid, pid, dl in deltas[:8]:
                print("    event {} / {}: {:+d}".format(eid, pid, dl))
        else:
            print("  No event moves the on-order baseline this period "
                  "(restatements and unconfirmed claims do not).")
        merge_flags = acprog.merge_candidates(
            [p for p in programmes_by_id.values()
             if p.get("review_status") in (None, "active")])
        if merge_flags:
            print("  {} possible duplicate programme pair(s) flagged for "
                  "analyst review.".format(len(merge_flags)))

        # ------------------------------------------------------------------
        # WoW A PUBLIKALT ELOZO ERTEKBOL  (a 18 -> 22 = +0 hiba javitasa)
        # ------------------------------------------------------------------
        prior_payload, prior_metrics = load_prior_report(week_label)
        recomputed_prev = len(prev_week)
        published_prev, wow, wow_basis, wow_drift = None, None, None, None
        if prior_metrics and prior_metrics.get("events_published") is not None:
            published_prev = int(prior_metrics["events_published"])
            wow_basis = "published figure from {}".format(
                prior_metrics.get("week_label"))
        elif prior_payload:
            published_prev = ((prior_payload.get("stats") or {})
                              .get("events_this_week"))
            if published_prev is not None:
                published_prev = int(published_prev)
                wow_basis = "published figure from {}".format(
                    prior_payload.get("week_label"))
        if published_prev is not None:
            wow = len(this_week) - published_prev
            if recomputed_prev != published_prev:
                # EZ A LENYEG: a drift nem elhallgatando, hanem kiirando.
                wow_drift = {
                    "published": published_prev,
                    "recomputed": recomputed_prev,
                    "note": ("the previous period now recomputes to {} events "
                             "against the {} published then; late-arriving "
                             "articles and re-dated events cause this. Week-"
                             "over-week is stated against the PUBLISHED "
                             "figure.".format(recomputed_prev, published_prev)),
                }
            prior_method = (prior_metrics or {}).get("methodology_version")
            if prior_method and prior_method != METHODOLOGY_VERSION:
                wow, wow_basis = None, (
                    "not comparable — collection methodology changed ({} -> "
                    "{})".format(prior_method, METHODOLOGY_VERSION))
        else:
            wow_basis = "no prior published report — week-over-week begins next "\
                        "period"

        prev_n, prev_avg = recomputed_prev, len(prev_4wk) / 4.0
        volume_not_comparable = bool(
            (prev_n < 8 and len(this_week) > 3 * max(prev_n, 1))
            or (prev_avg >= 1 and len(this_week) > 2.5 * prev_avg)
            or (len(this_week) >= 1 and prev_avg > 2.5 * len(this_week)))

        # Szerzodesnek MINOSULO stadiumok — csak ezekre mondjuk, hogy "firm",
        # es most mar szerzodes-evidenciat is kerunk hozza.
        firm_stages = {"contract_signed", "production", "delivery", "ioc", "foc"}
        firm = [e for e in this_week
                if ac_intel.stage_of(e) in firm_stages
                and acprog.contract_evidenced(e)[0]]
        labelled_firm = [e for e in this_week
                         if ac_intel.stage_of(e) in firm_stages]

        by_stage, by_domain, by_region = {}, {}, {}
        for e in this_week:
            by_stage[ac_intel.stage_of(e)] = by_stage.get(
                ac_intel.stage_of(e), 0) + 1
            dm = ac_intel.domain_of(e, types)
            by_domain[dm] = by_domain.get(dm, 0) + 1
            reg = (countries.get(e.get("country_id") or "") or {}).get("region")
            if reg:
                by_region.setdefault(reg, []).append(e)

        stats = {
            "events_this_week": len(this_week),
            "events_prev_week_published": published_prev,
            "events_prev_week_recomputed": recomputed_prev,
            "wow": wow,
            "wow_basis": wow_basis,
            "wow_drift": wow_drift,
            "events_prev_4wk_weekly_avg": round(prev_avg, 1),
            "volume_not_comparable": volume_not_comparable,
            "firm_procurement_actions": len(firm),
            "firm_actions_labelled": len(labelled_firm),
            "firm_actions_note": (
                "{} event(s) carried a contracted lifecycle label; {} are "
                "backed by signing language, an award reference or a contract "
                "date. Only the latter are counted as firm.".format(
                    len(labelled_firm), len(firm))),
            "value": ac_intel.value_breakdown(this_week),
            "airframes_by_domain": ac_intel.platform_breakdown(this_week, types),
            "by_lifecycle_stage": by_stage,
            "by_capability_domain": by_domain,
            "by_region": {r: len(v) for r, v in by_region.items()},
            "baseline_movement": {
                "events_moving_baseline": len(deltas),
                "total_on_order_delta": sum(d[2] for d in deltas),
                "note": ("Restatements of existing programmes contribute zero. "
                         "This is what prevents a programme of record from "
                         "inflating week by week."),
            },
            "programme_layer": {
                "programmes_touched": len({e.get("programme_id")
                                           for e in this_week
                                           if e.get("programme_id")}),
                "programmes_proposed": len(proposed),
                "events_unlinked": len(unlinked),
                "duplicate_pairs_flagged": len(merge_flags),
            },
            "collection_health": {
                "unique_events": len(this_week),
                "events_missing_event_date": sum(
                    1 for e in this_week if e.get("_undated")),
                "future_dated_excluded": len(future_dated),
                "new_confirmations_of_older_events": len(confirmations),
                "pending_review": sum(
                    1 for e in this_week
                    if e.get("review_status") == "pending"),
                "wow_comparable": wow is not None and not volume_not_comparable,
            },
        }

        client = anthropic.Anthropic()

        # ---------------- elemzoi retegek ----------------
        developments, background = [], []
        judgements, self_checks, orbat = None, [], []
        stage_fixes = []
        try:
            developments, background = ac_intel.build_developments(
                client, this_week, types, countries, fleets,
                programmes_by_id=programmes_by_id, articles_by_id=articles)
            if developments:
                judgements = ac_intel.build_judgements(
                    client, developments, stats)

            # A STADIUM-VISSZAIRAS AZ ORBAT ELOTT TORTENIK. Enelkul all elo az
            # uzbeg allapot: az elemzoi reteg "negotiation, unconfirmed", az
            # ORBAT "Contract signed x24".
            stage_fixes = ac_intel.propagate_stage_corrections(
                developments, this_week)
            if stage_fixes:
                print("  Stage corrections propagated to {} event(s):".format(
                    len(stage_fixes)))
                for eid, was, now_ in stage_fixes[:6]:
                    print("    event {}: {} -> {}".format(eid, was, now_))

            dev_ids = {i for d in developments
                       for i in (d.get("event_ids") or [])}
            orbat = ac_intel.orbat_delta(
                [e for e in this_week if e.get("event_id") in dev_ids]
                or this_week, fleets, types, countries,
                programmes_by_id=programmes_by_id)
            self_checks = ac_intel.run_self_checks(
                developments, judgements, wk_start, naive_now, stats,
                events=this_week, countries_by_id=countries, orbat=orbat)
            if self_checks:
                applied = ac_intel.qa_language_gate(
                    client, developments, judgements, self_checks)
                if applied:
                    print("  QA gate: {} field(s) rewritten, re-checking".format(
                        applied))
                    rechecked = ac_intel.run_self_checks(
                        developments, judgements, wk_start, naive_now, stats,
                        events=this_week, countries_by_id=countries,
                        orbat=orbat)
                    self_checks = ac_intel.mark_unresolved(
                        self_checks, rechecked)
            gated = ac_intel.gate_key_judgements(judgements, self_checks)
            if gated:
                print("  KJ gate: {} judgement(s) withheld for analyst "
                      "review: {}".format(len(gated),
                                          ", ".join(str(g.get("id"))
                                                    for g in gated)))
                ac_intel.rebuild_bottom_line(client, judgements,
                                             developments, stats)
                leak = ac_intel.check_bottom_line_leak(judgements)
                if leak:
                    self_checks.extend(leak)
                    print("  [warn] bottom line still echoes a withheld "
                          "judgement — flagged in the report")
            if self_checks:
                print("  self-checks raised {} issue(s):".format(
                    len(self_checks)))
                for c in self_checks[:8]:
                    print("    - {}: {}".format(c["check"], c["item"]))
        except Exception as exc:  # noqa: BLE001
            print("  [warn] intelligence layer unavailable ({}: {})".format(
                type(exc).__name__, str(exc)[:200]))

        # ---------------- szarmaztatott nezetek ----------------
        timeline = ac_intel.capability_timeline(
            developments, this_week, types, countries,
            programmes_by_id=programmes_by_id)
        matrix = ac_intel.maturity_matrix(developments)
        diff = ac_intel.since_last_week(
            {"developments": developments,
             "priority_watch": (judgements or {}).get("priority_watch") or [],
             "report_meta": {"week_label": week_label}},
            prior_payload)
        briefing = ac_intel.build_briefing(
            week_label, judgements, developments, timeline, diff, stats)

        def event_view(e):
            art = articles.get(e.get("article_id") or "")
            c = countries.get(e.get("country_id") or "") or {}
            t = types.get(e.get("type_id") or "") or {}
            return {
                "event_id": e["event_id"], "event_type": e["event_type"],
                "lifecycle_stage": ac_intel.stage_of(e),
                "lifecycle_stage_reported": e.get("lifecycle_stage_reported"),
                "stage_correction_note": e.get("stage_correction_note"),
                "capability_domain": ac_intel.domain_of(e, types),
                "programme_id": e.get("programme_id"),
                "country": c.get("name") or e.get("unresolved_country_name"),
                # A KANONIKUS nev; a forras tipusjele kulon. Nev alapjan itt
                # SOHA nem keresunk vissza.
                "aircraft": t.get("name") or e.get("unresolved_type_name"),
                "variant_reported": e.get("variant_raw"),
                "type_match_kind": e.get("type_match_kind"),
                "quantity": e.get("quantity"),
                "quantity_claimed": e.get("quantity_claimed"),
                "on_order_delta": e.get("on_order_delta") or 0,
                "on_order_delta_reason": e.get("on_order_delta_reason"),
                "value_usd_m": e.get("value_usd_m"),
                "value_type": e.get("value_type"),
                "event_date": e.get("event_date"),
                "evidence_kind": e.get("evidence_kind") or "new_event",
                "occurred_year": e.get("_occurred_year"),
                "expected_ioc_year": e.get("expected_ioc_year"),
                "summary": e["summary"],
                "undated": bool(e.get("_undated")),
                "pending": e.get("review_status") == "pending",
                "article_title": art.get("title") if art else None,
                "article_url": art.get("url") if art else None,
            }

        payload = {
            "schema": "air_power_v3",
            "week_label": week_label,
            "report_meta": {
                "week_label": week_label,
                "period_start": wk_start.strftime("%Y-%m-%d"),
                "period_end": naive_now.strftime("%Y-%m-%d"),
                "collection_cutoff_utc": now.strftime("%Y-%m-%d %H:%M UTC"),
                "generated_utc": now.strftime("%Y-%m-%d %H:%M UTC"),
                "status": ("analyst review required" if self_checks
                           else "auto-generated, QA clean"),
                "version": METHODOLOGY_VERSION,
                "methodology_version": METHODOLOGY_VERSION,
            },
            "stats": stats,
            "bottom_line": (judgements or {}).get("bottom_line") or "",
            "key_judgements": (judgements or {}).get("key_judgements") or [],
            "judgements_requiring_review": (judgements or {}).get(
                "judgements_requiring_review") or [],
            "developments": developments,
            "background_items": background,
            "priority_watch": (judgements or {}).get("priority_watch") or [],
            "intelligence_gaps": (judgements or {}).get(
                "intelligence_gaps") or [],
            "orbat_delta": orbat,
            "capability_timeline": timeline,
            "maturity_matrix": matrix.get("introduction"),
            "capability_withdrawal": matrix.get("withdrawal"),
            "since_last_week": diff,
            "briefing": briefing,
            "programme_state": [
                acprog.programme_view(
                    p, [e for e in this_week
                        if e.get("programme_id") == p.get("programme_id")])
                for p in programmes_by_id.values()
                if any(e.get("programme_id") == p.get("programme_id")
                       for e in this_week)
            ],
            "programme_review": {
                "proposed": [{"programme_id": k, "kind": v.get("programme_kind"),
                              "title": v.get("title"),
                              "events": v.get("_events")}
                             for k, v in proposed.items()],
                "duplicate_pairs": merge_flags,
                "unlinked_events": unlinked,
            },
            "self_checks": self_checks,
            "annex_events": [event_view(e) for e in sorted(
                this_week,
                key=lambda x: -(float(x.get("value_usd_m") or 0)))[:60]],
        }
        ac_intel.scrub_report_payload(payload)

        if dry_run:
            out = Path(__file__).resolve().parent.parent / "data" / \
                "dry_run_report_{}.json".format(week_label)
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                      default=str), encoding="utf-8")
            print("\nDRY RUN — nothing written to the database.")
            print("Report preview saved to {}".format(out))
            print("  {} in-period events, {} development(s), {} judgement(s), "
                  "{} self-check issue(s)".format(
                      len(this_week), len(developments),
                      len(payload["key_judgements"]), len(self_checks)))
            return

        db.upsert("ac_reports", [{
            "week_label": week_label,
            "period_start": wk_start.strftime("%Y-%m-%d"),
            "period_end": naive_now.strftime("%Y-%m-%d"),
            "generated_at": now.isoformat(),
            "payload": payload,
        }], "week_label")

        # A PUBLIKALT metrikak rogzitese — ez lesz a kovetkezo het WoW-alapja.
        try:
            db.upsert("ac_report_metrics", [{
                "week_label": week_label,
                "period_start": wk_start.strftime("%Y-%m-%d"),
                "period_end": naive_now.strftime("%Y-%m-%d"),
                "events_published": len(this_week),
                "developments_published": len(developments),
                "firm_actions_published": len(firm),
                "methodology_version": METHODOLOGY_VERSION,
                "metrics": {"by_lifecycle_stage": by_stage,
                            "by_capability_domain": by_domain,
                            "baseline_movement":
                                stats["baseline_movement"]},
            }], "week_label")
        except Exception as exc:  # noqa: BLE001
            print("  [warn] could not record published metrics ({}) — run "
                  "supabase/add_programme_layer.sql".format(str(exc)[:120]))

        print("Report {} saved ({} in-period events, {} development(s), "
              "{} judgement(s), {} self-check issue(s)).".format(
                  week_label, len(this_week), len(developments),
                  len(payload["key_judgements"]), len(self_checks)))
        db.finish_run(run, "success", items_processed=len(this_week))
    except Exception as e:  # noqa: BLE001
        if run is not None:
            db.finish_run(run, "error", error_message=str(e))
        raise


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
