# -*- coding: utf-8 -*-
"""ac_match.py — kanonikus entitas-illesztes designation-fegyelemmel.

MIERT LETEZIK EZ A MODUL
------------------------
A korabbi `match()` nyers substring-illesztest hasznalt:

    for alias, ident in sorted(index.items(), key=lambda kv: -len(kv[0])):
        if len(alias) >= 4 and alias in v:
            return ident

Ez determinisztikusan hibas. A Beriev A-100LL AEW&C-tesztpad megsemmisuleset
"A-10 Thunderbolt II — Loss x1"-kent vitte be az adatbazisba, mert

    "a-10" in "a-100ll"  ->  True

A hiba osztalya altalanos: MINDEN olyan tipusjel, amely egy masik tipusjel
szamjegy-prefixe, hamis talalatot ad.

    a-10   <- a-100, a-100ll
    f-15   <- f-15 (helyes), de mi vedi az f-150-tol?
    mq-9   <- mq-9 (helyes), mq-90 (nem letezik, de a logika ugyanaz)
    su-27  <- su-27 (helyes), su-270 ...

A javitas ket kenyszer:

  1. BAL HATAR. A tipusjel elott ne allhasson alfanumerikus karakter.
     Ez zarja ki, hogy a "HH-60W" a "uh-60" aliasra illeszkedjen (a "uh-60"
     nem szerepel benne, de a "h-60" igen — es a "h-60" elott ott van a "h").
  2. JOBB HATAR A SZAMJEGYEN. Ha az alias szamjegyre vegzodik, az utana
     kovetkezo karakter NEM lehet szamjegy. Ez zarja ki az a-10 / a-100ll
     osszecsuszast, de MEGTARTJA a valodi variansokat: "a-10c", "f-15ex",
     "f-16v", "c-130j-30", "ah-64e".

A masodik kenyszer azert a helyes szabaly, mert a katonai tipusjeleknel a
szamblokk zarja a csaladot, es ami utana jon (betu, kotojel), az varians.
Egy TOVABBI SZAMJEGY viszont mar mas csaladot jelol.

VARIANS-TUDATOSSAG
------------------
A tipuscsalad es a varians nem ugyanaz a felderitoi objektum. A "HH-60W
Jolly Green II" es a "UH-60M Black Hawk" ugyanabbol a csaladbol szarmazik,
de nem ugyanaz a kepesseg, nem ugyanaz a haderonem-szerep, es NEM ugyanaz az
ORBAT-sor. Ezert az illesztes harom dolgot ad vissza:

    type_id      — a kanonikus katalogus-csalad (vagy None)
    variant_raw  — a forrasban szereplo tipusjel, ahogy irtak
    match_kind   — exact | variant | family | none

Az ORBAT ezutan eldontheti, hogy egy varians-szintu esemenyhez szabad-e
csalad-szintu baseline-t rendelni. (Nem szabad: lasd a UH-60 "Active 2000"
sort egy 26 gepes HH-60W esemeny mellett.)

Fuzzy illesztes CSAK itt, az ingestion/review szakaszban tortenik. A riport
elóallitasakor soha — ott kizarolag a type_id foreign key hasznalhato.
"""
import re

__all__ = ["build_index", "match_type", "match_country", "extract_designation",
           "normalise", "designation_family"]


# --------------------------------------------------------------------------
# Normalizalas
# --------------------------------------------------------------------------

# Unicode-kotojelek, amiket a sajtó hasznal: en dash, em dash, minus sign,
# non-breaking hyphen. Ezek nelkul az "F‑35" (U+2011) nem talal semmit.
_DASHES = "‐‑‒–—―−"
_DASH_RX = re.compile("[" + _DASHES + "]")
_WS_RX = re.compile(r"\s+")


def normalise(value):
    """Kisbetus, egysegesitett kotojelu, osszevont whitespace-u alak."""
    if not value:
        return ""
    s = _DASH_RX.sub("-", str(value))
    s = s.replace(" ", " ")
    s = _WS_RX.sub(" ", s).strip().lower()
    return s


# --------------------------------------------------------------------------
# Designation-nyelvtan
# --------------------------------------------------------------------------

# Katonai tipusjel: 1-3 betus prefix, kotojel/szokoz, szamblokk, majd
# opcionalis varians-utotag (betuk es/vagy tovabbi -szam blokk).
#   A-10C, F-15EX, HH-60W, C-130J-30, MQ-9B, AH-64E, A-100LL, Su-57, J-10C,
#   KC-46A, VC-25B, F-16C/D, Tu-160M
DESIGNATION_RX = re.compile(
    r"\b([a-z]{1,3})[- ]?(\d{1,4})([a-z]{0,4}(?:[-/][a-z0-9]{1,4})?)\b",
    re.I)


def extract_designation(text):
    """Az elso tipusjel-szeru token a szovegbol: (prefix, szam, utotag).

    >>> extract_designation("Beriev A-100LL development testbed")
    ('a', '100', 'll')
    >>> extract_designation("HH-60W Jolly Green II")
    ('hh', '60', 'w')
    """
    m = DESIGNATION_RX.search(normalise(text))
    if not m:
        return None
    return (m.group(1).lower(), m.group(2), (m.group(3) or "").lower())


def designation_family(text):
    """A tipusjel csalad-alakja utotag nelkul: 'HH-60W' -> 'hh-60'."""
    d = extract_designation(text)
    return "{}-{}".format(d[0], d[1]) if d else None


def _ends_with_digit(s):
    return bool(s) and s[-1].isdigit()


def _boundary_hit(alias, haystack):
    """Hatar-tudatos substring-kereses.

    Igaz, ha az `alias` ugy szerepel a `haystack`-ben, hogy

      * bal oldalon nem all alfanumerikus karakter (szoeleji egyezes), es
      * ha az alias szamjegyre vegzodik, jobb oldalon NEM all szamjegy.

    Ez az a ket kenyszer, ami az A-100LL -> A-10 osszecsuszast megszunteti,
    de az A-10C -> A-10 varians-illesztest megtartja.
    """
    if not alias or not haystack:
        return False
    start = 0
    n, h = len(alias), len(haystack)
    while True:
        i = haystack.find(alias, start)
        if i < 0:
            return False
        start = i + 1
        # Bal hatar: elozo karakter ne legyen alfanumerikus.
        if i > 0 and (haystack[i - 1].isalnum()):
            continue
        j = i + n
        # Jobb hatar: szamjegyre vegzodo aliast ne kovethessen szamjegy.
        if j < h and _ends_with_digit(alias) and haystack[j].isdigit():
            continue
        # Beture vegzodo alias utan se allhasson betu, kulonben a "gripen"
        # illeszkedne a "gripenxyz"-re. (Szam jöhet: "gripen 39".)
        if j < h and alias[-1].isalpha() and haystack[j].isalpha():
            continue
        return True


# --------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------

def build_index(rows, id_key, name_keys=("name",), alias_key="aliases"):
    """Alias -> id tabla. Az azonos aliast igenylo utkozeseket eldobja: egy
    ketertelmu alias rosszabb, mint a hianyzo alias, mert csendben rossz
    entitashoz kot."""
    index, collisions = {}, set()
    for r in rows:
        ident = r.get(id_key)
        if not ident:
            continue
        values = [ident] + [r.get(k) for k in name_keys] \
            + list(r.get(alias_key) or [])
        for v in values:
            key = normalise(v)
            if not key:
                continue
            if key in index and index[key] != ident:
                collisions.add(key)
                continue
            index[key] = ident
    for key in collisions:
        index.pop(key, None)
    return index


# --------------------------------------------------------------------------
# Illesztes
# --------------------------------------------------------------------------

def match_type(value, index, family_index=None):
    """Tipus-illesztes. Visszaadja: (type_id, variant_raw, match_kind).

    match_kind:
      exact   — a teljes megnevezes szó szerint a katalogusban van
      variant — a csalad azonositott, a forras variansjelet is ad (A-10C)
      family  — csalad-szintu talalat, varians nelkul
      none    — nincs biztonsagos talalat; a hivo unresolved_type_name-be teszi

    A `family_index` opcionalis: designation-csalad ('hh-60') -> type_id.
    Ha meg van adva, a varians-illesztes ezen keresztul is probal, igy a
    "HH-60W" megtalalja a hh-60 csaladot, ha az katalogizalt — de SOHA nem
    csuszik at egy masik csaladba (uh-60).
    """
    raw = str(value or "").strip()
    v = normalise(raw)
    if not v:
        return None, None, "none"

    # A forras tipusjele MINDIG kiertekelesre kerul, fuggetlenul attol, hogyan
    # talalt az index. Ha a forras variansjelet ad (A-10C, HH-60W, F-15EX), az
    # varians-szintu megfigyeles — akkor is, ha a katalogus kanonikus NEVE
    # eppen variansszintu ("F-15EX Eagle II" a f-15 designationje). Ezt a
    # tudast az ORBAT hasznalja: csalad-baseline nem rendelhetó varians-
    # szintu esemenyhez.
    d = extract_designation(v)
    has_variant = bool(d and d[2])

    def result(ident, kind):
        return ident, (raw if has_variant else None), \
            ("variant" if has_variant else kind)

    # 1. Teljes, szó szerinti egyezes.
    if v in index:
        return result(index[v], "exact")

    # 2. Designation-alapu illesztes: a csaladot a NYELVTANBOL keressuk,
    #    nem substringgel.
    if d:
        prefix, number, _suffix = d
        fam = "{}-{}".format(prefix, number)
        for cand in (fam, "{}{}".format(prefix, number)):
            if cand in index:
                return result(index[cand], "family")
        if family_index and fam in family_index:
            return result(family_index[fam], "family")

    # 3. Hatar-tudatos alias-illesztes, a leghosszabb aliassal kezdve.
    #    Ez fogja a nev szerinti tipusokat ("Gripen", "Rafale", "Typhoon") es
    #    a katalogizalt varians-aliasokat ("HH-60" a uh-60 alatt).
    for alias, ident in sorted(index.items(), key=lambda kv: -len(kv[0])):
        if len(alias) < 4:
            continue
        if not _boundary_hit(alias, v):
            continue
        # Ha a forras designationt is tartalmaz, es az MAS csaladhoz tartozik,
        # mint az alias, nem illesztunk. Igy a "Beriev A-100LL" alias-uton sem
        # lesz a-10. A csalad-egyezest a SZAMBLOKK dönti el: a "hh-60" alias
        # es a "hh-60w" forras ugyanaz a csalad, a "a-10" es "a-100ll" nem.
        if d:
            alias_d = extract_designation(alias)
            if alias_d and alias_d[1] != d[1]:
                continue
        return result(ident, "family")

    return None, raw or None, "none"


def match_country(value, index):
    """Orszag-illesztes. Nincs designation-nyelvtan, de a hatar-kenyszer itt
    is kell: a 'Niger' ne illeszkedjen a 'Nigeria'-ra."""
    v = normalise(value)
    if not v:
        return None
    if v in index:
        return index[v]
    for alias, ident in sorted(index.items(), key=lambda kv: -len(kv[0])):
        if len(alias) >= 4 and _boundary_hit(alias, v):
            return ident
    return None
