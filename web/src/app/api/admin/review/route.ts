import { NextRequest, NextResponse } from "next/server";

// Approve / reject an extracted event, optionally applying it to the
// fleet baseline (action "approve_apply"). Uses the service_role key —
// server-side only, never exposed to the browser.

interface EventRow {
  event_id: number;
  event_type: string;
  country_id: string | null;
  type_id: string | null;
  quantity: number | null;
}

interface FleetRow {
  fleet_id: number;
  quantity: number | null;
}

function supa(supaUrl: string, key: string) {
  const headers = {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
    Prefer: "return=minimal",
  };
  return {
    async get<T>(path: string): Promise<T[]> {
      const r = await fetch(`${supaUrl}/rest/v1/${path}`, { headers });
      return r.ok ? ((await r.json()) as T[]) : [];
    },
    async patch(path: string, body: unknown): Promise<boolean> {
      const r = await fetch(`${supaUrl}/rest/v1/${path}`,
        { method: "PATCH", headers, body: JSON.stringify(body) });
      return r.ok;
    },
    async post(path: string, body: unknown): Promise<boolean> {
      const r = await fetch(`${supaUrl}/rest/v1/${path}`,
        { method: "POST", headers, body: JSON.stringify(body) });
      return r.ok;
    },
  };
}

/** Apply an approved event to ac_fleets.
 *  order      -> on_order += qty
 *  delivery   -> active += qty, on_order -= qty (not below 0)
 *  retirement -> active -= qty (not below 0)
 *  incident   -> active -= qty (not below 0)
 */
async function applyToFleet(
  db: ReturnType<typeof supa>, ev: EventRow
): Promise<string> {
  if (!ev.country_id || !ev.type_id || !ev.quantity) return "not applied (unresolved or no quantity)";
  const base = `ac_fleets?country_id=eq.${ev.country_id}&type_id=eq.${ev.type_id}`;
  const note = `[event] auto-applied from event #${ev.event_id}`;

  const adjust = async (status: string, delta: number) => {
    const rows = await db.get<FleetRow>(`${base}&fleet_status=eq.${status}&select=fleet_id,quantity`);
    if (rows.length > 0) {
      const next = Math.max(0, (rows[0].quantity ?? 0) + delta);
      await db.patch(`ac_fleets?fleet_id=eq.${rows[0].fleet_id}`,
        { quantity: next, source_note: note, as_of: new Date().toISOString().slice(0, 10) });
      return next;
    }
    if (delta > 0) {
      await db.post("ac_fleets", {
        country_id: ev.country_id, type_id: ev.type_id, fleet_status: status,
        quantity: delta, source_note: note,
        as_of: new Date().toISOString().slice(0, 10),
      });
      return delta;
    }
    return null;
  };

  const q = ev.quantity;
  switch (ev.event_type) {
    case "order":
      await adjust("on_order", q);
      return `fleet updated: on_order +${q}`;
    case "delivery":
      await adjust("active", q);
      await adjust("on_order", -q);
      return `fleet updated: active +${q}, on_order -${q}`;
    case "retirement":
    case "incident":
      await adjust("active", -q);
      return `fleet updated: active -${q}`;
    default:
      return "not applied (event type has no fleet effect)";
  }
}

export async function POST(req: NextRequest) {
  const supaUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supaUrl || !serviceKey) {
    return NextResponse.json({ error: "server not configured" }, { status: 500 });
  }

  const body = await req.json().catch(() => null) as
    { event_id?: number; action?: string } | null;
  if (!body?.event_id || !["approve", "reject", "approve_apply"].includes(body.action ?? "")) {
    return NextResponse.json({ error: "bad request" }, { status: 400 });
  }

  const db = supa(supaUrl, serviceKey);
  const newStatus = body.action === "reject" ? "rejected" : "approved";
  const ok = await db.patch(`ac_events?event_id=eq.${body.event_id}`,
    { review_status: newStatus });
  if (!ok) return NextResponse.json({ error: "supabase update failed" }, { status: 502 });

  let fleetResult: string | null = null;
  if (body.action === "approve_apply") {
    const rows = await db.get<EventRow>(
      `ac_events?event_id=eq.${body.event_id}&select=event_id,event_type,country_id,type_id,quantity`);
    fleetResult = rows.length ? await applyToFleet(db, rows[0]) : "event not found";
  }

  return NextResponse.json({ ok: true, fleet: fleetResult });
}
