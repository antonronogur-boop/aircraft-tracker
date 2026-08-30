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

## v3 — programme layer (event ≠ programme ≠ evidence)

A W33/W34 jelentések összevetése három olyan hibát mutatott, amelyek mind
ugyanabból az egy okból származtak: a rendszer nem választotta el a **heti
eseményt**, a **tartós programállapotot** és a **forrás állítását**.

```
EVIDENCE  ->  EVENT  ->  PROGRAMME STATE CHANGE      (v3, helyes)
ARTICLE   ->  quantity  ->  ORBAT += quantity        (v2, hibás)
```

Ezért egy újabb cikk ugyanarról a programról **nem ad hozzá darabszámot** —
frissíti vagy megerősíti ugyanazt a programot.

### Üzembe helyezés (v3)

```cmd
:: 1. Séma
::    Supabase SQL Editor -> supabase/add_programme_layer.sql

:: 2. A meglévő adat átkötése — ELŐSZÖR DRY RUN
python scripts\reconcile_programmes.py
::    -> data\reconcile_report.json  (típus-újraillesztés, programme-állapot,
::       baseline-delták, duplikátum-gyanúk)

:: 3. Átnézés után írás
python scripts\reconcile_programmes.py --write
::    a type_id javításokhoz külön kapcsoló, mert meglévő adatot módosít:
python scripts\reconcile_programmes.py --write --fix-types

:: 4. Jelentés — előbb dry run
python scripts\generate_weekly_report.py --dry-run
python scripts\generate_weekly_report.py
```

### Tesztek

```cmd
python scripts\test_ac_match.py            :: entitás-illesztés regressziók
python scripts\test_ac_programmes.py       :: programme-réteg (15 alszakasz)
python scripts\test_report_integration.py  :: végponti, a W33/W34 esetekkel
```

### Offline hangolás — ne az éles adatbázison iterálj

A programme-réteg finomhangolása a **valódi cikkszövegeken** dől el: a
szintetikus teszt nem tudja, hogy a „Tranche 5" típusjelölés, a „90 targeting
pods" nem repülőgép, vagy hogy a „£4.6 billion ($6.1 billion) contract"
zárójele széttöri a mintaillesztést. Ezért van két eszköz:

```cmd
:: 1. Egyszeri, csak-olvasó adatkimentés
python scripts\export_for_review.py
::    -> data\events_export.json

:: 2. A teljes programme-logika újrajátszása adatbázis nélkül, korlátlanul
python scripts\replay_audit.py             :: összefoglaló + gyanús esetek
python scripts\replay_audit.py --suspect   :: a gyanús programok részletei
python scripts\replay_audit.py --full      :: minden program
python scripts\replay_audit.py pol-ah64-2024   :: egy program döntésenként
```

A `replay_audit.py` minden döntést kiír indoklással (hatókör, alap,
baseline-delta), így egy logikaváltozás hatása másodpercek alatt látszik az
összes eseményen — éles futtatás nélkül. A `--suspect` lista azt mutatja, amit
**embernek** kell eldöntenie; ha az üres vagy csak valódi forrás-ellentmondásokat
tartalmaz, a `reconcile_programmes.py --write` biztonságosan futtatható.

### Mit javít a v3, és melyik konkrét hibára

| Modul | Javítás |
| --- | --- |
| `scripts/ac_match.py` | Határ-tudatos designation-illesztés. A régi kód `"a-10" in "a-100ll"` alapján a Beriev **A-100LL** veszteségét *A-10 Thunderbolt II — Loss ×1*-ként vitte be. Variáns (`HH-60W`) és `match_kind` rögzítése; fuzzy illesztés **csak** ingestionkor, a riportban soha. |
| `scripts/ac_programmes.py` | Programme-identitás, kanonikus darabszám felülírásos logikával (nem összegzéssel), `on_order_delta` **alapértelmezésben 0**, szerződés-evidencia kapu, duplikátum-jelzés. Ez szünteti meg a lengyel Apache 190 → 284 → 286 halmozódást és az üzbég „negotiation + Contract signed ×24" kettős állapotot. |
| `ac_intel.orbat_delta` | Baseline kulcsa `(ország, típus, variáns, haderőnem)`. Variáns-szintű eseményhez **nem** rendel család-szintű számot (HH-60W ↔ UH-60 *Active 2000*, UK AH-64E 50 ↔ *Active 100*) — a számot visszatartja, és kiírja, miért. |
| `ac_intel.count_lineages` | A független forrásláncok száma **determinisztikus**, a cikk/primer forrás alapján. A W33 „2 lineage" állítása két olyan eventre épült, amelyek ugyanabból a cikkből származtak; a confidence ehhez van kötve. |
| `ac_intel.capability_timeline` | **Egy sor = egy programme + egy milestone.** Késés (`schedule_slip`) nem képesség-érkezés; MRO/infrastruktúra-program nem veszi át a beszerzés gépátadási évét — dátum nélkül `TBD`. |
| `ac_intel._enforce_effect_timing` | **Kettős horizont**: legkorábbi műveleti hatás (IOC) és értelmes méretű képesség (FOC/scale) külön, hónapban számolva. A VC-25B (IOC 2028) így `1-3 years`, nem `>3 years`. |
| `ac_intel.run_self_checks` | Új ellenőrzések: veszteség ≠ mechanizmus ≠ szándék (W33 Iran/MQ-9), exploitation-lehetőség vs megtörtént tény, egy esetből többes számú trend („Baltic allies"), kvantifikálhatatlan „quantifiable gap", retorikus leértékelés („token addition"). |
| `ac_intel.propagate_stage_corrections` | Az elemzői stadium-downgrade **visszaíródik az eseményekre** az ORBAT felépítése előtt, így egy állítás nem lehet két állapotban. |
| `ac_intel.since_last_week` | „SINCE LAST WEEK" — 4-6 soros programme-szintű diff + az előző heti watchok állapota (resolved / unchanged / escalated / dropped). |
| `ac_intel.build_briefing` | 4 slide-os briefing view: `/weekly/<week>/brief` (vagy `/weekly/latest/brief`). Csak QA-n átment tartalomból épül. |
| `ac_report_metrics` | A **publikált** heti metrikák rögzítése. A WoW ebből számol, nem az újraszámolt előző hétből — ez a W33 „18" / W34 „22 (+0 WoW)" hiba javítása; az újraszámolási drift látható marad. |

Amit szándékosan **nem** változtattunk: a `Fact → Capability delta → So what →
Timing basis → Indicators → Sourcing` felépítés, a *Capability domain ×
programme maturity* tábla, a külön *Capability transition / withdrawal* réteg
és a *Priority Intelligence Watch*.

## Roadmap

- **Sprint 2**: Next.js frontend — What's-new feed, országoldalak
  (flotta-tábla + esemény-idővonal), géptípus-oldalak, mini admin review.
- **Sprint 3**: flotta-baseline feltöltés (CSV import + kézi szerkesztés),
  heti digest, e-mail/Telegram riasztás új eseményekre.
- **Sprint 4 (v3)**: programme-réteg, evidencia-láncok, longitudinális diff,
  briefing view. → lásd fentebb.
- **Következő**: a `ac_fleets` baseline variáns/haderőnem szintre bontása
  (a séma már támogatja: `variant`, `service`, `baseline_scope`), hogy az ORBAT
  a visszatartott számok helyett valódi variáns-adatot mutasson.
