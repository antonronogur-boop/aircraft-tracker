# -*- coding: utf-8 -*-
"""PDF <-> Word tartalmi egyezes es Word-integritas a Command Briefhez.

Usage: python3 e2e/check_parity.py <published_brief.json> <brief.pdf> <brief.docx>

A <published_brief.json> a KIADOTT brief (a publikacios szoveggel), amit az
E2E ment (OUT/published_brief.json). Ellenorzi:
  * ervenyes OOXML csomag (nincs mappa-bejegyzes, [Content_Types].xml elol,
    minden resz XML-kent beolvashato; ha elerheto, XSD-validacio);
  * valodi stilusok: Title, Heading1-3, Caption, Header/Footer, BriefTable;
  * fejlec es lablec (oldalszammal);
  * CONTENT CONTROLS: a presentation schema minden mezoje stabil CB_* cimkeju
    Word content control; a fix szoveg tartalom-zarolt; a kontrollalt
    metaadat (forras, HU, SIG, CONF) tartalom-zarolt; nem maradt konyvjelzo;
  * template-verzio, statusz es kiadas a dokumentum-tulajdonsagokban;
  * a forrasjegyzek minden eleme kattinthato hiperhivatkozas az eredeti URL-re,
    a kontextus-forras kulon "Context for" oszlopban;
  * a terkepek nagy felbontasu PNG-k (>= 2000 px), kep-vezerloben;
  * a magyar ekezetes szoveg epen van;
  * LAYOUT PARITY != PIXEL PARITY: MINDEN publikacios szoveg (a schema copy
    mezoi), forrascim es jelmagyarazat szerepel a PDF-ben ES a Wordben is;
  * a Word nem tartalmaz kozel ures koztes oldalt (LibreOffice render).
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
import ac_presentation as P  # noqa: E402

brief_path, pdf_path, docx_path = sys.argv[1:4]
FAILS = []


def ok(label, cond, extra=""):
    print("  {} {}{}".format("ok  " if cond else "FAIL", label,
                            "  — " + extra if extra else ""))
    if not cond:
        FAILS.append(label)


def norm(t):
    # A PDF-szovegkinyeres a sorvegi kotojelet elnyeli, ezert a kotojelet is
    # kihagyjuk az osszevetesbol; a tipografiai aposztrofot egysegesitjuk.
    t = t.replace("­", "").replace("‑", "").replace("-", "")
    t = t.replace("’", "'")
    return re.sub(r"\s+", "", t)


b = json.load(open(brief_path, encoding="utf-8"))
schema = P.load()

z = zipfile.ZipFile(docx_path)
names = z.namelist()
ok("no folder entries in the ZIP", not any(n.endswith("/") for n in names))
ok("[Content_Types].xml first", names[0] == "[Content_Types].xml")
import xml.dom.minidom as md  # noqa: E402
bad = []
for n in names:
    if n.endswith((".xml", ".rels")):
        try:
            md.parseString(z.read(n))
        except Exception as e:  # noqa: BLE001
            bad.append("{}: {}".format(n, e))
ok("every XML part parses", not bad, "; ".join(bad[:2]))
validator = "/mnt/skills/public/docx/scripts/office/validate.py"
if os.path.exists(validator):
    r = subprocess.run([sys.executable, validator, docx_path],
                       capture_output=True, text=True, timeout=180)
    ok("OOXML XSD validation (ISO/IEC 29500)", "PASSED" in r.stdout,
       (r.stdout + r.stderr).strip().splitlines()[-1:] and
       (r.stdout + r.stderr).strip().splitlines()[-1])
else:
    print("  (XSD validator not available — schema validation skipped)")
styles = z.read("word/styles.xml").decode("utf-8")
for sid in ("Title", "Heading1", "Heading2", "Heading3", "Caption", "Header",
            "Footer", "BriefTable", "Hyperlink"):
    ok("style {} defined".format(sid), 'w:styleId="{}"'.format(sid) in styles)
doc = z.read("word/document.xml").decode("utf-8")
for sid in ("Title", "Heading1", "Heading2", "Caption"):
    ok("style {} used".format(sid), 'w:pStyle w:val="{}"'.format(sid) in doc)
ok("tables use the BriefTable style", 'w:tblStyle w:val="BriefTable"' in doc)
ok("header part present", any(n.startswith("word/header") for n in names))
footer = "".join(z.read(n).decode("utf-8") for n in names
                 if n.startswith("word/footer") and n.endswith(".xml"))
ok("footer with page numbers", "PAGE" in footer and "NUMPAGES" in footer)

# --- content controls ---
sdts = re.findall(r"<w:sdtPr>(.*?)</w:sdtPr>", doc)
tags = {}
for x in sdts:
    t = re.search(r'<w:tag w:val="([^"]+)"', x)
    lk = re.search(r'<w:lock w:val="([^"]+)"', x)
    tags.setdefault(t.group(1) if t else None, []).append(
        lk.group(1) if lk else None)
ok("content controls present", len(sdts) > 50, str(len(sdts)))
ok("every content control has a tag", None not in tags)
ok("no leftover bookmarks", "w:bookmarkStart" not in doc)
ok("balanced content controls", doc.count("<w:sdt>") == doc.count("</w:sdt>"))
expected = []
counts = {
    "bottom_line": len(b["page1"]["bottom_line"]["sentences"]),
    "primary": len(b["page1"]["primary"]),
    "secondary_watch": len(b["page1"]["secondary_watch"]),
    "regional_rows": len(b["page2"]["rows"]),
    "collection_requirements": len(b["page2"]["collection_requirements"]),
    "p3_items": sum(len(s["items"]) for s in b["page3"]["sections"]),
    "maturity": len(b["page3"]["maturity"]["rows"]),
    "change_table": len(b["page3"]["change_table"]["rows"]),
    "global_items": len(b["page4"]["global"]["items"]),
    "priority_watch": len(b["page4"]["priority_watch"]),
    "intelligence_gaps": len(b["page4"]["intelligence_gaps"]),
    "outlook": len(b["page4"]["outlook"]),
}
for _, blk in P.blocks(schema):
    k = counts.get(blk["id"], 1)
    for f in blk.get("fields") or []:
        t = f.get("tag")
        if not t or f["edit"] != "copy":
            continue
        expected += [t.replace("{n}", str(i + 1)) for i in range(k)] \
            if "{n}" in t else [t]
missing = [t for t in expected if t not in tags]
ok("every publication-copy field is a CB_* content control "
   "({} expected)".format(len(expected)), not missing, ", ".join(missing[:5]))
for t in ("CB_KJ1_TITLE", "CB_KJ1_WHAT_CHANGED", "CB_KJ1_ASSESSMENT",
          "CB_KJ1_HU_RELEVANCE", "CB_KJ1_NEXT_OBSERVABLE", "CB_BOTTOM_LINE",
          "CB_BOTTOM_LINE_1", "CB_MAP_CEE", "CB_MAP_GLOBAL"):
    if t.startswith("CB_KJ1") and not counts["primary"]:
        continue
    ok("content control {} present".format(t), t in tags)
ok("CB_KJ1_SOURCES present (controlled)", not counts["primary"] or
   "CB_KJ1_SOURCES" in tags)
ok("fixed template text is content-locked",
   set(tags.get("CB_FIXED", [])) == {"sdtContentLocked"},
   str(len(tags.get("CB_FIXED", []))))
ctl_tags = [t for t in tags if t and re.search(
    r"_(SOURCES|HU_LEVEL|SIG|CONF|HORIZON)$", t)]
ok("controlled metadata (sources / HU / SIG / CONF) is content-locked",
   ctl_tags and all(set(tags[t]) == {"sdtContentLocked"} for t in ctl_tags),
   str(len(ctl_tags)))
ok("publication-copy controls are editable (not content-locked)",
   all(set(tags[t]) == {"sdtLocked"} for t in expected if t in tags))
ok("maps in picture content controls", doc.count("<w:picture/>") == 2)
custom = z.read("docProps/custom.xml").decode("utf-8") \
    if "docProps/custom.xml" in names else ""
ok("template version in document properties",
   "CB_TEMPLATE_VERSION" in custom and schema["template_version"] in custom)
ok("draft status / release in document properties",
   "CB_DRAFT_STATUS" in custom and "CB_RELEASE" in custom)
ok("Word marked as working copy, not canonical",
   "CB_CANONICAL" in custom and "working copy" in custom)

rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
links = set(re.findall(r'Target="(https?://[^"]+)"\s+TargetMode="External"',
                       rels)) | set(re.findall(
                           r'TargetMode="External"[^>]*Target="(https?://[^"]+)"',
                           rels))
reg_urls = {s["url"].replace("&", "&amp;") for s in b["page5"]["sources"]}
ok("every register source is a working hyperlink", reg_urls <= links,
   "{} of {}".format(len(reg_urls & links), len(reg_urls)))
pngs = [n for n in names if n.startswith("word/media/") and n.endswith(".png")]
widths = [struct.unpack(">I", z.read(n)[16:20])[0] for n in pngs]
ok("two map images embedded", len(pngs) == 2, str(len(pngs)))
ok("maps are high resolution (≥2000 px)", all(w >= 2000 for w in widths),
   str(widths))

docx_text = "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", doc))
docx_text = (docx_text.replace("&amp;", "&").replace("&lt;", "<")
             .replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'"))
ok("status line visible in Word", b["status_line"] in docx_text)
for field in ("week_label", "window_label", "generated_utc",
              "methodology_version", "hu_model_version", "template_version"):
    ok("metadata in Word: {}".format(field),
       norm(str(b["meta"].get(field) or "")) in norm(docx_text))
ctx_src = [s for s in b["page5"]["sources"]
           if s.get("evidence_role") == "CONTEXT_ONLY"]
ok("Word register: separate 'Context for' column",
   "Context for" in docx_text and "Evidence for" in docx_text)
if ctx_src:
    ok("Word register: context source labelled 'Context only — not evidence'",
       "Context only — not evidence" in docx_text)

pdf_text = subprocess.run(["pdftotext", pdf_path, "-"],
                          capture_output=True, text=True).stdout
pdf_raw = subprocess.run(["pdftotext", "-raw", pdf_path, "-"],
                         capture_output=True, text=True).stdout
nd, np_ = norm(docx_text), norm(pdf_text) + "\n" + norm(pdf_raw)

exec_texts = P.executive_texts(b, schema)
exec_texts += [s["title"] for s in b["page5"]["sources"]]
exec_texts += [t for sec in b["page5"]["legend"] for _, t in sec["items"]]
exec_texts = [t for t in exec_texts if t]
miss_d = [t for t in exec_texts if norm(t) not in nd]
miss_p = [t for t in exec_texts if norm(t) not in np_]
ok("all {} publication texts present in Word".format(len(exec_texts)),
   not miss_d, "; ".join(x[:60] for x in miss_d[:3]))
ok("all {} publication texts present in PDF".format(len(exec_texts)),
   not miss_p, "; ".join(x[:60] for x in miss_p[:3]))
for k in b["page1"]["primary"]:
    s = " ".join([str(k["significance"]), k["hu_relevance"]["level"]])
    ok("scores in Word and PDF: {} ({})".format(k["id"], s),
       "HU" + k["hu_relevance"]["level"] in nd and
       "HU" + k["hu_relevance"]["level"] in np_)
ok("no ellipsis in Word text", "…" not in docx_text)
hu = [s["title"] for s in b["page5"]["sources"]
      if re.search("[áéíóöőúüűÁÉÍÓÖŐÚÜŰąćęłńśźżĄĆĘŁŃŚŹŻ]", s["title"])]
ok("accented (HU/PL) characters intact in Word and PDF", all(
    norm(t) in nd and norm(t) in np_ for t in hu), "{} title(s)".format(len(hu)))

# --- Word layout: nincs kozel ures koztes oldal (LibreOffice render) ---
soffice = shutil.which("soffice") or shutil.which("libreoffice")
if soffice and shutil.which("pdftoppm"):
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "brief.docx")
    shutil.copy(docx_path, src)
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir",
                    tmp, src], capture_output=True, timeout=240)
    dpdf = os.path.join(tmp, "brief.pdf")
    if os.path.exists(dpdf):
        subprocess.run(["pdftoppm", "-r", "30", "-gray", dpdf,
                        os.path.join(tmp, "pg")], capture_output=True)
        pages = sorted(f for f in os.listdir(tmp) if f.startswith("pg"))
        fills = []
        from PIL import Image  # noqa: E402
        for f in pages:
            im = Image.open(os.path.join(tmp, f)).convert("L")
            w, h = im.size
            top, bot = int(h * 0.07), int(h * 0.91)
            px = im.load()
            last = top
            for y in range(top, bot):
                if any(px[x, y] < 200 for x in range(0, w, 2)):
                    last = y
            fills.append(round((last - top) / float(bot - top), 2))
        sparse = [i + 1 for i, fl in enumerate(fills[:-1]) if fl < 0.45]
        print("  Word render (LibreOffice): {} pages, body fill per page {}"
              .format(len(fills), fills))
        ok("Word: no nearly-empty intermediate pages", not sparse,
           "sparse pages: {}".format(sparse))
    else:
        ok("Word converts with LibreOffice", False)
else:
    print("  (LibreOffice not available — Word layout check skipped)")

print("\n" + ("{} parity check(s) FAILED".format(len(FAILS)) if FAILS
              else "All PDF/Word parity and integrity checks passed."))
sys.exit(1 if FAILS else 0)
