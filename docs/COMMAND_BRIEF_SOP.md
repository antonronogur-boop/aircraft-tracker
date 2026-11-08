# COMMAND AIR INTELLIGENCE BRIEF — SOP

**Standard Operating Procedure a heti Command Air Intelligence Brief elkészítéséhez, szerkesztéséhez, jóváhagyásához és kiadásához.**
Template: **v1.1** (`config/command_brief_presentation.json`) · Rövid változat: [`Command_Brief_Quick_Guide.md`](Command_Brief_Quick_Guide.md)

> Mérce: egy megfelelően képzett légierős / felderítő elemző a rendszerrel vagy a Word-template-tel — a PO jelenléte nélkül — ugyanabban a szakmai és vizuális szabványban elő tudja állítani a heti briefet.

---

## 1. A három réteg — mit szabad és mit nem

| Réteg | Mi ez | Ki változtatja | Hol |
|---|---|---|---|
| **A. Analytical truth** | jóváhagyott cikkek, események, evidence, capability delta, értékelés, confidence, significance, source lineage, watch indicators | csak az elemzői workflow (cikk-jóváhagyás, elemzés, restatement) | adatbázis, részletes heti jelentés |
| **B. Command Brief Draft** | a generált brief + az elemző által szerkesztett **publikációs szöveg** | elemző a webes szerkesztőben | `Weekly → Command Brief → Edit` |
| **C. Released product** | jóváhagyott draftból fagyasztott, verziózott kiadás (R-1, R-2 …) | csak *Release* gomb, APPROVED draftból | web nézet, kanonikus PDF, Word munkapéldány |

**A szerkesztő soha nem írja vissza az A réteget.** Ha egy értékelés (assessment, confidence, significance, forrás) hibás, azt nem a briefben javítod, hanem az elemzői workflow-ban (cikk/esemény felülvizsgálat → `--restate` vagy `backfill_command_brief.py --write --reason "..."`). A restatement után a szerkesztett mezők *„generated text changed”* jelzést kapnak, a korábbi jóváhagyás érvényét veszti.

---

## 2. Normál heti folyamat (web)

```
napi gyűjtés → AI triage → HUMAN cikk-jóváhagyás → elemzés → szerdai heti freeze
→ AI Command Brief Draft (GENERATED) → elemző: Edit → előnézet → Submit for approval
→ jóváhagyó: Approve → Release → kanonikus PDF / Word munkapéldány → terjesztés
```

1. Szerda reggel (05:15 UTC) a rendszer legenerálja a heti jelentést és a briefet: státusz **GENERATED**. Minden oldalon piros *WORKING COPY — NOT APPROVED* jelölés.
2. Nyisd meg: `Weekly → Command Brief → Edit (analyst)` (`/weekly/<hét>/command/edit`). Írd be a neved (*Analyst* mező) — minden változás a neveddel, időbélyeggel, mezőnként előtte/utána értékkel naplózódik.
3. Oldalanként (Page 1–5 fül) nézd át a blokkokat. Jobb oldalt élő előnézet — **pontosan ezt nyomtatja a PDF**.
4. Szerkeszthető (publication copy): a szövegmezők. **Nem szerkeszthető** (zárt, szürke címke): forrás (S-xx), lineage, publikációs dátum, HU relevance, SIG, CONF, horizon, collection status, a forrásjegyzék.
5. Lehetőségek: átírás, rövidítés, ↑/↓ átrendezés, *Hide* (elrejtés a kiadásból), *revert to generated*.
6. **Save changes** → státusz **EDITING**, új revízió. Ha egy oldal nem fér ki, a fejlécben *„Page N: text does not fit”* figyelmeztetés jelenik meg — rövidíts.
7. **Submit for approval** → **READY_FOR_APPROVAL**.
8. A jóváhagyó (lehetőleg másik személy) a saját nevével: **Approve** → **APPROVED**. Approve után bármilyen tartalmi szerkesztés visszaviszi EDITING-be (a jóváhagyás érvényét veszti).
9. **Release** → **RELEASED R-n**: verziózott, hash-sel rögzített pillanatkép (template-, módszertan- és HU-modell-verzióval). A nyilvános nézet ettől kezdve ezt mutatja.
10. A Command Brief oldalon **Download PDF** (nyomtatás → *Mentés PDF-ként*, A4 fekvő): ez a **kanonikus termék** — 5 oldal. Word: **Download Word (.docx)** — szerkeszthető munkapéldány.

Normál esetben ez néhány perces átnézés, nem kézi riportépítés.

### Státuszok

| Státusz | Jelentés | Kanonikus PDF? | Word export? |
|---|---|---|---|
| GENERATED | AI-előállítás, még senki nem nézte | nem (WORKING COPY) | igen, munkapéldány |
| EDITING | szerkesztés alatt | nem | igen |
| READY_FOR_APPROVAL | jóváhagyásra vár | nem | igen |
| APPROVED | jóváhagyva | **igen** | igen |
| RELEASED | kiadva (R-n), verziózott | **igen** | igen |

---

## 3. Tartalmi szabályok (minden csatornán ugyanaz)

| Elem | Szabály |
|---|---|
| **Primary KJ** | **max. 3**. Page 1-en elsődlegesen **HIGH/MEDIUM** Hungary relevance; LOW/MINIMAL csak kivételként (stratégiai súly). Elsődleges KJ-nek közvetlen forrása kell. |
| **What changed** | max. 1–2 mondat (≈240 karakter). Tény, nem értékelés. |
| **Assessment** | max. 2 mondat (≈260 karakter). Mit jelent — óvatos nyelvezet, nincs „trend” bizonyíték nélkül. |
| **Why Hungary should care** | max. 1–2 mondat (≈230 karakter). Konkrét kapcsolat Magyarországhoz / MH-hoz / NATO KKE légtérhez. |
| **Next observable** | **1 konkrét, ellenőrizhető indikátor** (≈170 karakter). |
| **What would make this wrong** | 1 mondat: mi cáfolná az értékelést. |
| **Sources** | **minden judgementnél kötelező** (S-xx). Hivatalos (Tier 1) forrás elöl. Kontextus-forrás („Context only — not evidence”) **soha nem bizonyíték**, nem számít lineage-nek. |
| **Collection gap** | gyűjtési hiány ≠ inaktivitás. Így írd: „absence of reporting is not evidence of inactivity”. |
| **Confidence** | **ne keverd a significance-szel**: a significance azt mondja, mennyire számít; a confidence azt, mennyire vagyunk biztosak. |
| **Page 5** | evidence-lineage register: egy sor = egy független lánc (hivatalos forrás + megerősítők). A teljes publikáció-lista: *Source detail* nézet és Word. |
| **Published** | a cikk saját publikációs dátuma — **soha** nem az esemény-, szerződés- vagy mérföldkő-dátum. |
| **Lineage** | ugyanazt a közleményt átvevő cikkek = **egy** lineage; állami (state-controlled) források = egy, mindig attribuált lineage. |
| **Szöveg** | egész mondatok; **nincs „…”**; nincs ki nem mondott rövidítés. |

A pontos hosszkorlátok a template-ben vannak (`config/command_brief_presentation.json`, `max_chars`/`max_sentences`); a szerkesztő számlálója sárga a célhossz felett, a rendszer a célhossz 1,6-szorosa felett nem ment.

---

## 4. Manuális / fallback folyamat (ha a webes rendszer nem elérhető)

1. Nyisd meg a **`templates/Command_Air_Intelligence_Brief.dotx`** template-et (Word: dupla kattintás → új dokumentum a template-ből; LibreOffice: *Fájl → Új → Sablonokból* vagy megnyitás). A template a webes felületről is letölthető: `/api/command-brief/template`.
2. Töltsd ki a mezőket: kattints a szürke helyőrzőre (pl. `[Assessment — 1–2 sentences, max 260 characters]`) és gépelj. Minden mező egy stabil címkéjű Word *content control* (pl. `CB_KJ1_ASSESSMENT`) — ne töröld a vezérlőt, csak a tartalmát írd át. A fix szöveg (címsorok, címkék, jelmagyarázat) zárolt.
3. Másold be a heti adatokat a részletes heti jelentésből (`/weekly/<hét>`) vagy az utolsó Word-exportból. Üresen maradó helyet (pl. 3. KJ, ha csak 2 van) törölj ki a tartalommal együtt.
4. Térképek: jobb klikk a térkép-helyőrzőn → *Kép módosítása* — a webes Command Brief oldalról mentett kép, vagy az előző heti Word-export térképe.
5. **Ellenőrizd a forrásokat**: minden judgementnél S-xx; a forrásjegyzékben a cím az eredeti nyelven, hiperhivatkozással (*Beszúrás → Hivatkozás*) az eredeti cikkre; a „Published” a cikk publikációs dátuma.
6. Töltsd ki a metaadat-táblát: hét, ablak, módszertan- és HU-modell-verzió, template-verzió (v1.0), státusz, jóváhagyó.
7. *Mentés másként* `.docx` (`Command_Brief_<hét>_MANUAL.docx`).
8. Export PDF (*Fájl → Exportálás → PDF*, A4 fekvő).
9. Jóváhagyás után nyomtasd / terjeszd. Amint a rendszer újra elérhető, a kiadott tartalmat vidd át a webes szerkesztőbe (ugyanazok a mezők), hogy a kiadás auditálható legyen.

> A Word **munkapéldány** — a szervezet kanonikus terméke a rendszerben kiadott (RELEASED) PDF. A manuális fallback PDF ideiglenes; a rendszer visszaállása után rögzíteni kell.

---

## 5. Nyomtatás

- A4 fekvő, normál irodai nyomtató, duplex is (rövid él mentén).
- Szürkeárnyalatban is olvasható: a szín soha nem hordoz egyedül jelentést — mindig van szöveges címke (**HU HIGH**, **SIG 4/5**, **GAP**, **WORKING COPY**).
- A kanonikus PDF pontosan **5 oldal**: 4 vezetői oldal + Sources & Legend. Ha 6 lenne, a szerkesztő túlcsordulást jelez — rövidíts.

---

## 6. Verziók

- **Template version** (`template_version`, jelenleg 1.0): a design / szerkezet verziója. Design-változás → verzióemelés; a régi template és schema a `templates/` mappában marad (`Command_Air_Intelligence_Brief_v1.0.dotx`, `command_brief_presentation_v1.0.json`), így régi riport a saját template-verziójával renderelhető.
- **Methodology version** és **HU model version**: az elemzői módszertan; a brief metaadataiban és minden kiadásban rögzítve.
- Minden kiadás (R-n) tartalmazza: draft-revízió, kiadó, jóváhagyó, időpontok, template/módszertan/HU-modell verzió, SHA-256 tartalom-hash.

---

## 7. Hibaelhárítás

| Jelenség | Teendő |
|---|---|
| *„draft changed since it was loaded — reload”* | valaki más közben mentett: frissítsd az oldalt, a saját módosításaidat vidd fel újra. |
| *„… is controlled analytical metadata”* | ezt a mezőt nem a briefben kell javítani → elemzői workflow. |
| *„generated text changed”* jelzés | restatement történt: nézd át a szerkesztett mezőt az új generált szöveg alapján, majd újra Submit / Approve. |
| *„Page N: text does not fit”* | rövidíts az adott oldalon (vagy rejts el egy alacsonyabb prioritású tételt). |
| Approve gomb inaktív | előbb ments, vagy kezeld a „generated text changed” mezőket. |
