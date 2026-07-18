import { NextRequest, NextResponse } from "next/server";

// Approve / reject an extracted event. Uses the service_role key —
// server-side only, never exposed to the browser.
export async function POST(req: NextRequest) {
  const supaUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supaUrl || !serviceKey) {
    return NextResponse.json({ error: "server not configured" }, { status: 500 });
  }

  const body = await req.json().catch(() => null) as
    { event_id?: number; action?: string } | null;
  if (!body?.event_id || !["approve", "reject"].includes(body.action ?? "")) {
    return NextResponse.json({ error: "bad request" }, { status: 400 });
  }

  const res = await fetch(
    `${supaUrl}/rest/v1/ac_events?event_id=eq.${body.event_id}`,
    {
      method: "PATCH",
      headers: {
        apikey: serviceKey,
        Authorization: `Bearer ${serviceKey}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify({
        review_status: body.action === "approve" ? "approved" : "rejected",
      }),
    }
  );

  if (!res.ok) {
    return NextResponse.json({ error: `supabase ${res.status}` }, { status: 502 });
  }
  return NextResponse.json({ ok: true });
}
