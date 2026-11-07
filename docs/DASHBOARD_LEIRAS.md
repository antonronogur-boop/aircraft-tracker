# Aircraft Tracker — a dashboard áttekintő és részletes leírása

> **Mire való ez a dokumentum.** Egy prezentációhoz készült: bárki, aki be
> akarja mutatni a rendszert — a felületet, a folyamatot és a hátteret —, innen
> minden választ megtalál. Az eleje gyors áttekintés (ebből lehet előadni), a
> többi a mélyebb kérdésekre felel. A fejlesztői, kód-szintű mélységet külön
> dokumentum tartalmazza (`docs/SYSTEM_SPEC.md`).
>
> Állapot: 2026-11-03 · Élő: https://aircraft-tracker-three.vercel.app/

---

## 0. Egy mondatban

> Egy önműködő felderítő rendszer, amely a nyílt forrású (OSINT) katonai
> repülős hírekből napról napra felépíti, **ki rendel, kap, modernizál, elad,
> von ki vagy veszít el** milyen repülőgépet — és ebből hetente egy rövid,
> döntéstámogató **légierő-fejlesztési jelentést** állít elő.

Nem hírolvasó. Nem adatbázis-böngésző. A kérdés, amire válaszol, nem az, hogy
*mi történt*, hanem hogy **mi változott a légi képességképben, mennyire
biztos, mikorra hat, és mit jelent**.

---

## 1. Áttekintés — mit lát a néző

A dashboard egy böngészőben futó, sötét témájú webfelület, öt menüponttal. A
tartalom három rétegre bomlik, az „elég egy pillantás" szinttől a „teljes
felderítői elemzés" szintig:

| réteg | hol | mire jó |
|---|---|---|
| **Operatív áttekintés** | Dashboard, Countries, Aircraft | „Mi mozog most? Melyik ország, melyik géptípus?" |
| **Felderítői termék** | Weekly report + Briefing | „Melyik 3–5 fejlemény számít, és miért?" |
| **Minőségbiztosítás** | Review (admin) | „Mit engedünk a nyilvános oldalakra?" |

A felső sávban mindig ott a navigáció (**Dashboard · Countries · Aircraft ·
Weekly report · Review**), alul pedig egy állandó figyelmeztetés:

> *OSINT-based tracker — data extracted automatically from public news, verify
> before use.*

Ez szándékos: a rendszer **gépi kivonat**, nem hitelesített hírszerzés. A
felület mindenhol megmutatja, mennyire bízhatunk egy adott számban — ez a
tervezés egyik vezérelve.

---

## 2. A felület, oldalról oldalra

### 2.1 Dashboard (kezdőlap)

Három blokk, fentről lefelé:

**(a) Rendszerállapot-sáv.** Egy vékony csík három zöld/sárga/piros ponttal:
`Collection` (gyűjtés), `AI processing` (feldolgozás), `Weekly report`. Minden
pont azt mutatja, mikor futott utoljára az adott komponens és hány elemet
dolgozott fel. A küszöbök be vannak építve: a napi komponenseknél 14 óra fölött
sárga, 36 óra fölött piros; a heti jelentésnél 8, illetve 15 nap. Ha valami
elakadt, a sáv kiírja: *„check GitHub → Actions if this persists."* Ez teszi a
rendszert **önellenőrzővé** — nem kell külön belépni sehová, hogy lássam, él-e.

**(b) Négy számláló-kártya:** *Events this week* (e heti események), *Active
countries* (hány ország mozgott), *Pending review* (jóváhagyásra vár), *Tracked
types* (követett géptípusok száma).

**(c) Két hasáb:**
- **Latest signals** — a 30 legfrissebb esemény kártyaként. Minden kártyán:
  esemény-típus színes címke (Order, Delivery, Upgrade, Export sale, Selection,
  Negotiation, Retirement, Incident), ország, géptípus (kattintható), darabszám,
  érték, dátum, egymondatos összefoglaló, és a **forráscikkre mutató link**.
  A még jóvá nem hagyott események is itt vannak, *„pending review"* jelzéssel —
  így egy új kivonat azonnal látszik, de látható is, hogy még nem ellenőrzött.
- **Most active countries** — a hét 8 legaktívabb országa, eseményszámmal,
  kattintható.

### 2.2 Countries (országlista) és országoldal

**A lista** régiók szerint csoportosít (Balkans, Middle East, …), minden
országnál a flotta-sorok és a jóváhagyott események száma.

**Az országoldal** két szekcióból áll:

1. **Fleet baseline** — táblázat: géptípus, változat, státusz (Active, On
   order, Option, Selected, In negotiation, Retiring, Retired), darabszám,
   dátum, és egy **Verification** oszlop. Ez utóbbi a felület egyik
   legfontosabb része:
   - Négy hitelesítési állapot, mindegyik külön színnel és magyarázattal:
     *verified* (megerősített), *corrected* (javított), *not verifiable* (nem
     ellenőrizhető), *record mixes two types* (a sor két típust kever).
   - Ha egy program teljes kerete ismert, az **külön** jelenik meg
     („programme total: 29") — mert *egy 29 gépes program nem 29 üzemelő gép*.
   - Ha a valós érték egy **tartomány** („kb. 160–165", „legalább 11"), akkor a
     felület a tartományt mutatja, a régi pontos számot pedig áthúzva alatta.
     A hamis pontosság itt rosszabb a bevallott bizonytalanságnál.
2. **Event timeline** — minden esemény, ahol az ország akár vevő, akár a másik
   fél (eladó). Ugyanazok a kártyák, mint a dashboardon.

### 2.3 Aircraft (katalógus) és géptípus-oldal

**A katalógus** kategóriánként rendezi a követett típusokat (Fighters,
Bombers, Attack, Helicopters, Transport, Tankers, Special mission / AEW&C,
Maritime patrol, Trainers, Large UAVs), eseményszámmal, gyártóval, és jelzi a
fejlesztés alatt állókat.

**A géptípus-oldal** három részből áll: **alapadatok** (megnevezés, kategória,
gyártó, származás, szerep, első repülés, gyártási státusz), **üzemeltetők**
listája (mely országok, mennyi, milyen státuszban), és a típus teljes
**eseménytörténete**.

### 2.4 Weekly report (a heti jelentés) — a rendszer csúcsterméke

Ez a legösszetettebb nézet, és ez az, amiért az egész rendszer létezik. A
`/weekly` a legfrissebbet mutatja, a `/weekly/<hét>` egy archivált hetit, és
minden jelentés kinyomtatható / PDF-be menthető. A jelentés szekciói felülről:

- **Bottom line** — 3–5 mondat arról, mi változott ténylegesen a képességképben.
  Mellette heti statisztikák, köztük a **hét-a-héthez** (WoW) mutató és annak
  alapja (lásd 5.4), plusz az érték **értéktípusonként** bontva (aláírt
  szerződés, IDIQ-plafon, DSCA-maximum — ezek nem adhatók össze).
- **Key judgements** — 3–5 kulcsítélet, mindegyiknél bizonyosság, időhorizont,
  a mögöttes evidencia, és egy *alternatív magyarázat*. Ami nem állja ki a
  minőségi kaput, az **visszatartva** jelenik meg, külön jelölve, nem
  ítéletként.
- **Since last week** — 4–6 soros programme-szintű diff az előző héthez képest,
  plusz az előző heti figyelőpontok állapota (megoldódott / változatlan /
  felerősödött / elejtett / új).
- **Capability developments** — a hét fejleményei, mindegyiknél a
  képesség-domén, az életciklus-stádium, a **kettős időhorizont** (legkorábbi
  műveleti hatás vs. értelmes méretű képesség), a forráslánc és egy
  „mit nem tudunk" sor.
- **Capability × maturity mátrix** — melyik képesség hol tart a *szándék →
  elkötelezés → szerződés → feltöltés → műveleti* skálán.
- **Capability transition / withdrawal** — a kivonások és veszteségek külön
  rétegben (nem ugyanaz a folyamat, mint a bevezetés).
- **ORBAT delta** — az érintett flották: mi van hadrendben, mi rendelésben, mit
  érint a heti esemény. Variáns- és haderőnem-biztos: egy variáns-szintű
  eseményhez nem rendel család-szintű számot.
- **Capability arrival timeline** — mikor válik a beszerzés valódi képességgé.
  Egy sor = egy program + egy mérföldkő; a késés nem érkezés.
- **Priority intelligence watch** — legfeljebb öt figyelőpont, hatás szerint
  rangsorolva.
- **Automated analytical QA** — ahol egy ellenőrzés jelez, ott a kapcsolódó
  megfogalmazást gyengébbnek kell olvasni.
- **Programme register review** — duplikátum-gyanúk és darabszám-konfliktusok
  **elemzői döntésre** (a rendszer jelez, nem dönt).
- **Evidence annex** — a nyers esemény-folyam, forráslinkekkel. „A fenti
  elemzés a döntési termék; ez az adatréteg."

**A briefing nézet** (`/weekly/<hét>/brief`, vagy `/weekly/latest/brief`):
ugyanabból, de **4 diára** sűrítve egy 5–8 perces szóbeli előadáshoz:
(1) Ez történt a héten, (2) Mi változott *most / 1–3 év / >3 év* bontásban,
(3) Mélyfúrás a hét fő témájáról, (4) Mit figyeljünk. Nyomtatásban minden dia
külön lapra kerül. **Fontos elv:** a briefing kizárólag a minőségi kapun átment
tartalomból épül — a visszatartó kapu nem kerülhető meg egy „összefoglalón" át.

### 2.5 Review (admin jóváhagyó sor)

Itt dől el, mi kerül a nyilvános oldalakra. A felület kilistázza a
jóváhagyásra váró, gépi úton kinyert eseményeket. Minden soron: esemény-típus,
ország + típus (vagy „unresolved", ha a gép nem tudta biztosan beazonosítani),
darabszám, a modell **bizonyossági** értéke, és az összefoglaló.

Műveletek:
- **✓** jóváhagy (megjelenik a nyilvános oldalakon),
- **✗** elutasít (rejtve marad),
- **✓+fleet** jóváhagy **és** rávezeti a flotta-baseline-ra (csak
  order / delivery / retirement / incident típusnál, ahol van ország, típus és
  darabszám). A gomb buborékja megmondja, mit tesz: rendelés → `on_order`,
  szállítás → `active` fel / `on_order` le, kivonás vagy veszteség → `active` le.
- Tömeges műveletek: *Select all*, *Select resolved only* (csak a biztosan
  beazonosítottak), *Clear*, majd *Approve / Reject selected*.

A felületi jogosultság **kétszintű**: az olvasás nyilvános (anon kulcs), de a
tényleges módosítás egy szerveroldali végponton (`/api/admin/review`) megy át,
amely a **service-role** kulcsot használja — az soha nem kerül a böngészőbe.

---

## 3. A folyamat — a hírtől a képernyőig

### 3.1 A napi ciklus (automatikus, hajnali 04:30 UTC)

```
RSS-források ──► előszűrés ──► forrás-kapu ──► olcsó kapu ──► AI-kinyerés ──► adatbázis
  (10 lap)      kulcsszó     (pass/gate/drop)   (Haiku)        (Sonnet)       (Supabase)
```

1. **Gyűjtés** — tíz katonai repülős RSS-forrásból. Már itt előszűrés van: csak
   az a cikk kerül be, ami katalógusbeli géptípust vagy beszerzési kulcsszót
   említ.
2. **Forrás-szintű kapu** — forrásonként beállítható, mennyi erőfeszítést ér meg
   egy lap. Három állapot: `pass` (teljes feldolgozás, ez az alap), `haiku_gate`
   (előbb egy olcsó modell dönt cím + összefoglaló alapján), `drop` (nincs
   modellhívás). **Fontos:** ismeretlen forrás mindig `pass` — a hallgatás nem
   kizárás —, és a `drop` **nem törlés**: a cikk auditálható marad és a politika
   módosításával újrafeldolgozható.
3. **Olcsó relevancia-kapu** — a kapuzott forrásoknál egy olcsó modell (Haiku)
   dönt a drága kinyerés előtt. Aszimmetrikus: a *tévesen kizárt* cikk véglegesen
   kiesne, ezért **minden bizonytalan eset átmegy** („If unsure, YES").
4. **AI-kinyerés** — a megmaradt cikkekből egy nagyobb modell (Sonnet)
   **strukturált eseményeket** von ki: típus, ország, géptípus, darabszám,
   érték, dátum, életciklus-stádium, bizonyosság, forráslánc. Minden esemény
   `pending` (jóváhagyásra váró) állapottal születik.
5. **Beírás** — az események a Supabase adatbázisba kerülnek, és azonnal
   megjelennek a dashboard „Latest signals" sávjában (pending jelzéssel).

### 3.2 Az emberi lépés (a Review-sor)

Az elemző (Anton) átnézi a `pending` eseményeket, és jóváhagyja / elutasítja /
rávezeti a flottára. Csak a **jóváhagyott** események jelennek meg az
országoldalak és géptípus-oldalak hivatalos nézetein.

### 3.3 A heti ciklus (automatikus, hétfő 05:00 UTC)

A heti jelentés-generátor a programme-réteg logikájával felépíti a felderítői
terméket (kulcsítéletek, ORBAT, timeline, horizontok, briefing), lefuttatja az
automatikus minőségi QA-t, és archiválja. Opcionálisan Telegram-digestet is küld.

---

## 4. A háttér — mi hajtja

### 4.1 Technológiai lánc

```
RSS ──► Claude-kinyerés ──► Supabase (PostgreSQL) ──► Next.js 14 + Tailwind (Vercel)
```

- **Adatbázis:** Supabase (PostgreSQL), `ac_` prefixű táblákkal. A projekt
  **osztozik** egy Supabase-példányon két testvérprojekttel (Drone/UAV Monitor,
  Balkan Monitor); az elkülönítés a tábla-prefix.
- **Frontend:** Next.js 14 (App Router) + Tailwind, szerveroldali
  adatlekéréssel, 120 másodperces gyorsítótárral. A nyilvános oldalak az **anon**
  kulcsot használják (csak olvasás), az írás a service-role kulccsal, kizárólag
  szerveroldalon.
- **Automatizálás:** GitHub Actions — napi gyűjtés+feldolgozás, heti jelentés.
- **Hosting:** Vercel, minden git-push után automatikus deploy.

### 4.2 A központi fogalmi elválasztás (ezen áll az egész)

```
EVIDENCE  (mit állít egy forrás)
   │
   ▼
EVENT     (mi történt / mi jelent meg a héten)
   │
   ▼
PROGRAMME (a tartós valóság: a program állapota)
```

A jelentés **ebben az irányban** épül, és **soha** nem így:
`cikk → darabszám → ORBAT += darabszám`. Ennek az egy szabálynak a hiánya
okozta a rendszer legsúlyosabb korábbi hibáját: ugyanarról a lengyel AH-64E
beszerzésről szóló minden újabb cikk új rendelésnek látszott, és az „on order"
190 → 286 → tovább kúszott, miközben egyetlen 96 gépes program létezik. A
javítás nem okosabb összegzés, hanem hogy **nem összegzünk**: a rendelési
állomány a program *szerződött* darabszámából származik, nem az események
összegéből.

### 4.3 Miért bízhatunk benne — a beépített fegyelem

A rendszer minden ponton **a bizonyosságot is kezeli**, nem csak az adatot:

- **Entitás-fegyelem.** A géptípus-azonosítás határ-tudatos: az „A-100LL" nem
  csúszik össze az „A-10"-zel, de az „A-10C" helyesen a családjához kötődik. A
  riport kizárólag biztos azonosítóról dolgozik, névalapú találgatás nélkül.
- **Darabszám-hatókör.** Egy lezuhant gép, egy prototípus gurulási próbája vagy
  „90 célzókonténer" nem programméret. A rendszer megkülönbözteti a *program /
  részszállítás / veszteség / nem-gép* hatóköröket.
- **Szerződött ≠ tervezett.** Egy programnak két darabszáma van (pl. 20
  szerződött KAAN egy 148 gépes tervből) — ezek nem ellentmondásosak, és nincs
  összeadva.
- **Forráslánc.** Három szaklap ugyanarról a gyártói közleményről **egy**
  független forrás — a bizonyosság ehhez van kötve, nem a cikkek számához.
- **Kettős időhorizont.** A legkorábbi műveleti hatás (IOC) és az értelmes
  méretű képesség (FOC) külön — egy 2028-as IOC 1–3 éves hatás, akkor is, ha a
  teljes képesség 2030.
- **Minőségi kapu.** Ami beszerzési adatból harci képességet állít, vagy amit a
  rendszer saját hiánylistája ismeretlennek mond, azt a kapu **visszatartja**.
- **Hiányzó adat ≠ nulla.** Sem a táblában (`n/d`), sem a narratívában.
- **A rendszer jelez, nem dönt.** Duplikátum-gyanú, konfliktus, hiányzó
  baseline — mind elemzői döntésre kerül.

A teljes szabálylista és az egyes szabályok mögötti konkrét, megtörtént hibák a
`docs/SYSTEM_SPEC.md` 11. szakaszában (invariánsok) szerepelnek.

---

## 5. Gyakori kérdések (a prezentációhoz)

**Honnan jönnek az adatok?** Kizárólag nyilvános hírforrásokból (OSINT) — tíz
katonai repülős RSS-lapból. Nincs zárt vagy minősített forrás.

**Mennyire friss?** A gyűjtés és feldolgozás naponta fut (04:30 UTC), a heti
jelentés hétfőnként. A dashboard „System" sávja mindig megmutatja, mikor futott
utoljára minden komponens.

**Mennyire megbízható?** A rendszer gépi kivonat, és ezt a felület mindenhol
kimondja. Három védelem van beépítve: (1) emberi jóváhagyás a nyilvános oldalak
előtt, (2) külső hitelesítési réteg a flotta-számokon (verified / corrected /
not verifiable / mixes two types), (3) automatikus analitikai QA a heti
jelentésben. Ahol a rendszer nem biztos, azt **megmutatja**, nem elrejti.

**Mi automatikus és mi kézi?** Automatikus: a gyűjtés, a szűrés, a kinyerés, a
heti jelentés és a saját állapotfigyelés. Kézi: a jóváhagyó sor (mi kerül
nyilvánosra), és az elemzői döntések, amiket a rendszer jelez (duplikátum,
konfliktus, hiányzó baseline).

**Mennyibe kerül?** A fő költség az AI-kinyerés (minden releváns cikk egy
modellhívás). Ezt két dolog fogja vissza: a forrás-kapu (a pazarló lapokat
olcsó modell szűri vagy teljesen kihagyja) és a rendszerprompt-gyorsítótár.
Minden futás méri a saját token-fogyasztását, és külön riport mutatja,
forrásonként mennyit pazarolunk.

**Ki tudja rontani?** Igen — gépi kivonatról van szó. Egy modell félreolvashat
egy számot vagy egy típust. Ezért van a jóváhagyó sor, a hitelesítési réteg és
a QA. A felület alapelve, hogy a bizonytalanságot **láthatóvá** teszi, nem
eltünteti.

**Ki tartja karban?** Egyetlen elemző/adminisztrátor (Anton), külső AI
kódsegéddel a fejlesztéshez. A rendszer úgy épült, hogy egy ember
üzemeltethesse: önműködő, önellenőrző, és a kézi munkát a jóváhagyó sorra
koncentrálja.

**Terjeszthető-e más területre?** Igen — ez az architektúra egy a három
testvérprojekt közül (drón/UAV, Balkán), közös adatbázison, ugyanazzal a
mintával (RSS → AI-kinyerés → ellenőrzés → jelentés).

---

## 6. Két őszinte korlát / árnyalat

Egy prezentációban ezeket érdemes elöl tudni, mert egy felkészült kérdező
rájuk fog kérdezni.

1. **Kétféle flotta-nézet.** Az operatív országoldalak a nyers
   `ac_fleets` táblát mutatják (a hitelesítési réteggel), míg a heti jelentés
   ORBAT-ja a fejlettebb programme-réteggel dolgozik (szerződött vs. tervezett,
   variáns-biztos). A kettő átfed, de nem azonos. A kézi *✓+fleet* gomb még az
   egyszerű additív logikát használja (`on_order += qty`), amit egy külön
   egyeztető lépés (`fix_fleet_baseline.py`) időnként visszaigazít a
   programme-regiszterhez. Ez egy ismert, kezelt varrat — nem rejtett hiba.

2. **A felület a nyers esemény-réteget mutatja, a mélység a jelentésben van.**
   A dashboard és az országoldalak gyorsak és egyszerűek; a programme-réteg
   teljes finomsága (kettős darabszám, forráslánc, kettős horizont) a **heti
   jelentésben** jelenik meg. Ha valaki a „miért éppen ennyi gép?" kérdést
   teszi fel, a válasz a Weekly report, nem a nyers flotta-tábla.

---

## 7. Mit mondjunk egy percben

> „Ez egy önműködő OSINT-rendszer, amely nyilvános hírekből napról napra
> követi a világ katonai repülőgép-flottáinak változásait, és hetente egy rövid
> felderítői jelentést készít arról, melyik fejlemény változtatja meg a légi
> képességképet, mennyire biztosan és mikorra. A felületen látszik minden
> esemény a forrásáig visszavezetve, minden ország flottája a bevallott
> bizonytalansággal együtt, és egy heti jelentés, amiből 5 perc alatt lehet
> szóban prezentálni. A rendszer önellenőrző, egy ember üzemelteti, és mindenhol
> megmutatja, mennyire bízhatunk egy adott számban — mert gépi kivonat, nem
> hitelesített hírszerzés."
