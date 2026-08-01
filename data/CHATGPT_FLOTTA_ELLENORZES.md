# Feladat egy külső ellenőrzőnek (ChatGPT): repülőgép-flotta adatok hitelesítése

*Másold be ezt a szöveget a CSV-vel együtt. A CSV-t az `export_fleet_review.sql`
1. lekérdezése adja.*

---

## A feladat

Kapsz egy táblázatot arról, hogy egyes országok milyen katonai repülőgépeket
üzemeltetnek vagy üzemeltettek korábban. Az adat gépi kinyerésből és
kézi feltöltésből származik, **nincs hitelesítve**. A feladatod nem az, hogy
kiegészítsd, hanem hogy **megmondd, melyik sorban lehet megbízni és melyikben nem**.

## A legfontosabb szabály

**A birtokolt és a megrendelt állomány nem ugyanaz, és soha nem adható össze.**

A kapott táblázat szándékosan csak három állapotot tartalmaz:

| `allapot` | jelentése |
|---|---|
| `uzemel` | jelenleg repül, hadrendben van |
| `kivonas alatt` | még üzemel, de kivonás alatt áll |
| `korabban hasznalt` | már nem üzemel |

Ha egy sornál azt látod, hogy a darabszám valójában **leszállítás alatt álló
vagy megrendelt** gépeket is tartalmaz, azt külön jelezd — ez a leggyakoribb
hiba nyílt forrású flotta-összesítésekben.

## Amit kérek

Soronként add meg:

1. **Ítélet**: `MEGERŐSÍTVE` / `HELYESBÍTVE` / `NEM ELLENŐRIZHETŐ` / `TÖRLENDŐ`
2. **Helyes darabszám**, ha eltér — és hogy ez **mikorra** vonatkozik (dátum)
3. **Forrás** — konkrét, megnevezett forrás (pl. IISS Military Balance kiadási
   évvel, WDMMA, Flight International World Air Forces, hivatalos honvédelmi
   közlemény). Ne írj „általános ismeret" jellegű indoklást.
4. **Megbízhatóság**: `magas` / `közepes` / `alacsony`
5. **Megjegyzés**, ha a helyzet ennél árnyaltabb (pl. tárolt gépek, csak
   kiképzésre használt példányok, egy részük repülésképtelen)

## Amit kifejezetten NE csinálj

- **Ne találj ki számot.** Ha nem tudod ellenőrizni, `NEM ELLENŐRIZHETŐ` a
  helyes válasz. Egy bizonytalan sor, ami annak van jelölve, használható;
  egy magabiztos téves szám kárt okoz.
- **Ne pontosítsd túl.** Ha a nyílt források „kb. 30–40 gép"-et mondanak, ne
  írj 34-et. Add meg a tartományt.
- **Ne egészítsd ki a listát** olyan típusokkal, amik nincsenek benne. Az most
  külön kérdés; itt a meglévő sorok hitelesítése a feladat.
- **Ne vond össze a változatokat.** Az F-16C/D Block 52 és az F-16 Block 70
  külön sor, még ha mindkettő „F-16" is — a képességkülönbség lényeges.

## Amire külön figyelj

- **Tárolt vs. hadrendben lévő gép.** Sok forrás a teljes állományt közli, a
  hadrafoghatót nem. Ha tudod a különbséget, jelezd.
- **Régi adat.** A `jelzesek` oszlop megmondja, ha egy sor 2 évnél régebbi.
  Ezeknél a legvalószínűbb a változás.
- **Hiányzó darabszám.** Ahol a `darab` üres, ott a típus megléte lehet igaz,
  csak a mennyiség ismeretlen — ezt ne keverd a „nincs ilyen gépe" esettel.
- **Kivonás dátuma.** A `korabban hasznalt` soroknál az is érték, hogy mikor
  vonták ki — ha tudod, írd oda.

## Kimeneti formátum

Ugyanazokkal az azonosító oszlopokkal, hogy vissza tudjam tölteni:

```
orszag_kod | tipus_kod | valtozat | allapot | eredeti_darab | itelet |
helyes_darab | ervenyes_datum | forras | megbizhatosag | megjegyzes
```

CSV, pontosvesszővel elválasztva. Ha egy sorhoz több forrás is tartozik és
azok ellentmondanak egymásnak, azt írd le — **az ellentmondás önmagában
információ**, nem hiba.

## Végül

A táblázat végigolvasása után írj 5–10 mondatot arról, hogy **hol a
leggyengébb ez az adatkészlet**: mely régió, mely kategória vagy mely
időszak adatai a legmegbízhatatlanabbak. Ez fontosabb nekem, mint bármelyik
egyedi javítás — abból tudom, hol kell más forrást bevonni.
