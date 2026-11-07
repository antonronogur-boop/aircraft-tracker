# Command Air Intelligence Brief — v3.1 (2026-11)

A heti jelentés elé került egy **4 oldalas vezetői brief** egy magyar katonai vezető számára. Nem új projekt és nem második pipeline: a brief a heti jelentés **már elkészült, QA-n átment payloadjából** épül, ugyanabban a futásban, ugyanabba a `ac_reports.payload`-ba (`payload.command_brief`). A részletes jelentés változatlanul megmaradt (Part II), minden brief-tétel rá hivatkozik.

## 1. Adatfolyam — egy pipeline, egy igazság

```
RSS (napi) → source policy → Haiku gate → Sonnet extraction → ac_events (pending/approved; rejected kizárva)
                                                                    │
SZERDA reggel  generate_weekly_report.py  ──────────────────────────┘
   ├─ heti ablak: Europe/Budapest szerda 00:00:00 → kedd 23:59:59   (ac_window.py)
   ├─ developments / key_judgements / QA / since_last_week          (változatlan, ac_intel.py)
   ├─ coverage audit (ADEQUATE / PARTIAL / GAP)                      (coverage_audit.py)
   └─ command brief = nézet a fenti objektumokra                     (ac_command_brief.py + ac_hungary.py)
          └─ egyetlen jelölt új szöveg: EXECUTIVE SYNTHESIS (validált, hivatkozott, fallbackkel)
                                   │
                         ac_reports.payload  ──►  /weekly (brief + Part II)  ·  /weekly/command-brief  ·  4 oldalas PDF
```

A brief minden tétele egy `D-xx` fejleményre vagy `KJ-xx` ítéletre mutat. A generátor ezeket a hivatkozási kulcsokat a **részletes rétegbe is visszaírja** (`developments[].ref`, `country_ids`, `hu_relevance`), így a részletes jelentés ugyanazt a HU-relevanciát mutatja, mint a brief. Egy brief-hivatkozás, ami a részletes jelentésben nem létezik, self-check hibát ad.

## 2. A négy oldal

| Oldal | Tartalom | Forrás a payloadban |
|---|---|---|
| 1 | HU Air Intelligence Bottom Line (5–7 mondat) · Top 3–5 KJ (HU relevance → significance → confidence → immediacy) · CEE térkép (hotspotok HU-relevancia szerint, collection gap szaggatottan) | `key_judgements`, `developments`, coverage |
| 2 | Közvetlen és közeli régió: non-NATO prioritás, szomszédok, kiterjesztett NATO / szövetséges légtérpozíció CEE-ben · táblázat · *No material change identified* vs *Collection gap* · coverage csíkok | `developments`, coverage |
| 3 | Közel-Kelet · Afrika · tágabb NATO (régiónként 2–4, csak anyagi) · **Executive change table** (Priority · Country · Capability · Previous · Current · Delta · HU relevance · Confidence) | `developments`, `since_last_week` |
| 4 | Globális stratégiai kép (Indo-Pacific) + globális térkép (significance szerint) · Priority Intelligence Watch ≤5 · Intelligence Gaps 3–5 · Next 7–30 days | `developments`, `priority_watch`, `intelligence_gaps`, coverage |

Szabályok: nincs töltelék (csak anyagi fejlemény: significance ≥3, vagy HIGH HU-relevancia és ≥2); egy fejlemény a 2–4. oldalon legfeljebb egyszer szerepel; üres régió = `NO MATERIAL CHANGE IDENTIFIED` (ha a gyűjtés legalább PARTIAL) vagy `COLLECTION GAP` (ha 60 napig semmi nem érkezett onnan). A page-1 KJ-knél mindig van „What would make this wrong” sor: a jelentés `alternative_explanation`-je, vagy ha az üres, a bizonyíték állapotából képzett, jelölt rendszer-alternatíva.

**Executive synthesis (XS-xx).** Ha egy HIGH/MEDIUM HU-relevanciájú, anyagi fejleményt egyetlen riport-KJ sem fed le, a page-1-re XS-tételként kerülhet (legfeljebb 3). Lila keret, „Executive synthesis” címke, `traces_to: [D-xx]`. **Visszatartott (QA-n elbukott) ítélet eseményeiből XS nem készülhet** — a fejlemény ténysorként a 2. oldalon ettől még megjelenik. A bottom line modellből jön (egy rövid Sonnet-hívás), de minden mondat: (1) hivatkozik egy D-/KJ-/XS-tételre, (2) nem tartalmazhat a hivatkozott tételekben nem szereplő számot, (3) nem nevezhet meg más országot, (4) nem sértheti a trend/szuperlatívusz QA-szabályokat, (5) nem idézheti vissza a visszatartott ítéletet. Ami elbukik, kiesik (okkal naplózva); ha 3-nál kevesebb mondat marad, **determinisztikus bottom line** lép be. A brief modell nélkül is teljes (`AC_BRIEF_SYNTHESIS=0`).

## 3. Hungary relevance — külön dimenzió

`config/hungary_relevance.json` + `scripts/ac_hungary.py`. Determinisztikus, szerkeszthető, verziózott (`hu-1.0`). A **significance (1–5)** a légierő-kép változásának súlya az elemzői rétegből; a **HU relevance** (0–100 → HIGH ≥55 · MEDIUM ≥35 · LOW ≥15 · MINIMAL) azt méri, mennyire számít Magyarországnak / az MH-nak / a NATO közép-keleti légtérpozíciójának. A kettő független: egy japán F-35 rendelés lehet SIG 5 és MINIMAL, egy amerikai F-16 telepítés Romániába SIG 3 és HIGH.

| Tényező | Pont | Mikor |
|---|---|---|
| Földrajz / szereplő | 0–45 | Magyarország 45 · Ukrajna 36 · Szerbia 34 · Oroszország 34 · Szlovákia/Románia 30 · Ausztria 28 · Belarusz 28 · Horvát/Szlovén 26 · Lengyel/Cseh 22 … más NATO 8, Európa 5 |
| Names Hungary / MH | 40 | a FORRÁS (cím, tény) nevezi meg Magyarországot — a saját elemzésünk nem számít |
| MH platform | 15 | Gripen, KC-390, H145M, H225M, L-39NG, Falcon 7X, NASAMS, SAC C-17 (Pápa), NATO AWACS |
| Air policing / QRA | 12 | air policing, QRA, scramble, intercept |
| Eastern-flank posture | 15 | eastern flank, forward/rotational deployment Lengyelo./Románia/Szlovákia/Baltikum… |
| Airspace incident | 15 | légtérsértés, drón-berepülés a régióban |
| Air defence / counter-air | 10 | légvédelem, SAM, Patriot, NASAMS, IRIS-T, C-UAS |
| Regional air balance | 10 | vadász/támadó helikopter szomszédnál vagy non-NATO prioritásnál |
| Major change next door | 10 | significance ≥4 szomszédnál / prioritásnál |
| NATO enabler | 8 | ISR/tanker/airlift NATO-szereplőnél (nem MH saját) |
| Attrition adjacent | 8 | veszteség a háborús szomszédságban |
| Names a CEE state | 12 | a forrás egy másik CEE-államot nevez meg |
| Regional sustainment / exercise | 5 | MRO/képzési központ, gyakorlat CEE-szereplővel |
| Horizon | −5…+5 | immediate/<12 hó +5, >3 év −5 |

Minden alkalmazott tényező pontszámmal és indoklással bekerül a payloadba — a szint mindig visszakövethető. **Az MH-platformlistát (mh_platforms) érdemes ellenőrizni és szükség szerint bővíteni** — ez határozza meg, mikor emel egy távoli tétel az MH tervezés szempontjából.

## 4. Coverage audit

`scripts/coverage_audit.py` (önállóan is futtatható, és a heti generátor is ezt hívja). Országonként 60 napra: ADEQUATE (≥4 esemény, ≥2 forrás) · PARTIAL (≥1) · GAP (0). Elutasított esemény nem számít, pending igen (ugyanaz a szemantika, mint a jelentésnél). Jelzi azt is, ha egy prioritási országra **nincs hivatalos (AF/MoD/NATO) forrás** a gyűjtésben — jelenleg ez mind a 10 forrásra igaz (szakmédia). `config/coverage_sources.json` tartalmazza a forrás-prioritást és a **jelölt** hivatalos forrásokat (honvedelem.hu, MApN, MON/Agencja Uzbrojenia, MoSR, MORH, Bundesheer, mod.gov.rs, AIRCOM…). Ezek NINCSENEK automatikusan felvéve: az audit eredménye alapján, a feed ellenőrzése után kerülhetnek az `ac_sources`-ba. Eredeti nyelvű evidencia megmarad (a gyűjtés nem fordít).

## 5. Heti ablak, ütemezés, késői adat

- **Ablak:** Europe/Budapest szerda 00:00:00 → kedd 23:59:59. Saját EU-DST szabály (a Windows Python 3.9 zoneinfo-ja tzdata nélkül nem megbízható). A hétcímke a kedd ISO-hete — folytonos a korábbi hétfői címkékkel.
- **Ütemezés:** `weekly_digest.yml` szerda 05:15 UTC (06:15 CET / 07:15 CEST). Előtte még egy gyűjtés + feldolgozás fut (keddig megjelent cikkek). Közös concurrency group a napi szinkronnal — sosem futnak egyszerre. A napi gyűjtés (04:30 UTC) változatlan.
- **Átállás:** az első szerdai futás az ablak elejét az utolsó hétfői jelentés utáni napra húzza (pl. W46: 2026-11-03 → 11-10), és ezt a jelentés kiírja. Egy nap sem esik ki.
- **Késői adat:** ami egy már publikált ablakról a publikálás UTÁN érkezik, a következő héten `late-arriving confirmation`-ként jelenik meg (`stats.collection_health.late_arriving_from_previous_period`). Ami még a szerdai gyűjtésben bekerült az előző jelentésbe, nem számít újra.
- **Nincs csendes felülírás:** egy már publikált hét újrafuttatása nem ír semmit. Szándékos újrakiadás: `python scripts/generate_weekly_report.py --restate "<ok>"` vagy GitHub Actions → weekly-digest → Run workflow → `restate_reason`. A jelentés és a brief látható RESTATEMENT sávot kap.

## 6. Felület és PDF

- `/weekly` és `/weekly/<hét>` — az első 4 oldal a Command Brief, utána „Part II — Detailed assessment”. Nyomtatás/PDF: 4 fekvő A4 oldal, majd a részletes jelentés álló A4-en.
- `/weekly/command-brief` (legfrissebb) és `/weekly/<hét>/command` — önálló brief; Print / Save as PDF = pontosan 4 oldal.
- `/weekly/<hét>/brief` — a korábbi 4 slide-os briefing változatlanul megmaradt.
- Térképek: Natural Earth (world-atlas, public domain) előre vetített SVG-útvonalakként a kódban (`web/src/lib/geo/*.ts`, generátor: `web/scripts/build-geo.cjs`). Nincs futásidejű térképkönyvtár, nincs külső tile.
- Webes kereszthivatkozás: `#D-03`, `#KJ-01` horgonyok; PDF-ben determinisztikus szöveg: „Detailed assessment → KJ-02, D-01”.
- Régebbi (v3.1 előtti) jelentésnél az oldal megmondja, hogy nincs brief, és hogyan építhető utólag: `python scripts/backfill_command_brief.py --week <hét>` (csak olvas; `--write` esetén látható restatementként írja be).

## 7. Ellenőrzés (2026-11-07)

| Teszt | Eredmény |
|---|---|
| `test_ac_match.py`, `test_ac_programmes.py`, `test_report_integration.py` (meglévő regresszió) | PASS |
| `test_programme_write.py` (valódi PostgreSQL 16, 5 migráció, 127 program) | PASS |
| `test_command_brief.py` — A: ablak/DST/átállás (15) · B: HU-modell (11) · C: brief konzisztencia, no filler, limitek (38) · D: synthesis validáció/fallback (9) · E: a **valódi** `generate_weekly_report.main()` memória-adatbázison: rejected kizárva, pending benne, szerdai dátum a következő hétre, kedd 23:50 helyi idő benne, late-arriving jelölve, már lefedett esemény nem számít újra, brief a payloadban, nincs csendes felülírás, `--restate` látható (23) | PASS |
| `next build` (típusellenőrzéssel) | PASS |
| Playwright E2E (`web/e2e/command-brief.e2e.cjs`): 4 oldal, egyik sem csordul túl; 2 SVG térkép; nincs külső asset; minden brief-hivatkozásnak van horgonya a részletes jelentésben; önálló PDF = 4 db A4 fekvő oldal; teljes jelentés PDF = 4 fekvő + álló folytatás; régi jelentés és a meglévő route-ok működnek | PASS |

## 8. BEFORE / AFTER

| Szempont | ELŐTTE (v3.0) | UTÁNA (v3.1) |
|---|---|---|
| Vezetői termék | 13–14 oldalas reference report + 4 slide-os briefing | + 4 oldalas Command Air Intelligence Brief (web, önálló route, 4 oldalas PDF), a teljes jelentés első 4 oldala |
| Magyar nézőpont | nincs; a rangsor significance + horizont | külön **HU relevance** dimenzió (tényezőkkel, pontokkal, indoklással); page-1 rangsor HU → SIG → conf → horizont |
| Regionális lefedettség | régió szerinti darabszám | prioritási országlista (non-NATO, szomszédok, kiterjesztett NATO) — anyagi változás / *no material change* / *collection gap* szétválasztva |
| „Nincs hír” értelmezése | nem különböztetett | coverage audit: ADEQUATE / PARTIAL / GAP országonként, hivatalos forrás jelzéssel |
| Heti ablak | futás pillanatától visszafelé 7 nap (UTC), hétfőn | Budapest szerda 00:00 → kedd 23:59:59, szerda reggeli futás, átállás nap-vesztés nélkül |
| Késői adat | a frissesség az ablak elejéhez mérve | az előző **publikálás** idejéhez mérve, `late_arriving` jelöléssel |
| Újrafuttatás | csendben felülírta a hetet | nem ír; csak `--restate "<ok>"`, látható sávval |
| Új ítélet a vezetői rétegben | — | csak jelölt executive synthesis, hivatkozással, validálva, visszatartott ítéletből soha |
| Változástábla | Since last week (részletes rétegben) | ugyanabból: Executive change table HU-relevanciával és prioritással (nincs új baseline) |
| Térkép | nincs | CEE (HU-relevancia) + globális (significance), determinisztikus SVG |
| Kereszthivatkozás | — | D-xx / KJ-xx horgonyok; PDF-ben szöveges hivatkozás |
| Approval / napi gyűjtés | — | változatlan (rejected kizárva, pending jelölve — tesztelve) |

## 9. Ismert korlátok / következő lépések

- A **review felület** (article approval) szemantikája szándékosan változatlan; a javasolt bővítések (AI relevancia-javaslat, ország, domain, újdonság, duplikátum, indoklás) ebben a körben nem készültek el.
- A „Next 7–30 days” csak a napokon/heteken belüli watch-tételekből épül — dátumozott regionális eseménynaptár (gyakorlatok, átadások) nincs a gyűjtésben.
- Régi payloadnál (v3.1 előtt) az ország a mellékelt eseményekből, végső esetben a címből származik — a backfill ezért kevésbé pontos, mint egy éles szerdai futás.
- A coverage audit ma minden prioritási országra „nincs hivatalos forrás”-t mutat. A jelölt források felvétele a következő lépés, feedenként ellenőrizve.
- Az executive synthesis heti egy rövid Sonnet-hívás (nagyságrendileg néhány cent); kikapcsolható.
