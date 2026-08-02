# Repülőgép-flotta export – részletes ellenőrzési jelentés

**Ellenőrzés időpontja:** 2026-08-01

## Eredmény

- Ellenőrzött sorok: **52**
- MEGERŐSÍTVE: **18**
- HELYESBÍTVE: **25**
- NEM ELLENŐRIZHETŐ: **8**
- TÖRLENDŐ: **1**

## Fontos értelmezési szabály

Az `ellenorzott_active` és a `firm_on_order` mezőt nem szabad automatikusan összeadni aktuális flottaként. A `programkeret_vagy_korrigalt_osszes` csak programnézet, és több sornál a megrendelés kivonandó gépeket pótol.

## Kiemelt forrásellentmondás

Az Egyesült Államok KC-46 sorában a Boeing 2025. novemberi közlése 183 globálisan szerződött vagy szolgálatban lévő gépet, a Reuters 2026. júniusi jelentése pedig 188 USAF által megrendelt gépet közöl. A fájl ezt 183–188-as tartományként, `NEM ELLENŐRIZHETŐ` minősítéssel őrzi meg; az ellentmondást nem simítja el.

## Az adatkészlet leggyengébb pontjai

1. Az export alapvető szerkezeti gyengesége, hogy az aktív és a megrendelt mennyiséget egy „összesen” mezőben összeadja; ez programméretet mutat, nem aktuális flottát.
2. A leggyakoribb hiba az engedélyezett vagy politikailag bejelentett mennyiség firm szerződésként történő kezelése. Ez különösen az F-35-, F-16- és helikopterprogramoknál jelentkezik.
3. Több sorban modernizációs programot számoltak új repülőgépként. A legszembetűnőbb példa Marokkó F-16-flottája, ahol a meglévő gépek F-16V korszerűsítése nem növeli a fizikai darabszámot.
4. A pótló beszerzések összeadása a kivonandó flottával szintén torzít: Egyiptom és az Egyesült Királyság Chinook-programja, illetve az olasz és német Eurofighter-beszerzések ilyenek.
5. A változatok összevonása több helyen elemzési kárt okoz: Tejas Mk1/Mk1A, Rafale/Rafale M, Gripen C/D/E/F, F-35A/B, FA-50GF/PL, valamint MQ-9A Reaper/Protector.
6. Az „active” sok forrásban leltári vagy átadott állományt jelent, nem hadrafogható mennyiséget. A tárolt, karbantartás alatt álló és külföldi kiképzési gépek külön jelölése nélkül hamis pontosság keletkezik.
7. A leggyengébb konkrét sorok azok, ahol a hivatalos közlés nem tartalmaz darabszámot vagy gyorsan változik az átadás: Azerbajdzsán JF-17, Dánia F-35, Franciaország Rafale, Olaszország F-35, Lengyelország AW149 és az Egyesült Királyság következő F-35-tétele.
8. A gyors ütemben átadott programoknál a kötelező „érvényes dátum” hiánya néhány hónap alatt elavulttá teszi az adatot. Ausztrália F-35, Magyarország Gripen, Németország P-8 és Izrael F-35 jól mutatja ezt.
9. A forrásmezőt legalább forrásnév, publikációs dátum, URL és az állítás pontos jelentése szerint kell tárolni. Egy általános flottajegyzék önmagában nem elegendő egy gyorsan változó szállítási státuszhoz.

## Javasolt adatmodell-módosítások

- `active_delivered`, `active_in_country`, `operational`, `stored` és `training_abroad` külön mezők vagy státuszok.
- `firm_order`, `option`, `approved_not_contracted`, `planned` és `cancelled` külön beszerzési állapotok.
- Változat, haderőnem és feladatkör szerinti külön sorok.
- Minden darabszámhoz kötelező `valid_as_of`, forrásnév, URL és forrásmondat.
- Pótló beszerzésnél `replaces_type` / `replaces_quantity` mező, hogy ne lehessen nettó növekedésként összeadni.

## Visszatöltési megjegyzés

Az eredeti export nem tartalmazott `orszag_kod`, `tipus_kod`, `valtozat` vagy saját rekordazonosítót. Ezért a javított fájl `sor_id` mezővel őrzi az eredeti sorrendet. A tényleges adatbázisba történő visszatöltés előtt ezt a saját törzsadat-azonosítókkal kell összekapcsolni.
