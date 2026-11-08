# -*- coding: utf-8 -*-
"""Command Brief Presentation Schema — Python oldali olvaso.

A config/command_brief_presentation.json az EGYETLEN megjelenitesi
szabvany (web, PDF, DOCX, .dotx). Ez a modul:
  * bejarja a schema blokkjait egy briefen (path -> tetelek);
  * felsorolja a publikacios (copy) es a kontrollalt mezoket;
  * a parity-teszt ebbol kepzi a "vezetoi szovegek" listajat, igy a
    kimenetek osszevetese nem kezzel karbantartott lista.
Nem ir semmit, nem modosit semmit.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "config" / "command_brief_presentation.json"


def load(path=None):
    return json.loads(Path(path or SCHEMA_PATH).read_text(encoding="utf-8"))


def blocks(schema=None):
    schema = schema or load()
    for page in schema["pages"]:
        for blk in page["blocks"]:
            yield page, blk


def _walk(obj, parts):
    if not parts:
        yield obj
        return
    head, rest = parts[0], parts[1:]
    if head.endswith("[]"):
        for x in (obj or {}).get(head[:-2]) or []:
            yield from _walk(x, rest)
    else:
        nxt = (obj or {}).get(head) if isinstance(obj, dict) else None
        if nxt is None:
            return
        yield from _walk(nxt, rest)


def block_items(brief, blk):
    """A blokk tetelei (lista-blokknal a tetelek, objektumnal maga az
    objektum) — sorrendben."""
    out = []
    for target in _walk(brief, blk["path"].split(".")):
        if blk["kind"] == "list":
            if isinstance(target, list):
                out.extend(target)
        elif blk["kind"] == "object":
            out.append(target)
    return out


def item_key(blk, item, index):
    k = blk.get("item_key") or "#index"
    if k == "#index" or not isinstance(item, dict) or item.get(k) in (
            None, ""):
        return "#{}".format(index)
    return str(item.get(k))


def get_field(item, key):
    cur = item
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def copy_fields(blk):
    return [f for f in blk.get("fields") or [] if f.get("edit") == "copy"]


def controlled_fields(blk):
    return [f for f in blk.get("fields") or []
            if f.get("edit") == "controlled"]


def executive_texts(brief, schema=None):
    """Minden publikacios (copy) szoveg a briefben — a parity-teszthez."""
    out = []
    for _, blk in blocks(schema):
        for item in block_items(brief, blk):
            for f in copy_fields(blk):
                v = get_field(item, f["key"])
                if isinstance(v, str) and v.strip():
                    out.append(v)
    return out


def all_tags(schema=None):
    tags = []
    for _, blk in blocks(schema):
        n_max = blk.get("max_items") or 1
        for f in blk.get("fields") or []:
            t = f.get("tag")
            if not t:
                continue
            if "{n}" in t:
                tags += [t.replace("{n}", str(i + 1)) for i in range(n_max)]
            else:
                tags.append(t)
        if blk.get("tag"):
            tags.append(blk["tag"])
        fig = (blk.get("figure") or {}).get("tag")
        if fig:
            tags.append(fig)
    return tags
