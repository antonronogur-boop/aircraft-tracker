# Aircraft Procurement Tracker — rendszerspecifikáció

> **Kinek szól ez a dokumentum.** Egy másik AI-nak (vagy fejlesztőnek), aki a
> kódbázison fog dolgozni. Nem bevezető: azt írja le, *mit csinál a rendszer
> most*, és — ami fontosabb — **miért úgy**. A „miért" szakaszok nem
> magyarázkodás: olyan hibákat zárnak le, amelyek egyszer már megtörténtek, és
> egy jóhiszemű „egyszerűsítés" bármelyiket visszahozná.
>
> Állapot: 2026-10-08. Séma-verzió: `v3.0` (`METHODOLOGY_VERSION`).
> Élő: https://aircraft-tracker-three.vercel.app/

---

## 1. Mi ez

Ország-központú katonai repülőgép-flotta követő. Napi RSS-gyűjtésből épít
eseménytörténetet arról, **ki rendel, kap, modernizál, elad, kivon vagy veszít
el** milyen repülőgépet, és ebből hetente egy **légierő-fejlesztési felderítői
jelentést** állít elő.

A termék **nem** piaci hírösszefoglaló. A vezető kérdése nem az, hogy hány
esemény került az adatbázisba, hanem:

> Melyik 3–5 fejlemény változtatja meg a következő 6–36 hónap légi
> képességképét, mennyire biztos, mikorra hat, és mit jelent ránk nézve?

Ebből következik a teljes szerkezet: a szelekció **képességhatás** szerint
történik, nem szerződésérték szerint, és minden állítás mellett ott áll a
bizonyosság, az időhorizont és a forráslánc.

**Technológia:** RSS → Claude-extrakció → Supabase (PostgreSQL, `ac_` prefixű
táblák) → Next.js 14 + Tailwind (Vercel). A Supabase projekt **közös** a
Drone/UAV Monitorral és a Balkan Monitorral; az elkülönítés a tábla-prefix.

---

## 2. A központi fogalmi elválasztás

Ez a rendszer legfontosabb tulajdonsága. Ha ebből bármit összevonsz, a
hibák azonnal visszatérnek.

```
EVIDENCE   — mit állít egy forrás            (ac_articles, ac_event_evidence)
EVENT      — mi történt / mi jelent meg      (ac_events)
PROGRAMME  — a tartós valóság                (ac_programmes)
```

A heti jelentés **ebben az irányban** épül:

```
EVIDENCE  →  EVENT  →  PROGRAMME STATE CHANGE
```

és **soha** nem így:

```
ARTICLE  →  quantity  →  ORBAT += quantity
```

### Miért

A v2-ben nem volt programme-réteg. Ugyanarról a lengyel AH-64E beszerzésről
szóló minden újabb cikk új rendelésnek látszott:

| hét | ORBAT „on order" | heti sor |
|---|---|---|
| W33 | 190 | `Contract signed ×94` |
| W34 | 286 | `Contract signed ×96` |

Egyetlen valós program létezik (96 gép, 2024. augusztusi szerződés). A 190, a
94 és a 96 ugyanannak a programnak különböző forrás-állításai. A régi logika
380-ra, majd tovább kúszott volna. Egy procurement-adatbázisnál ez évek alatt
elszakítja a baseline-t a valóságtól.

**A javítás nem okosabb összegzés, hanem hogy nem összegzünk:**

```python
on_order = programme.contracted_quantity     # a program állapota
# NEM:
on_order = previous_on_order + article_quantity
```

---

## 3. Adatmodell

### 3.1 Alaptáblák (`supabase/schema.sql`)

| tábla | tartalom |
|---|---|
| `ac_aircraft_types` | katalógus: `type_id` (slug), `name`, `designation`, `category`, `aliases` (jsonb) |
| `ac_countries` | `country_id` (ISO-3 kisbetűs), `name`, `region`, `aliases` |
| `ac_fleets` | baseline: ország × típus × `fleet_status` × `quantity` |
| `ac_sources` | RSS-források, `enabled`, `reliability_score` |
| `ac_articles` | gyűjtött cikkek, `status`: `raw \| processed \| irrelevant \| failed` |
| `ac_events` | az AI által kinyert események |

### 3.2 `ac_events` — a három réteg

```
alap:  event_id article_id event_type country_id type_id counterparty_country_id
       quantity value_usd_m event_date summary confidence review_status
       unresolved_type_name unresolved_country_name created_at

v2:    lifecycle_stage value_type value_currency_year capability_domain
       delivery_start_year delivery_end_year expected_ioc_year
       announcement_date reports_count independent_lineages updated_at

v3:    programme_id variant_raw type_match_kind quantity_claimed on_order_delta
       first_reported_at new_evidence_at assessment_updated_at evidence_kind
       originating_evidence_id milestone_kind foc_year meaningful_scale_year
       schedule_change
```

**A v3 kulcsmezői és a szemantikájuk:**

- `quantity_claimed` — amit a forrás **állít**. Önmagában nem mozgat semmit.
- `on_order_delta` — amennyivel az ORBAT `on_order` ténylegesen változik.
  **Alapértelmezésben 0.** Csak elfogadott szerződés-evidencia és
  programme-szintű hatókör esetén nem nulla.
- `evidence_kind` — `new_event` | `new_confirmation` | `reassessment` |
  `correction`. Ez dönti el, hogy az elem **e heti hír**-e. Egy 2025-ös
  veszteség 2026-os vizuális igazolása `new_confirmation`: az `event_date`
  marad 2025, a `new_evidence_at` lesz 2026.
- `originating_evidence_id` — a **forráslánc gyökere** (gyártói közlemény,
  DSCA-notifikáció, minisztériumi nyilatkozat), nem a publikáló lap. Három
  szaklap ugyanarról a Boeing-közleményről **egy** lánc.
- `type_match_kind` — `exact | variant | family | none`. Ha `variant`, az ORBAT
  **nem** rendelhet család-szintű baseline-t az eseményhez.
- `milestone_kind` — lásd 6.3. Egy **késés** nem képesség-érkezés.

### 3.3 `ac_programmes` — a tartós valóság (`add_programme_layer.sql`)

Azonosító: stabil, ember által olvasható kulcs, `ac_programmes.programme_key()`
által generálva:

```
<ország>-<típus><variáns>[-<haderőnem>][-<fajta>]-<horgony-év>

pol-ah64e-2024          lengyel AH-64E beszerzés
pol-ah64e-sustai-2026   a hozzá tartozó MRO-program KÜLÖN
usa-uh60hh60w-usaf-2020 USAF HH-60W, NEM UH-60M
```

A horgony-év a program **indulása** (első evidencia), nem az aktuális hét —
így a későbbi cikkek ugyanahhoz a kulcshoz vezetnek.

**Programfajták** (`PROGRAMME_KINDS`):
`acquisition`, `upgrade`, `sustainment_mro`, `infrastructure`, `training`,
`retirement`, `lease`, `development`, `attrition`.

Két származtatott halmaz:

```python
NO_CANONICAL_QUANTITY = {"attrition", "infrastructure", "sustainment_mro"}
NO_AIRFRAME_ARRIVAL   = {"sustainment_mro", "infrastructure", "training"}
```

### 3.4 A kettős darabszám

**Ez a leggyakrabban félreértett rész.** Egy programnak **két** darabszáma van,
és ezek nem ellentmondásosak:

| mező | jelentés | példa (`tur-kaan-2026`) |
|---|---|---|
| `contracted_quantity` | ami firm szerződés alatt van | 20 |
| `planned_quantity` | a bejelentett/tervezett teljes program | 148 |
| `canonical_quantity` | **származtatott** fejszám: contracted, ha van; különben planned | 20 |
| `canonical_source` | `contracted` \| `planned` | contracted |

Ugyanez az ukrán Gripennél: 16 szerződött, „up to 150" szándéknyilatkozat.

Az `on_order` **kizárólag** a `contracted_quantity`-ből származhat. Egy
„148 tervezett sorozatgyártás" nem rendelési állomány.

**Miért:** egyetlen mezőbe zsúfolva vagy az egyik elveszett, vagy a kettő
ellentmondásnak látszott, és a rendszer „konfliktusként" jelezte azt, ami
valójában két különböző mérték. Ez ugyanaz a hibaosztály, mint az összeadás,
csak harmadik alakban: **összemosás**.

Kísérő mezők:
- `superseded_quantities` (jsonb) — felülírt értékek, nem vesznek el
- `quantity_conflicts` (jsonb) — valódi ellentmondás elemzői döntésre
- `observed_quantities` (jsonb) — részszállítás, prototípus, nem-gép tétel
- `claim_history` (jsonb) — minden evidencia nyoma

### 3.5 További táblák

- `ac_event_evidence` — explicit forrásláncok (`origin_kind`, `origin_ref`)
- `ac_reports` — heti jelentés teljes payloadja (jsonb), `week_label` kulcson
- `ac_report_metrics` — a **publikált** heti metrikák változatlan
  pillanatfelvétele. A WoW ebből számol (lásd 6.4).
- `ac_fleets` kiegészítés: `service`, `baseline_scope`, `programme_id`;
  unique kulcs: `(country_id, type_id, fleet_status, coalesce(variant,''), coalesce(service,''))`

---

## 4. Pipeline

### 4.1 Napi gyűjtés — `collect_rss.py`
GitHub Actions, `aircraft_sync.yml`, **04:30 UTC**. Előszűrés: csak azok a
cikkek kerülnek be, amik katalógusbeli géptípust vagy beszerzési kulcsszót
említenek.

### 4.2 Forrás-szintű kapu — `source_policy.py` + `config/source_policy.json`

Három állapot forrásonként:

| állapot | viselkedés |
|---|---|
| `pass` | a szokásos (drága) Sonnet-kinyerés. **Alapértelmezés.** |
| `haiku_gate` | előbb egy olcsó modell dönt cím+összefoglaló alapján |
| `drop` | nincs modellhívás, a cikk `status='irrelevant'` |

**Két biztonsági szabály a kódban:**

1. **Ismeretlen forrás → `pass`.** A hallgatás nem jelenthet kizárást.
2. **Hibás/hiányzó config → minden `pass`.** Ha a konfiguráció nem olvasható,
   a rendszer a drága, de teljes feldolgozást választja. Egy elgépelt érték
   (`hakiu_gate`) figyelmeztetést ír és `pass` lesz — nem kapcsol ki kaput
   csendben.

A `drop` **nem törlés**: a cikk ugyanabba az állapotba kerül, amit a modell
adott volna neki, tehát auditálható és a policy módosításával újrafeldolgozható.

**Mérési alap** (2026-10-03): 8599 cikkből 1971 (23%) lett irreleváns, mind egy
teljes Sonnet-hívás árán. A pazarlás 65%-a nyolc forrásból jött.

### 4.3 Olcsó relevancia-kapu — `cheap_relevance_gate()`

`GATE_MODEL = claude-haiku-4-5`. A prompt a fő `PROMPT` hatókör-definíciójából
származik — ugyanazt a határt kell húznia.

**Aszimmetrikus hibakezelés:** a hibás NEM drágább a hibás IGEN-nél — egy
tévesen kizárt cikk véglegesen kimarad. Ezért **minden bizonytalan eset
átmegy** (API-hiba, értelmezhetetlen válasz → `None` → pass), és a prompt is
így zárul: *„If unsure, YES."*

A kapu validálása: `validate_relevance_gate.py` — már felcímkézett cikkeken
futtatja az **éles** kaput (fájlútvonal szerint betöltve a
`process_articles.py`-ból, hogy ne divergálhasson), és megmondja, hány
**releváns** cikket dobna el. Nem ír semmit. A tévesen eldobott **címeket**
kiírja — azt kell elolvasni, nem a százalékot.

### 4.4 Kinyerés — `process_articles.py`

`MODEL = claude-sonnet-4-6`, `BATCH_LIMIT = 25`, `FULLTEXT_MAX_CHARS = 12000`.

A rendszerprompt `cache_control: ephemeral` blokkban megy (`_cached()`) — a
modell pontosan ugyanazt látja, csak az ismétlődő előtag cache-találatként
számlázódik.

A prompt főbb kényszerei (a teljes szöveg a fájlban):

- **EVENT DATE DISCIPLINE** — az `event_date` az esemény megtörténtének napja.
  Egy 2026-os cikk egy 2020-as szerződésről **nem** tesz egy 2020-as eseményt
  e hetivé.
- **LIFECYCLE STAGE ≠ EVENT TYPE** — a DSCA/FMS-engedély `export_approval`,
  **nem** vásárlás; az értéke engedélyezési felső határ.
- **VARIANT AND SERVICE ARE NOT DECORATION** — a típusjelet pontosan úgy kell
  megadni, ahogy írták (`HH-60W`, nem `UH-60`).
- **ORIGINATING SOURCE** — a primer állítást nevezd meg, ne a lapot.
- **MILESTONE KIND** — egy késés `schedule_slip`, nem `first_delivery`.

Hibakezelés: tranziens API-hibákra 3 próbálkozás; **elfogyott kredit esetén a
futás azonnal megáll**, hogy a cikkek `raw`-ban maradjanak és a következő futás
folytathassa (különben mind `failed` lenne és kiesne).

`_safe_date()` — a modell néha csak `2026-07`-et ad; a `date` oszlop ezt
HTTP 400-zal utasítja el, és **egyetlen ilyen esemény az egész futást
leállította**. Most a hónap/év első napjára kerekít.

### 4.5 Entitás-illesztés — `ac_match.py`

**A legismertebb konkrét hiba, amit ez a modul lezár.** A régi `match()` nyers
substringet használt:

```python
if len(alias) >= 4 and alias in v:     # "a-10" in "a-100ll"  →  True
```

Emiatt a Beriev **A-100LL** AEW&C-tesztpad megsemmisülése
*„A-10 Thunderbolt II — Loss ×1"*-ként került az adatbázisba, és onnan a heti
jelentés ORBAT-táblájába.

A javítás két kényszer (`_boundary_hit()`):

1. **Bal határ** — a típusjel előtt nem állhat alfanumerikus karakter.
2. **Jobb határ a számjegyen** — ha az alias számjegyre végződik, utána **nem**
   állhat számjegy.

Ez zárja ki az `a-10` / `a-100ll` összecsúszást, de **megtartja** a valódi
variánsokat: `a-10c`, `f-15ex`, `f-16v`, `c-130j-30`, `ah-64e`. A katalógusban
további három valós ütközés van (`f-4`/`f-47`, `b-2`/`b-21`,
`mi-17`/`mi-171sh`) — mind helyesen oldódik fel.

A `match_type()` visszaad: `(type_id, variant_raw, match_kind)`. A variáns
**mindig** rögzül, akkor is, ha az index-találat pontos volt — különben az
ORBAT nem tudja, hogy nem szabad család-szintű számot mutatnia.

**Fuzzy illesztés csak az ingestion/review szakaszban történik. A riport
előállításakor soha — ott kizárólag a `type_id` foreign key használható.**

### 4.6 Programme-kötés — `ac_programmes.py`

`find_programme()` konzervatív: egyezés kell országra, katalógus-típusra,
**kompatibilis variánsra**, **kompatibilis haderőnemre** és **programfajtára**.
Ha nem biztos, új programot javasol és review-ba küldi — mert egy hibásan
**összevont** program ugyanolyan káros, mint egy hibásan **szétválasztott**.

---

## 5. A darabszám-logika (`quantity_scope`)

Ez a rész felel a legtöbb elkerült hibáért. A darabszámnak **hatóköre** van:

| hatókör | jelentés | mozgathatja a programméretet? |
|---|---|---|
| `programme` | a program teljes mérete | **igen** |
| `tranche` | részszállítás, tétel, prototípus | nem |
| `attrition` | veszteség, kivonás | nem |
| `non_airframe` | konténer, hajtómű, pénzösszeg | nem |
| `unknown` | nem eldönthető | nem |

**A döntés sorrendje:**

1. Veszteség mindent felülír.
2. **Mértékegység a szám után közvetlenül** — melyik egység-főnév áll
   *közelebb* a számhoz? `AIRFRAME_UNIT_RX` vs `NON_AIRFRAME_UNIT_RX`.
3. A szám **közvetlen környezete** (`_number_windows`, ±70 karakter).
4. Mondat-szint.
5. Ha mindkét jelzés jelen van és a szám környezete sem döntött →
   **konzervatívan `tranche`**.
6. Stádium alapján, ha a szöveg egyáltalán nem döntött.

### Valós esetek, amiket ez old meg

```
"Turkey's TAI Kaan second prototype (P1) began taxi trials"        qty=1
    → tranche. A KAAN programméret 148 marad, nem lesz 1.

"Germany's Bundestag authorized the purchase of 90 LITENING 5
 targeting pods"                                                   qty=90
    → non_airframe. A 90 célzókonténer, nem repülőgép.

"A USAF KC-135R was lost with six fatalities"                      qty=1
    → attrition. Öt ilyen eseményből nem lesz 1 gépes "program".

"152 F-35Cs on order as part of a Programme of Record for 140"     qty=152
    → programme. Az explicit programme-of-record nyelvezet felülírja
      a production stádiumot.

"Misawa received its first four permanent F-35s"                   qty=4
    → tranche.
```

### Két finom csapda, amit külön kezel

**„Tranche 5" típusjelölés, nem részszállítás.** A
*„20 Eurofighter Typhoon **Tranche 5** aircraft"* firm szerződést a korai
változat eldobta, mert a „tranche" szó részszállításnak látszott. Most a
`batch|tranche|lot` csak akkor számít mennyiségnek, ha határozó előzi meg és
**nem sorszám követi** (`\b(?:a|the|first|…)\s+(?:batch|tranche|lot)\b(?!\s*\d)`).

**Zárójeles kettős valutaérték.** A védelmi sajtóban általános
*„awarded a £4.6 billion ($6.1 billion) 18-month development contract"* forma
széttörte a szerződés-felismerést. A közbeszúrt rész karakterkészlete most
tartalmazza a zárójelet és a valutajeleket.

### Felülírás vs konfliktus

```python
if cur is None:                    → beállít
elif q == cur:                     → újramondás, nem ad hozzá
elif stronger or (equal and q > cur) or reduction:
                                   → felülír, a régi a superseded_quantities-be
elif q < cur:                       → "within_planned" MEGFIGYELÉS, nem konfliktus
else:                              → KONFLIKTUS (nagyobb szám gyengébb evidencián)
```

Evidencia-erősség: `contract (3) > announced (2) > reported (1) ≈ estimate (1)`.
Az `ESTIMATE_RX` fogja a sajtóspekulációt („local reports suggest", „may
acquire") — enélkül egy spekuláció felülírt egy hivatalos bejelentést.

**Egy plafon alatti kisebb szám nem ellentmondás.** Az ukrán „up to 150" alatt
a 20 és a 16 normális részhalmaz — korábban mindhárom „konfliktusként" ment
elemzői döntésre.

### Szerződés-evidencia (`contract_evidenced`)

Ez a kapu szünteti meg az üzbég kettős állapotot (az elemzői réteg
„negotiation, unconfirmed"-et írt, az ORBAT „Contract signed ×24"-et).

- `CONTRACT_EVIDENCE_RX` — aláírási/odaítélési nyelvezet, közbeszúrt értékkel
  és többes számmal (`contracts?`, `orders?`)
- `CONTRACT_NEGATED_RX` — „no contract has been signed", „yet to be signed",
  „expected to sign" → **nem** evidencia
- `NEGOTIATION_RX` — tárgyalás, megerősítetlen állítás

**`resolved_stage()`** — a legacy események `lifecycle_stage` oszlopa NULL (az
`add_capability_fields.sql` előtti extrakciók). Nyers olvasással szinte minden
esemény stádium nélkülinek látszott, és a programok életciklusa sosem lépett
előre. Mindenhol ezt a feloldót kell használni, nem a nyers mezőt.

---

## 6. Elemzői réteg — `ac_intel.py`

### 6.1 Fejlemények (`build_developments`)

Modellhívás `DEV_PROMPT`-tal. A bemenet eseményenként tartalmazza a **tartós
programállapotot** is — így a modell látja, hogy a program már rögzítve van, és
nem „veszi meg" újra minden héten.

Determinisztikus utófeldolgozás a modell válaszán:

- **Lineage felülírása.** A `count_lineages()` a forrásláncokból számol
  (`originating_evidence_id` → `article_id` → `event_id`). A modell értékét
  legfeljebb **lefelé** fogadjuk el. A W33-ban a modell 2 független láncot
  állított az iráni MQ-9/MQ-1C veszteséghez, miközben mindkét event **ugyanabból
  a cikkből** származott.
- **Confidence-plafon.** Egyetlen lánc → legfeljebb `moderate`.
- **Programme-kötés** és `programme_delta` (a baseline-mozgás, nulla is
  információ).
- **Evidencia-jelleg**: ha minden forrásesemény `new_confirmation`, a fejlemény
  „New confirmation this period" jelölést kap az eredeti év feltüntetésével.

### 6.2 Kettős horizont (`_enforce_effect_timing`)

Két **külön** mező:

| mező | alap |
|---|---|
| `effect_timing` | legkorábbi műveleti hatás — IOC, ennek hiányában első átadás |
| `full_capability_timing` | értelmes méretű képesség — FOC / meaningful scale |

Hónapban számol (`_months_until`), és a **pontosságot a szöveg dönti el**:
`mid-2028` → június, `Q3 2028` → szeptember, puszta `2028` → december
(konzervatív), pénzügyi év → +1 év március.

**Miért:** egyetlen `effect` fogalom próbálta lefedni mindkettőt. A VC-25B
(első átadás 2028 közepe, IOC 2028, használható 2029) így `>3 years` címkét
kapott, holott 2026 augusztusától 2028 közepe **22 hónap**. Most:
`earliest effect 1-3 years` + `meaningful scale >3 years`.

### 6.3 Timeline (`capability_timeline`)

**Egy sor = egy programme + egy milestone.**

`MILESTONE_LABELS` 15 fajtát ismer. Három halmaz:

```python
NOT_AN_ARRIVAL   = {schedule_slip, withdrawal_start, withdrawal_complete,
                    loss, contract_award, selection_decision}
AIRFRAME_ARRIVAL = {first_delivery, final_delivery, deliveries_complete,
                    ioc, foc, meaningful_scale, production_start}
SUPPORT_ARRIVAL  = {mro_standup, certification}
```

Két konkrét javítás:

- **A késés nem érkezés.** A W34 *„2029 US VC-25B delay (meaningful
  capability)"* sora hibás volt; most `schedule_slip`, `arrival_kind: none`.
- **Egy MRO-program nem veszi át a beszerzés gépátadási évét.** A W34
  *„2028 Poland AH-64E MRO deal (first delivery)"* sorában a 2028 a **2024-es
  beszerzési** program első átadása volt. Most a támogató program dátum nélkül
  `TBD`-ként jelenik meg (`allow_undated=True`), nem kölcsönvesz.

Egy rendes beszerzés **három külön sort** ad: first delivery, IOC, meaningful
scale.

### 6.4 ORBAT (`orbat_delta`)

Baseline kulcsa `(country, type, variant, service)` — a régi `(country, type)`
a `variant` mezőt egyszerűen eldobta.

**Ha az esemény variáns-szintű, de csak család-szintű baseline van, a szám
NEM jelenik meg** (`baseline_scope_match = "variant_without_baseline"`),
helyette explicit hatókör-magyarázat. Enélkül állt elő:

```
26 gépes USAF HH-60W esemény  →  "UH-60 Black Hawk — Active 2000"
50 gépes brit AH-64E flotta   →  "UK AH-64 Apache — Active 100"
```

Minden sor explicit heti olvasatot kap (`period_reading`), hogy az olvasó ne
adja össze a programme-of-record és a heti oszlopot.

`propagate_stage_corrections()` — az elemzői stádium-downgrade **visszaíródik
az eseményekre az ORBAT felépítése előtt**, és nullázza a baseline-deltát. Az
eredeti címke `lifecycle_stage_reported`-ben megmarad: a felderítői termék nem
töröl nyomot.

### 6.5 Week-over-week

A W33 „18 in-period events"-et írt, a W34 „22 (+0 WoW)"-t. Két egymást követő
hét ugyanazon metrikája **+4**, nem +0. Az ok: a W34 az előző hetet
**újraszámolta** a saját, későbbi adatállapotából.

Most a WoW a `ac_report_metrics`-ben **publikált** értékből számol, és ha az
újraszámolt érték eltér, a **drift kiíródik**:

```
Previous period: 18 published · 23 on recomputation.
Week-over-week is stated against the PUBLISHED figure.
```

Ha a metodika-verzió változik → `WoW: not comparable`. Ha nincs előző jelentés
→ „no prior published report", nem `+0`.

### 6.6 Analitikai QA

`run_self_checks()` jelez, `qa_language_gate()` átírat, `gate_key_judgements()`
visszatart. Két lista vezérli: `REWRITABLE` (átírható) és `KJ_BLOCKING`
(visszatartandó — az ítélet **szerkezete** hibás, nem a megfogalmazása).

Fontosabb ellenőrzések:

| ellenőrzés | mit fog meg |
|---|---|
| veszteség ≠ mechanizmus ≠ szándék | a W33 iráni MQ-9 ítélet: „demonstrated effective counter-MALE capability", miközben a saját Basis és a gap-lista ismeretlennek mondta a mechanizmust |
| exploitation lehetőség vs tény | a roncsbemutatás **lehetőséget** teremt, nem bizonyít megtörtént kiértékelést |
| egy eset ≠ csoport-trend | egy litván rendelésből „small Baltic NATO allies" |
| kvantifikálhatatlan „quantifiable gap" | Hawk T2: sem out-of-service dátum, sem throughput-adat |
| abszolút készlet-állítás | *„Poland fields no attack helicopters currently"* — **tévesen**; Lengyelország Mi-24-eket üzemeltet. A hiányzó katalógus-sort olvasta nullának. Csak explicit, hatókörben egyező, nullát mutató baseline-ra engedélyezett. |
| retorikus leértékelés | „token addition" → „limited-scale contribution" |
| szövetségi tagság | egy NATO-tagot nem lehet „NATO-adjacent"-nek nevezni |
| designation a forráson kívülről | a modell emlékezetéből hozott típusjel |
| lineage-infláció | több event egy cikkből |

`rebuild_bottom_line()` + `check_bottom_line_leak()` — ha egy ítéletet
visszatartunk, a nyitó bekezdés újraépül **kizárólag az átment tartalomból**,
majd szivárgás-ellenőrzést kap. **Ismert nyitott tétel:** a szivárgás-detektor
néha tüzel (`withheld judgement reappears in the bottom line`) — ez *jelzés*,
nem csendes hiba, de a gépi tartalék még nincs megírva.

### 6.7 Since last week + briefing

`since_last_week()` — programme-szintű diff az előző **publikált** jelentésből,
4–6 sor, plusz az előző heti watchok állapota
(`resolved | unchanged | escalated | dropped | new`).

`build_briefing()` — 4 slide-os nézet, **kizárólag QA-n átment tartalomból**,
hogy a visszatartó kapu ne legyen megkerülhető egy „összefoglaló" nézeten át:

1. This week in air power — bottom line + 3 legfontosabb változás
2. What actually changed — `NOW | 1–3 YEARS | >3 YEARS`, oszloponként max 2
3. Deep dive — mi történt / képesség-delta / miért számít / **mit nem tudunk**
4. Watch next — watchok + az előző hetiek állapota

---

## 7. Frontend

```
/                           dashboard
/countries, /countries/[id]
/aircraft, /aircraft/[id]
/weekly                     a legfrissebb jelentés
/weekly/[week]              archív jelentés
/weekly/[week]/brief        4 slide-os briefing  ("latest" kulcsszó is működik)
/admin/review               esemény-jóváhagyás
/api/admin/review           service-role route
```

Komponensek: `WeeklyReportView.tsx` (a teljes jelentés, visszafelé kompatibilis
v1/v2/v3 payloaddal), `BriefingView.tsx` (nyomtatásban slide-onként új lap),
`SystemHealth.tsx`, `ui.tsx`.

Adatréteg: `lib/db.ts`, Supabase REST anon kulccsal, szerveroldalon,
`revalidate: 120`.

---

## 8. Költség-instrumentáció — `usage_tracker.py`

A modell minden válaszban visszaadja a token-fogyasztást, és a projekt ezt
korábban **mindenhol eldobta**.

```python
client = usage.wrap(anthropic.Anthropic())    # egyetlen sor változik
...
db.finish_run(run, "success", n, details=usage.summary())
```

Átlátszó burkolat: a hívások, paraméterek és visszatérési értékek
változatlanok, ezért a **retry-kat is fogja** — azok is pénzbe kerülnek, és
pont azok maradnának ki kézi méréssel.

Négy token-fajtát **külön** tart: `input`, `output`, `cache_write`,
`cache_read`. Árak nincsenek a kódba drótozva — `config/model_prices.json`;
hiányzó ár esetén csak tokent mond, nem magabiztos nullát.

**Soha nem dob kivételt**: a mérés a futás megfigyelése, nem a része.

`source_waste_report.py` — forrásonként mutatja az irreleváns arányt és a
becsült elpazarolt költséget. Ez adta a `source_policy.json` beosztását.

---

## 9. Eszközök és tesztelés

### Offline hangolás — **ne az éles adatbázison iterálj**

```
export_for_review.py    egyszeri, csak-olvasó kimentés → data/events_export.json
replay_audit.py         a teljes programme-logika újrajátszása DB nélkül
    --suspect           csak a gyanús esetek
    --full              minden program
    <programme_id>      egy program döntésenként, indoklással
```

A `replay_audit.py` minden döntést kiír (hatókör, alap, baseline-delta), így
egy logikaváltozás hatása **másodpercek alatt** látszik az összes eseményen.

A `--suspect` lista azt mutatja, amit **embernek** kell eldöntenie. Jelenlegi
állapot: 2 tétel, mindkettő valódi elemzői kérdés (a lengyel Apache 94/96
forrás-ellentmondás; a B-21, amiről a cikkek nem közölnek darabszámot).

### Teszt-suite-ok

```
test_ac_match.py            entitás-illesztés regressziók + a teljes katalógus
                            önkonzisztenciája + számjegy-prefix ütközések
test_ac_programmes.py       programme-réteg, 15 alszakasz, mind valódi
                            cikkszövegekből
test_report_integration.py  végponti: ORBAT, timeline, horizontok, briefing
test_programme_write.py     az írási út VALÓDI PostgreSQL-en
source_policy.py            self-test (önállóan futtatható)
usage_tracker.py            self-test
validate_relevance_gate.py  a kapu mérése felcímkézett cikkeken
```

**`test_programme_write.py` külön említést érdemel.** Az írás három különböző
hibával bukott el egymás után, mindhárom éles futásban:

```
HTTP 400 (ismeretlen oszlop)  — a séma korábbi migráción állt
PGRST102 "All object keys must match"  — a batch sorai más kulcsokat vittek
23502 NOT NULL violation      — a kulcs-normalizálás explicit NULL-t küldött
                                oda, ahol addig a default érvényesült
```

A teszt felépíti a **teljes sémát az öt migrációs fájlból** egy igazi
PostgreSQL-ben, és a **produkciós sor-építővel**
(`reconcile_programmes.build_programme_rows`) beszúrja a programokat. A NOT
NULL oszlopokat **a migrációs fájlból olvassa vissza**, tehát egy jövőbeli új
NOT NULL oszlop sem maradhat le a kliens-oldali defaultokról.

### Karbantartó scriptek

```
reconcile_programmes.py --write --fix-types   a meglévő adat átkötése
fix_fleet_baseline.py [--write]               ac_fleets egyeztetés a regiszterrel
apply_source_policy.py --apply                a drop-források enabled=false
```

Mindkettő **alapértelmezésben dry run**, és JSON-riportot ír a `data/`-ba.

A `fix_fleet_baseline.py` három eltérés-típust jelez, és a `--write` **csak az
első kettőt** javítja:

1. on-order túllőtt (a felhalmozott duplikáció)
2. rossz oszlop (aktív állomány szállítás előtt)
3. hiányzó sor — **soha nem írja automatikusan**: a hiányzó baseline elemzői
   döntés, nem következtetés

Az első éles futása 9 sort javított: Poland AH-64 `286→96`, Turkey KAAN
`188→20`, Ukraine Gripen `116→16`, Turkey Eurofighter `40→20`, Poland F-35
`48→32`, Indonesia M-346 `24→12`, Colombia C-390 `4→2`, Spain NH90
`active 30→0, on_order→31`.

---

## 10. Ütemezés (GitHub Actions)

| workflow | ütemezés | mit csinál |
|---|---|---|
| `aircraft_sync.yml` | 04:30 UTC naponta | `collect_rss.py` → `process_articles.py` |
| `weekly_digest.yml` | hétfő 05:00 UTC | `generate_weekly_report.py` → `generate_digest.py` |
| `source_waste.yml` | kézi | forrásonkénti pazarlás-riport |
| `source_policy.yml` | kézi | `apply_source_policy.py --apply` + kapu-validáció |

Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY`
(+ opcionális `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).

**Figyelem:** a `pipeline_runs` tábla **közös** három projekttel. A
`script_name` CHECK megszorítás ezért **önjavító**: futásidőben a már meglévő
értékek ∪ az ismert nevek halmazából épül fel. Egy whitelist egy megosztott
naplótáblán szerkezeti csapda — kétszer törte el a migrációt.

---

## 11. Invariánsok — amit nem szabad megbontani

Ha a kódbázison dolgozol, ezek a szabályok nem stílus kérdései. Mindegyik
mögött egy megtörtént hiba áll.

1. **Egy újabb cikk nem új repülőgép.** A programállapot frissül, nem
   összegződik.
2. **Az `on_order_delta` alapértelmezésben 0.** Nem nulla csak akkor, ha van
   szerződés-evidencia **és** a darabszám hatóköre `programme` **és** a
   programfajta tart gépállományt.
3. **Programme nélküli esemény nem mozgathatja a baseline-t.** Ha nem tudjuk
   programhoz kötni, azt sem tudjuk, újramondás-e.
4. **Fuzzy illesztés csak ingestionkor.** A riport kizárólag `type_id`
   foreign key-ről dolgozhat. Névalapú visszakeresés a megjelenítéskor tilos.
5. **Család-szintű baseline nem rendelhető variáns-szintű eseményhez.**
   Inkább visszatartott szám, mint közelítés.
6. **A hiányzó adat nem nulla.** Sem az ORBAT-táblában (`n/d`), sem a
   narratívában („fields no attack helicopters").
7. **A veszteség nem beszerzés.** Külön programfajta, nincs kanonikus mérete.
8. **A szerződött és a tervezett darabszám két külön mérték.** Nem összegezhető
   és nem ellentmondás.
9. **A WoW a publikált előző értékből számol**, és a drift látható marad.
10. **A visszatartó kapu nem megkerülhető.** Sem a bottom line-on, sem a
    briefing nézeten keresztül.
11. **A bizonytalan eset átmegy a relevancia-kapun.** A hibás NEM drágább a
    hibás IGEN-nél.
12. **Ismeretlen forrás → `pass`.** A hallgatás nem kizárás.
13. **A `drop` nem törlés.** Minden auditálható és újrafeldolgozható marad.
14. **A mérés nem állíthat meg futást.** A `usage_tracker` sosem dob kivételt.
15. **A rendszer jelez, nem dönt.** Duplikátum-gyanú, darabszám-konfliktus,
    hiányzó baseline — mind elemzői döntés.

---

## 12. Ismert nyitott tételek

- **Bottom line szivárgás.** A visszatartott ítélet tartalma néha átszivárog a
  nyitó bekezdésbe. A detektor jelzi, de a determinisztikus tartalék (gépi
  bottom line kizárólag az átment ítéletekből) még nincs megírva.
- **`ac_fleets` lefedettség.** A séma támogatja a variáns/haderőnem szintet
  (`variant`, `service`, `baseline_scope`), de az adat nagyrészt még
  család-szintű — ezért az ORBAT sok helyen visszatartja a számot ahelyett,
  hogy valódi variáns-adatot mutatna.
- **Kéretlen programme-szaporodás.** 214 eseményből 127–135 program. Nem
  bizonyítottan hibás (sok egyedi ország-típus pár), de a horgony-év alapú
  kulcsolás elvileg szétvághat egy programot, ha az első evidencia éve
  eltolódik.
- **Elemzői review-sor.** 56 esemény nem oldódik fel katalógus-típusra, és
  review-ban vár. Ez szándékos (jobb, mint a csendben rossz FK), de a
  katalógus bővítése csökkentené.

---

## 13. Gyors tájékozódás egy új dolgozónak

```
ac_match.py        entitás-illesztés          ~200 sor
ac_programmes.py   programme-identitás és állapot   ~700 sor
ac_intel.py        elemzői réteg + QA         ~1700 sor
process_articles.py kinyerés + kapuk          ~700 sor
generate_weekly_report.py  orchestrátor       ~600 sor
```

A kód magyar nyelvű kommentárral dokumentált, és a kommentek **a hiba
anatómiáját** írják le, nem azt, hogy mit csinál a sor alatta. Ha egy
szabály feleslegesnek tűnik, keresd meg a hozzá tartozó kommentet — majdnem
biztosan egy konkrét, megtörtént jelentés-hibára hivatkozik.
