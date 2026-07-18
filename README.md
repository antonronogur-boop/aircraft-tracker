# Aircraft Procurement Tracker

Country-centric tracker of military aircraft fleets: who orders, receives,
upgrades, sells or retires which aircraft. Built on the same stack as the
Drone/UAV Monitor (RSS → Claude extraction → Supabase → Next.js), sharing
the same Supabase project (tables prefixed `ac_`) and GitHub secrets.

## Data model (lean by design)

- `ac_aircraft_types` — the catalogue: ~80 major types with base data + aliases
- `ac_countries` — operators, with region grouping
- `ac_fleets` — the BASELINE: country × type × status (active / on_order / …) × quantity
- `ac_articles` — collected news items
- `ac_events` — the core: extracted events (order / delivery / upgrade /
  export_sale / selection / negotiation / retirement / incident), each
  linked to an article and, where matched, a country + type

An "alert" is simply a new approved event that changes the baseline.

## Gyors indítás (első üzembe helyezés)

1. **Supabase séma** — a Supabase SQL Editorban futtasd le:
   `supabase/schema.sql`
2. **Seed** (cmd, az projekt mappából):
   ```cmd
   set SUPABASE_URL=https://uqjhgdclaagfkopdfjlq.supabase.co
   set SUPABASE_SERVICE_ROLE_KEY=<kulcs>
   set ANTHROPIC_API_KEY=<kulcs>
   python scripts\seed_database.py
   ```
3. **Első gyűjtés + feldolgozás** (ugyanabban az ablakban):
   ```cmd
   python scripts\collect_rss.py
   python scripts\process_articles.py
   ```
4. **Automata futás**: a `.github/workflows/aircraft_sync.yml` push után
   magától fut naponta kétszer (04:30 és 16:30 UTC) — a meglévő GitHub
   secrets-eket használja, nincs új teendő.

## Pipeline

`collect_rss.py` szűr: csak azok a cikkek kerülnek be, amik katalógusbeli
géptípust vagy beszerzési kulcsszót említenek — így az AI-feldolgozás
(fizetős) csak releváns cikkeken fut. `process_articles.py` cikkstátuszok:
`raw → processed | irrelevant | failed`. A kinyert események
`review_status=pending`-gel születnek; a frontend admin felületén lehet
majd jóváhagyni őket (Sprint 2).

## Web frontend (web/)

Next.js 14 + Tailwind, country-first UI: Dashboard ("Latest signals" feed +
weekly stats), Countries (region-grouped, fleet table + event timeline per
country), Aircraft catalogue (base data, operators, event history per type),
and an admin Review queue with bulk approve/reject.

Local run:
```cmd
cd web
npm install
npm run dev
```
Open http://localhost:3000. Config comes from `web/.env.local`
(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, and
SUPABASE_SERVICE_ROLE_KEY for the review API route).

Vercel deploy: import the GitHub repo, set **Root Directory = `web`**, add
the same three env vars, deploy. Every push auto-deploys.

## Roadmap

- **Sprint 2**: Next.js frontend — What's-new feed, országoldalak
  (flotta-tábla + esemény-idővonal), géptípus-oldalak, mini admin review.
- **Sprint 3**: flotta-baseline feltöltés (CSV import + kézi szerkesztés),
  heti digest, e-mail/Telegram riasztás új eseményekre.
