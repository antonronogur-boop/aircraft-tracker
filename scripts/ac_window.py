# -*- coding: utf-8 -*-
"""Heti jelentesi ablak — Europe/Budapest, SZERDA 00:00:00 -> KEDD 23:59:59.

Miert sajat DST-szabaly es nem zoneinfo: a helyi Windows Python 3.9 alatt a
zoneinfo-nak nincs tzdata-ja, es a jelentesnek MINDENHOL ugyanazt az ablakot
kell szamolnia (GitHub Actions, helyi gep, teszt). Az EU-szabaly 1996 ota
valtozatlan: nyari ido marcius utolso vasarnapja 01:00 UTC-tol oktober utolso
vasarnapja 01:00 UTC-ig. Budapest: CET = UTC+1, CEST = UTC+2.

A gyujtes (napi) es a feldolgozas tovabbra is minden nap fut. Az ablak csak
azt donti el, hogy egy esemeny MELYIK heti jelentesbe tartozik.
"""
import os
from datetime import date, datetime, time, timedelta, timezone

TZ_NAME = "Europe/Budapest"


def _last_sunday(year, month):
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 \
        else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def budapest_offset(utc_dt):
    """A Budapest-i UTC-eltolas (timedelta) egy UTC idopontban."""
    if utc_dt.tzinfo is not None:
        utc_dt = utc_dt.astimezone(timezone.utc).replace(tzinfo=None)
    y = utc_dt.year
    start = datetime.combine(_last_sunday(y, 3), time(1, 0))
    end = datetime.combine(_last_sunday(y, 10), time(1, 0))
    return timedelta(hours=2) if start <= utc_dt < end else timedelta(hours=1)


def to_local(utc_dt):
    """UTC (aware vagy naiv-UTC) -> naiv Budapest-i helyi ido."""
    if utc_dt.tzinfo is not None:
        utc_dt = utc_dt.astimezone(timezone.utc).replace(tzinfo=None)
    return utc_dt + budapest_offset(utc_dt)


def local_to_utc(local_dt):
    """Naiv Budapest-i helyi ido -> naiv UTC. Ejfelre (az ablak hatarai)
    egyertelmu: a DST-valtas 02:00/03:00 helyi idoben tortenik."""
    guess = local_dt - timedelta(hours=1)
    off = budapest_offset(guess)
    return local_dt - off


def now_utc():
    """A 'most' — tesztelheto: AC_REPORT_NOW=2026-11-11T05:15:00Z."""
    forced = os.environ.get("AC_REPORT_NOW")
    if forced:
        s = forced.strip().replace("Z", "")
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def reporting_window(now=None, prior_period_end=None):
    """Az utolso LEZART szerda->kedd ablak a 'now' pillanathoz kepest.

    Szerda reggeli futasnal: az elozo szerda 00:00:00 -> tegnap (kedd)
    23:59:59. A hetcimke a kedd ISO-hete (= a szerdai futas ISO-hete), igy a
    cimkek folytonosak a korabbi, hetfoi jelentesekkel.

    prior_period_end: az elozo publikalt jelentes utolso napja (YYYY-MM-DD).
    Atallaskor (hetfoi -> szerdai ritmus) a kimarado napokat az ablak
    ELEJEHEZ csatoljuk, es ezt jelezzuk — egy nap sem eshet ki.
    """
    now = now or now_utc()
    local_now = to_local(now)
    days_since_wed = (local_now.weekday() - 2) % 7
    this_wed = local_now.date() - timedelta(days=days_since_wed)
    end_date = this_wed - timedelta(days=1)          # kedd
    start_date = end_date - timedelta(days=6)        # szerda
    transition = None
    if prior_period_end:
        try:
            pe = date.fromisoformat(str(prior_period_end)[:10])
        except ValueError:
            pe = None
        if pe and pe + timedelta(days=1) < start_date:
            transition = {
                "extended_from": start_date.isoformat(),
                "extended_to": (pe + timedelta(days=1)).isoformat(),
                "note": ("window start moved back to the day after the "
                         "previous published period ({}), so no day falls "
                         "between two reports".format(pe.isoformat())),
            }
            start_date = pe + timedelta(days=1)
    start_local = datetime.combine(start_date, time(0, 0, 0))
    end_local = datetime.combine(end_date, time(23, 59, 59))
    iso = end_date.isocalendar()
    return {
        "timezone": TZ_NAME,
        "start_date": start_date,
        "end_date": end_date,
        "start_local": start_local,
        "end_local": end_local,
        "start_utc": local_to_utc(start_local),
        "end_utc": local_to_utc(end_local),
        "week_label": "{}-W{:02d}".format(iso[0], iso[1]),
        "transition": transition,
        "label": "{} 00:00:00 -> {} 23:59:59 ({})".format(
            start_date.isoformat(), end_date.isoformat(), TZ_NAME),
    }


def in_window(day, window):
    """Napi pontossagu datum (datetime/date) az ablakban van-e."""
    if day is None:
        return False
    d = day.date() if isinstance(day, datetime) else day
    return window["start_date"] <= d <= window["end_date"]


def local_day_of_timestamp(value):
    """ISO idobelyeg (UTC, pl. created_at) -> Budapest-i helyi NAP."""
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s[:32])
    except ValueError:
        try:
            dt = datetime.fromisoformat(s[:19])
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return to_local(dt).date()


def parse_utc(value):
    """ISO idobelyeg -> naiv UTC datetime (vagy None)."""
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s[:32])
    except ValueError:
        try:
            dt = datetime.fromisoformat(s[:19])
        except ValueError:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
