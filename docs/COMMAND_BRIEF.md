# Command Air Intelligence Brief — v2 (2026-11)

A Command Brief **önálló termék**: 4 vezetői oldal és egy 5. oldal (Sources & Legend), magyar fókusszal. A részletes heti jelentés (Detailed Weekly Report) külön elemzői termék marad, és a brief nélküle is érthető. Nem új pipeline: a brief ugyanabból a heti, befagyasztott korpuszból és ugyanazokból az elemzői objektumokból épül (developments, key judgements, programme state, confidence, significance, lineage, watch items), ugyanabban a szerdai futásban.

Három formátum, **egyetlen kanonikus adatmodellből** (`payload.command_brief`, schema `command_brief_v2`):

| Formátum | Hol | Hogyan készül |
|---|---|---|
| Web | `/weekly/command-brief`, `/weekly/<hét>/command` | React, ugyanaz az adatmodell |
| PDF | „Download PDF” gomb | a web nézet nyomtatási CSS-e: **pontosan 5 fix A4 fekvő oldal** (4 vezetői + Sources & Legend); kanonikus csak APPROVED / RELEASED draftból |
| Word (.docx) | „Download Word (.docx)” gomb, `/api/command-brief/<hét>/docx` | `docx` könyvtár ugyanabból az adatmodellből — **nem a PDF-ből konvertálva**; szerkeszthető munkapéldány, minden mező stabil `CB_*` content control, folyamatos tördeléssel (W45: 9 oldal, nincs közel üres köztes oldal) |
| Word template (.dotx) | `templates/Command_Air_Intelligence_Brief.dotx`, `/api/command-brief/template` | ugyanaz a renderer és schema, helyőrzőkkel — hivatalos manuális fallback |

A Word-fájl szerkesztése nem módosítja a rendszerben tárolt jelentést (a dokumentumon: `EDITABLE EXPORT — GENERATED FROM AIRCRAFT TRACKER`). A kanonikus publikáció a web/PDF.

## 0. Szerkesztési modell (PO-döntés, 2026-11) — Analytical truth → Draft → Release

Részletes eljárás: [`COMMAND_BRIEF_SOP.md`](COMMAND_BRIEF_SOP.md) · 1 oldalas: [`Command_Brief_Quick_Guide.md`](Command_Brief_Quick_Guide.md) ([PDF](Command_Brief_Quick_Guide.pdf)).

| Réteg | Tartalom | Tárolás | Ki írja |
|---|---|---|---|
| **A. Analytical truth** | cikkek, események, evidence, értékelés, confidence, significance, lineage | `ac_events`, `ac_reports.payload` elemzői kulcsai | pipeline + elemzői workflow — a brief-szerkesztő **soha** |
| **B. Command Brief Draft** | generált brief (`payload.command_brief`) + **publikációs szöveg** (overrides), rejtés, sorrend, státusz, audit | `ac_reports.payload.command_brief_draft` | webes szerkesztő (`/weekly/<hét>/command/edit`) |
| **C. Released product** | APPROVED draftból fagyasztott kiadás (R-n): publikált brief, jóváhagyó, kiadó, template/módszertan/HU-modell verzió, SHA-256 | `command_brief_draft.releases[]` | *Release* művelet |

- **Presentation Schema** — `config/command_brief_presentation.json` (template **v1.0**): oldalak és blokkok sorrendje, mezőnevek, szerkeszthető (*copy*) vs. kontrollált (*controlled*) vs. fix mezők, max. hossz / mondatszám, max. tételszám, címkék, táblázat-oszlopok, színszemantika (mindig szöveges címkével), jelmagyarázat, státusz-átmenetek, Word `CB_*` címkék. Ebből dolgozik a Python generátor (legend, principles, micro-legend, register-szöveg), a web/PDF, a DOCX és a .dotx. Teszt: a schema hosszai = a generátor budgetje, a tételszámok = a generátor limitjei, a Word-címkék egyediek. A web a `web/src/lib/command_brief_presentation.json` tükörpéldányt olvassa (a Vercel build csak a `web/` mappát látja); a kettő egyezését a teszt ellenőrzi, a `node scripts/build_dotx.cjs` szinkronizálja.
- **Csak publication copy szerkeszthető.** Forrás, lineage, publikációs dátum, evidence role, HU szint, SIG, CONF, horizon, collection status, a teljes forrásjegyzék **kontrollált** — a szerkesztő csak olvasható címkeként mutatja, az API 400-zal elutasítja. Az eredeti generált szöveg változatlan marad; az override a saját alapszövegét is tárolja.
- **Verziózás / audit:** minden mentés új revízió; audit-bejegyzés: actor, időbélyeg, mező, előző és új érték; státusz-átmenetek naplózva. Optimista zárolás: elavult revízióra mentés → 409 (senki munkája nem íródik felül csendben).
- **Státuszok:** GENERATED → EDITING → READY_FOR_APPROVAL → APPROVED → RELEASED. Jóváhagyás utáni tartalmi szerkesztés → EDITING (jóváhagyás érvénytelen). Restatement / backfill után a generált alap megváltozik: a szerkesztett mezők *stale* jelzést kapnak, a jóváhagyás érvényét veszti, Release tiltva amíg újra nincs jóváhagyva. A Python írók (`generate_weekly_report --restate`, `backfill_command_brief --write`) a draftot **átviszik** (audit: `rebase`), nem törlik.
- **Kanonikus PDF csak APPROVED / RELEASED** állapotból; minden más állapotban minden oldalon *WORKING COPY — … · NOT APPROVED* bélyeg, és a gomb „Print working copy (not approved)”. A nyilvános nézet a legutóbbi kiadást mutatja (`?view=draft` munkapéldány, `?release=N` adott kiadás); ha kiadás után újabb draft van, azt jelzi.
- **Word = munkapéldány**, bármely státuszból; fájlnév `_WORKING_COPY` / `_R<n>`; dokumentum-tulajdonságok: `CB_TEMPLATE_VERSION`, `CB_DRAFT_STATUS`, `CB_RELEASE`, `CB_CANONICAL=false`. Content controls: publikációs mezők szerkeszthetők (`sdtLocked`), kontrollált metaadat és fix design-szöveg tartalom-zárolt (`sdtContentLocked`), térképek kép-vezérlőben.
- **Tárolás SQL nélkül:** a draft a heti jelentés sorában van (`payload.command_brief_draft`), így nincs új tábla és nincs kézi migráció; a szerkesztő a service-role kulccsal a szerver oldalon ír (mint a review-oldal). Opcionális védelem: `BRIEF_EDITOR_TOKEN` környezeti változó — ha be van állítva, az író kérésekhez kell.
- **Template-verziózás:** `templates/Command_Air_Intelligence_Brief_v1.0.dotx` + `templates/command_brief_presentation_v1.0.json` archiválva; a brief és minden kiadás metaadata tartalmazza a template-, módszertan- és HU-modell-verziót. Template újragenerálása: `cd web && node scripts/build_dotx.cjs`.

## 1. Oldalak

**Page 1 — Hungary Air Intelligence Bottom Line.** Bottom line (5–7 egész mondat, forrásokkal); **legfeljebb 3 PRIMARY KJ** (HU relevance → significance → confidence → immediacy). LOW/MINIMAL HU-relevancia csak kivétellel kerülhet ide (significance 5 + high confidence, vagy a PO strategic watch listája a `config/hungary_relevance.json`-ban). Minden primary KJ: What changed · Assessment · Why Hungary should care · Next observable · What would make this wrong · Sources S-xx. Alatta **Secondary Air Power Watch** (≤3 rövid sor): globálisan fontos, de alacsony HU-relevanciájú tételek. CEE térkép: HU-relevancia szerinti hotspotok, collection gap szaggatottan.

**Page 2 — Immediate & Near-Regional Air Picture.** A táblázat marad (non-NATO prioritás, szomszédok, kiterjesztett regionális NATO; csak anyagi változás). *No material change identified* csak legalább PARTIAL lefedettségnél, különben *Collection gap*. A felszabaduló hely: **Regional collection requirements** — gap → intelligence question → desired observable (`config/collection_requirements.json`, országonként szerkeszthető).

**Page 3 — Extended Air Power Picture.** Kompakt Közel-Kelet / Afrika / tágabb NATO blokkok (≤3), **Capability change / maturity matrix** (Intent → Committed → Contracted → Fielding → IOC → FOC; a meglévő életciklus-érettségből, új adatmodell nélkül; veszteség/kivonás külön), **Executive change table** (az előző publikált jelentéshez).

**Page 4 — Global Strategic Air Power Watch.** Globális stratégiai tételek, globális térkép (significance szerint — nem HU-relevancia), Priority Intelligence Watch (≤5), Intelligence Gaps (≤5), **Outlook & expected observables — next 7–30 days** (a fő tételek következő ellenőrizhető jele; intelligence outlook, nem eseménynaptár).

**Page 5 — Sources & Legend.** Source register (ID · forrás + tier · eredeti nyelvű, kattintható cím · publikálás · ország · forrástípus · nyelv · lineage · melyik tétel használja), állandó, teljes jelmagyarázat (HU relevance, SIG, CONF, horizon, collection status, terminológia) és az elemzői fegyelem elvei (significance ≠ confidence, procurement ≠ operational capability, delivery ≠ IOC, multiple articles ≠ independent lineage, official statement ≠ independent confirmation). Minden oldal alján egysoros **micro-legend**.

## 2. Forrás-nyomonkövetés (javítva 2026-11-08, PO blocker 1)

Minden vezetői tétel `Sources: S-01 (official) · S-02` hivatkozást kap az általa megnevezett publikációra (webben és PDF-ben kattintható, Wordben hiperhivatkozás). Szabályok:

- **Csak közvetlen bizonyíték hivatkozható.** Egy forrás akkor szerepel egy tétel forrásaként, ha a címe vagy összefoglalója a tétel tárgyát (típusjel / típusnév — cirill írással is, pl. Су-57Э) közvetlenül megnevezi. Ha az állítás csak egy más témájú cikk törzsében szerepel (W45: a lengyel FA-50 QRA állítás egyetlen gyűjtött cikke egy MiG-29-átadásról szólt), a cikk **Context — not cited as evidence**: a jegyzékben látszik, de nem bizonyíték. Közvetlen forrás nélküli tétel **nem lehet Primary KJ**, és a 2. oldalon „No direct source” jelölést kap.
- **Hivatalos forrás elöl.** Egy tételen belül a Tier 1 (légierő, MoD, haderő, beszerzési hatóság, NATO) forrás az első („official” jelöléssel), a szakmédia „Corroborating”.
- **Ellenőrzött, verziókezelt csatolt bizonyíték:** `config/evidence_supplements.json`. W45: a lengyel FA-50GF harci készültségbe lépéséről a honvédelmi miniszter 2026-10-02-i közlése (X), a Defence24.pl (10-03), a Militarnyi (10-03) és az Aviation Week (10-05) — mindegyik megnyitva és ellenőrizve 2026-11-08-án. Mivel mind ugyanazt a miniszteri közlést adja vissza, **egy lineage**.
- **`Published` = a publikáció saját dátuma** (feed, ennek híján a cikk URL-jében lévő dátum, csatolt bizonyítéknál az ellenőrzött dátum) — soha nem esemény-, szerződés-, mérföldkő- vagy gyűjtési dátum; ha nincs, üres („not recorded”). Lásd `docs/DATE_SEMANTICS.md`.
- A forrásjegyzék címe „Source register — evidence behind each judgement”; ha egy héten nincs hivatalos forrás, a jegyzet ezt kimondja.
- Lineage: egy evidencia-lánc egy `L-xx`; állami ellenőrzés alatti forrás (orosz, belarusz, kínai, iráni stb.) mindig attribúcióval, egy állam összes közlése egy lineage.

## 3. Csonkolás nélkül

A vezetői szöveg mindig egész mondatokból áll (`fit()` sosem vág mondatot, nincs „…”). Ha egy mező egész mondatként is hosszú, a validált **executive editor** (ugyanabban a rövid modellhívásban, mint az executive synthesis) rövidebb, teljes mondatra írja át — csak akkor fogadjuk el, ha nem hoz új számot vagy országot, és megtartja a hedge-et/tagadást. Különben az eredeti egész mondat marad, és a layout alkalmazkodik. A böngészős teszt mind a szintetikus, mind a valós W45 adaton ellenőrzi, hogy az 1–4. oldalon semmi nem lóg ki.

## 4. Hungary relevance — hu-1.1

A v1 modell működött, két finomítással: (1) a **supplier/partner kapcsolat legfeljebb egy kis faktor** (6 pont, távoli szereplőnél 3) — Etiópia Su-35SE + Oroszország így MINIMAL, nem LOW; (2) a **HIGH elérhető, ha indokolt**: új faktorok — *Capability milestone next door* (szomszéd / non-NATO prioritás harci képesség-mérföldköve, +12), *Regional QRA / air policing change* (+16), *Capability adoption / NATO doctrinal relevance* (uncrewed / C-UAS, SIG ≥4, +10). Eredmény W45-ön: Lengyelország FA-50 QRA → HIGH (59), Ukrajna Rafale-képzés → HIGH (63), kínai GJ-21 → LOW (doktrinális), etióp Su-35 → MINIMAL.

## 5. Gyűjtés

- **Coverage audit** (`scripts/coverage_audit.py`): a közvetlen régió 17 országa mellett Közel-Kelet, Afrika és Indo-Pacific csoportok, országonként ADEQUATE / PARTIAL / GAP, hivatalos-forrás jelzéssel. W45: a 17 regionális prioritásból **10 GAP** (Szerbia, Belarusz, BiH, Ausztria, Szlovákia, Horvátország, Szlovénia, Bulgária, Észtország, Lettország), és egyikre sincs hivatalos forrás. Az Indo-Pacific szinte teljesen ADEQUATE (Kína PARTIAL); a Közel-Keleten Irán és az Emírségek GAP.
- **Forrásprioritás:** Tier 1 hivatalos (légierő, MoD, haderő, beszerzési hatóság, NATO, kormányzati ügynökség) → Tier 2 ipar (OEM) → Tier 3 szakmédia → Tier 4 regionális média (csak ha magasabb nem fedi).
- **RSS/Atom felderítés** (`scripts/source_discovery.py`, csak olvas): a jelölt forrásokon `<link rel=alternate>` + szokásos útvonalak, validált feed, elemszám, legfrissebb dátum → `data/source_discovery.json`. RSS preferált, nem kötelező; ahol nincs feed, „page polling” jelölt.
- **Célzott bővítés** (`config/source_expansion.json`, `scripts/add_sources.py` — csak az új forrásokat veszi fel, a meglévőkhöz és a policy által kikapcsoltakhoz nem nyúl): **ACS-0016 Serbian Ministry of Defence** (RSS ellenőrizve, szerb cirill — Tier 1, a GAP-ország Szerbia lefedésére) és **ACS-0017 Defence24** (RSS ellenőrizve, lengyel/CEE szakmédia). Mindkettő a Haiku-kapu mögött; nem angol nyelvű forrásnál az angol kulcsszó-előszűrő kimarad, a többnyelvű olcsó kapu dönt, az eredeti nyelvű cím megmarad.
- **Review triage** (`scripts/triage_events.py`; séma: `supabase/add_review_triage.sql`, a `supabase/migrations.txt` sorrendjében — additív, idempotens, `scripts/test_migrations.py` friss és meglévő adatbázison ellenőrzi; a migráció nélkül a triage lépés kimarad, a review-sor változatlanul működik): tanácsadó besorolás minden pending eseményre — ország, forrás, tier, domain, HU relevance, AI relevance, újdonság (programhoz képest), duplikátum-valószínűség, materialitás, indoklás; osztály: *likely material / routine / likely duplicate / low relevance*. A review-sor ezek szerint rendez; bulk *Select likely material* és *Select duplicates + low relevance*, a meglévő bulk approve/reject-tel. **A jóváhagyás szemantikája változatlan** — a triage soha nem állít `review_status`-t.

## 6. Ellenőrzés (2026-11-08)

| Teszt | Eredmény |
|---|---|
| Meglévő regresszió (`test_ac_match`, `test_ac_programmes`, `test_report_integration`, `test_programme_write` valódi PostgreSQL-lel) | PASS |
| `test_command_brief.py` — ablak/DST, HU-modell (v2 finomítások), brief v2 (max 3 primary, nincs „…”, források, gap→kérdés, maturity, outlook, register, állami lineage, legend), synthesis + executive editor validáció, a valódi `generate_weekly_report.main()` memória-adatbázison, review triage | PASS |
| `test_command_brief.py` G: forrás-nyomonkövetés és publikációs dátum (kontextus-cikk nem bizonyíték, közvetlen forrás nélkül nincs Primary KJ, hivatalos forrás elöl, közös lineage, `Published` soha nem eseménydátum, feed > URL > üres) | PASS |
| `test_migrations.py`: friss adatbázis (teljes sorrend, kétszer), meglévő adatbázis (adatok változatlanok, checksum), nem destruktív, futásidő migráció nélkül | PASS |
| `next build` (típusellenőrzéssel) | PASS |
| Böngészős E2E (`web/e2e/command-brief.e2e.cjs`) a szintetikus és a **valós W45** adaton: 4+1 oldal, az 1–4. nem csordul túl, micro-legend minden oldalon, nincs „…”, nincs „Detailed assessment →”, minden S-xx az eredeti URL-re és a registerre mutat, PDF = 5 A4 fekvő oldal, DOCX letöltés, régi hét 404 (nem hibás fájl), a részletes jelentés külön és ép, a meglévő route-ok működnek | PASS |
| Word/PDF egyezés (`web/e2e/check_parity.py`): OOXML séma-validáció (Word-kompatibilitás), nincs ZIP mappa-bejegyzés, valódi stílusok (Title, Heading 1–3, Caption, Header, Footer, Brief Table, Hyperlink) használatban, fejléc + lábléc oldalszámmal, minden forrás hiperhivatkozás, térképek 2400 px szélesek, magyar ékezetek épek, **mind a 107 (W45) / 114 (fixture) vezetői szöveg szerepel a PDF-ben és a Wordben is** | PASS |

## 7. BEFORE / AFTER — ugyanaz a 2026-W45 korpusz

| | Command Brief v1 | Command Brief v2 |
|---|---|---|
| Termék | a részletes jelentés első 4 oldala | önálló 4+1 oldal; a részletes jelentés külön analyst product |
| Page 1 | 5 egyforma KJ-kártya, köztük 2 MINIMAL (Kína, MQ-25) és 1 LOW (Etiópia) | 2 PRIMARY (Lengyelország FA-50 QRA, Ukrajna Rafale — mindkettő HU HIGH) + 3 sor Secondary Watch (Kína, MQ-25, Etiópia) |
| Levágott szöveg | 22 „…” a vezetői szövegben | 0 — csak egész mondatok |
| HU-relevancia | Lengyelország és Ukrajna MEDIUM; Etiópia LOW a „Russia” supplier miatt; Oroszország hotspot az etióp vásárlás miatt | Lengyelország és Ukrajna HIGH (QRA-változás, szomszédos képesség-mérföldkő); Etiópia MINIMAL; Oroszország nem hotspot |
| Nyomonkövetés | `→ Detailed assessment D-06` (belső oldalra) | 12 hivatkozott forrás (S-01…S-12) kattintható címmel, tierrel, szereppel, lineage-dzsel; a lengyel FA-50 tételnél elöl a hivatalos miniszteri közlés (S-01), a MiG-29-cikk csak kontextus (S-13) |
| Üres terület p. 2 | üres | 6 regionális gyűjtési követelmény (Szerbia, Belarusz, BiH, Ausztria, Szlovákia, Horvátország) |
| Page 3 | sok üres hely | maturity matrix (7 fejlemény) + változástábla |
| Outlook | „No dated, intelligence-relevant event” | 5 expected observable a fő tételekre |
| Jelmagyarázat | szétszórt | micro-legend minden oldalon + teljes legend a p. 5-ön |
| Revision | hangsúlyos RESTATEMENT sáv minden oldalon | kis „rev.” jelölés a fejlécben, részletek a p. 5-ön |
| Formátum | web + PDF | web + PDF + szerkeszthető Word |

**Megmaradt collection gapek (W45):** Szerbia (az új MoD-feed szerdától gyűjt), Belarusz, Bosznia-Hercegovina, Ausztria, Szlovákia, Horvátország, Szlovénia, Bulgária, Észtország, Lettország; Irán, Egyesült Arab Emírségek, Nigéria, Dél-Afrika, Líbia. A következő lépés a `source_discovery.py` lefuttatása és a talált hivatalos feedek felvétele `source_expansion.json`-ba.

## 9. Szerkesztési modell — ellenőrzés és BEFORE / AFTER (2026-11-08)

| Teszt | Eredmény |
|---|---|
| `test_command_brief.py` (198 ellenőrzés), új: **G** S-13 kontextus-szemantika (CONTEXT_ONLY, üres „Evidence for”, külön „Context for”, nincs lineage, soha nincs `sources` listában), **H** backfill `anthropic` nélkül + a draft átvitele, **E** restatement megtartja a draftot és a kiadásokat (audit: rebase), **I** Presentation Schema = generátor (hosszak, tételszámok, legend, egyedi `CB_*` címkék, kontrollált mező nem szerkeszthető) | PASS |
| `test_migrations.py`, `test_ac_match`, `test_ac_programmes`, `test_report_integration`, `test_programme_write` | PASS |
| `web/e2e/draft.unit.cjs` (46): copy-mező szerkesztés + audit (actor, idő, mező, előtte/utána), kontrollált mezők (sources, HU, SIG, CONF, horizon, refs, forrásjegyzék) elutasítva, „…”/üres/kemény limit/név nélkül elutasítva, rejtés/sorrend/revert, státuszgép, kiadás hash-sel és verziókkal, kiadás utáni szerkesztés, restatement → stale + jóváhagyás érvénytelen + Release tiltva, régi briefek S-13 normalizálása | PASS (fixture + valós W45) |
| Böngészős E2E (`web/e2e/command-brief.e2e.cjs`, ~195 ellenőrzés): generált nézet minden oldalon WORKING COPY bélyeggel, **PDF pontosan 5 oldal** (munkapéldány és kiadás is), register evidence role / Context for oszlopok; szerkesztő: blokkok, read-only kontrollált címkék, élő előnézet, **túlcsordulás-figyelmeztetés**, mentés → EDITING, audit-napló, API 400 kontrollált mezőre és forrásjegyzékre, **409 elavult revízióra**, az alap (elemzői) szöveg változatlan; Submit → Approve (másik név) → Release; kiadott nézet RELEASED R-1 bélyeggel és a szerkesztett szöveggel, kanonikus „Download PDF”, DOCX `_R1`; kiadás utáni szerkesztés a kiadást megtartja és jelzi; .dotx letöltés; meglévő route-ok | PASS (fixture + valós W45) |
| `web/e2e/check_parity.py`: OOXML **XSD-validáció** (ISO/IEC 29500), stílusok, fejléc/lábléc oldalszámmal, **334 / 315 content control**, minden publikációs mező `CB_*` vezérlő (109 / 103), fix szöveg és kontrollált metaadat tartalom-zárolt, publikációs mezők szerkeszthetők, térképek kép-vezérlőben 2400 px, dokumentum-tulajdonságok (template-verzió, státusz, kiadás, nem kanonikus), forrás-hiperhivatkozások, „Context for” oszlop, **mind a 157 / 147 publikációs szöveg a PDF-ben és a Wordben**, ékezetek (HU/PL), LibreOffice-render: **9 oldal, nincs közel üres oldal** | PASS |
| `web/e2e/check_template.py` (.dotx): template content type, XSD, a schema mind a 200+ címkéje vezérlő, helyőrzők (showingPlcHdr), fix szöveg zárolt, kép-helyőrzők, template-verzió, LibreOffice-render 10 oldal, nincs közel üres köztes oldal | PASS |
| `next build` (típusellenőrzéssel) | PASS |

**Microsoft Word:** ebben a környezetben nincs Word-automatizálás. A Word-kompatibilitást az ISO/IEC 29500 XSD-validáció és a LibreOffice-megnyitás/-render támasztja alá — **Wordben megnyitva nem ellenőriztük**; ezt az első használatkor egy Wordös gépen érdemes megnézni (content controls, helyőrzők, kép-csere).

| W45 (ugyanaz a tárolt brief) | BEFORE (bceaf71) | AFTER |
|---|---|---|
| Kanonikus PDF | 6 oldal (Analytical discipline + Document blokk külön oldalra tört) | **5 oldal**; a Page 5 fix oldal: tömörebb register, 4 hasábos legend + Analytical discipline, dokumentum-metaadat a láblécben |
| S-13 (MiG-29-cikk) | „Context — not cited as evidence”, de *Used by: KJ-05, p.2 Poland, p.4 outlook* és lineage L-10 | Evidence role **Context only — not evidence**, *Evidence for: —*, külön **Context for: KJ-05, p.2 Poland, p.4 outlook**, lineage **—**; a lineage-számozás csak bizonyítékon |
| Státusz / jóváhagyás | nincs; minden generált brief „kész” termékként jelent meg | GENERATED → … → RELEASED; nem jóváhagyott nyomat minden oldalon WORKING COPY bélyeg |
| Szerkesztés | csak a letöltött Wordben, nyomon követés nélkül | strukturált webes szerkesztő, élő előnézet, verziózott audit, kiadások hash-sel |
| Word | 10 oldal, címkék nélkül | 9 oldal, 315 content control (`CB_KJ1_ASSESSMENT` …), zárolt fix szöveg és metaadat |
| Fallback | nincs | `Command_Air_Intelligence_Brief.dotx` v1.0 + SOP + 1 oldalas Quick Guide |
| Megjelenítési szabvány | a szövegek a Python-kódban és a rendererekben szétszórva | egy `command_brief_presentation.json` (template v1.0) |

A tárolt W45 brief a webes nézetben már a javított szemantikával jelenik meg (régi briefek megjelenítéskori normalizálása — a tárolt adathoz nem nyúl). A `backfill_command_brief.py --week 2026-W45 --write --reason "..."` futtatása a tárolt briefbe is beírja az új mezőket (evidence_role, context_for, template_version, rövidebb register-jegyzet) — ez restatementként látszik; a draft (ha már van) átkerül.

## 8. Ismert korlátok

- A „Download PDF” a böngésző nyomtatásából készül (Save as PDF); szerveroldali PDF-generálás nincs (a Vercel serverless környezetben nincs böngésző).
- A Word-export oldaltörései eltérhetnek a PDF-től (szándékosan: a szerkeszthetőség fontosabb), a tartalom azonos.
- Nem RSS-es hivatalos oldalak lekérdezése („page polling”) még nincs megvalósítva — dokumentált jelöltként szerepelnek.
- A triage szabályalapú, az AI-kinyerés mezőire épül (külön modellhívás nélkül).
- A szerkesztő „Analyst” neve önbevallás (a webalkalmazásban nincs bejelentkezés — ugyanúgy, mint a review-oldalon). Az audit így ki-mit-mikor nyomot ad, nem hitelesített azonosítót. Opcionális író-token: `BRIEF_EDITOR_TOKEN`.
- A draft (és az audit-napló nevei) a jelentés sorában van, így ugyanazzal a publikus olvasási joggal olvasható, mint maga a jelentés.
- A Python írók (restatement / backfill) közvetlenül írás előtt olvassák újra a draftot; egy ugyanabban a néhány másodpercben történő webes mentés elveszhet (ritka, a restatement kézi indítású).
- A forrásjegyzék „Evidence for” oszlopa a generált brief tételeire hivatkozik; egy szerkesztőben elrejtett tétel ott továbbra is szerepelhet (a register kontrollált adat).
