# -*- coding: utf-8 -*-
"""PDF <-> Word tartalmi egyezes es Word-integritas a Command Brief v2-hoz.

Usage: python3 e2e/check_parity.py <rows.json> <week> <brief.pdf> <brief.docx>

Ellenorzi:
  * a .docx egy ervenyes OOXML csomag (nincs mappa-bejegyzes, a
    [Content_Types].xml elol, minden resz XML-kent beolvashato);
  * valodi stilusok: Title, Heading1-3, Caption, Header/Footer, BriefTable;
  * fejlec es lablec (oldalszammal) letezik;
  * a forrasjegyzek minden eleme kattinthato hiperhivatkozas az eredeti URL-re;
  * a terkepek nagy felbontasu PNG-k (>= 2000 px szeles);
  * a magyar ekezetes szoveg epen van;
  * MINDEN vezetoi szoveg (bottom line, KJ-mezok, sorok, gapek, outlook,
    forrascimek) szerepel a PDF-ben ES a Word-fajlban is.
"""
import json
import re
import struct
import subprocess
import sys
import zipfile

rows_path, week, pdf_path, docx_path = sys.argv[1:5]
FAILS = []


def ok(label, cond, extra=""):
    print("  {} {}{}".format("ok  " if cond else "FAIL", label,
                            "  — " + extra if extra else ""))
    if not cond:
        FAILS.append(label)


def norm(t):
    # Sortores-elvalasztas: a PDF-szovegkinyeres a sorvegi kotojelet
    # elnyeli ("south-eastern" -> "southeastern"), ezert a kotojelet is
    # kihagyjuk az osszevetesbol.
    t = t.replace("­", "").replace("‑", "").replace("-", "")
    return re.sub(r"\s+", "", t)


rows = json.load(open(rows_path, encoding="utf-8"))
b = next(r for r in rows if r["week_label"] == week)["payload"]["command_brief"]

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
rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
links = set(re.findall(r'Target="(https?://[^"]+)"\s+TargetMode="External"',
                       rels)) | set(re.findall(
                           r'TargetMode="External"[^>]*Target="(https?://[^"]+)"',
                           rels))
reg_urls = {s["url"].replace("&", "&amp;") for s in b["page5"]["sources"]}
ok("every register source is a working hyperlink", reg_urls <= links,
   "{} of {}".format(len(reg_urls & links), len(reg_urls)))
pngs = [n for n in names if n.startswith("word/media/") and n.endswith(".png")]
widths = []
for n in pngs:
    head = z.read(n)[:24]
    widths.append(struct.unpack(">I", head[16:20])[0])
ok("two map images embedded", len(pngs) == 2, str(len(pngs)))
ok("maps are high resolution (≥2000 px)", all(w >= 2000 for w in widths),
   str(widths))

docx_text = "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", doc))
docx_text = (docx_text.replace("&amp;", "&").replace("&lt;", "<")
             .replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'"))
ok("status line visible in Word", b["status_line"] in docx_text)
for field in ("week_label", "window_label", "generated_utc",
              "methodology_version", "hu_model_version"):
    ok("metadata in Word: {}".format(field),
       norm(str(b["meta"].get(field) or "")) in norm(docx_text))
pdf_text = subprocess.run(["pdftotext", pdf_path, "-"],
                          capture_output=True, text=True).stdout
nd, np_ = norm(docx_text), norm(pdf_text)

exec_texts = [s["text"] for s in b["page1"]["bottom_line"]["sentences"]]
for k in b["page1"]["primary"]:
    exec_texts += [k[f] for f in ("statement", "what_changed", "assessment",
                                  "why_hungary", "next_observable",
                                  "alternative_explanation")]
exec_texts += [x["line"] for x in b["page1"]["secondary_watch"]]
for r in b["page2"]["rows"]:
    exec_texts += [r["what_changed"], r["effect"], r["next_observable"]]
for q in b["page2"]["collection_requirements"]:
    exec_texts += [q["question"], q["observable"]]
for sec in b["page3"]["sections"]:
    exec_texts += [i["what_changed"] for i in sec["items"]]
    exec_texts += [i["assessment"] for i in sec["items"] if i["assessment"]]
exec_texts += [i["assessment"] for i in b["page4"]["global"]["items"]]
exec_texts += [g["text"] for g in b["page4"]["intelligence_gaps"]]
exec_texts += [o["expected_observable"] for o in b["page4"]["outlook"]]
for w in b["page4"]["priority_watch"]:
    exec_texts += [w["why"], w["next_observable"]]
exec_texts += [s["title"] for s in b["page5"]["sources"]]
exec_texts += [t for sec in b["page5"]["legend"] for _, t in sec["items"]]
exec_texts = [t for t in exec_texts if t]
miss_d = [t for t in exec_texts if norm(t) not in nd]
miss_p = [t for t in exec_texts if norm(t) not in np_]
ok("all {} executive texts present in Word".format(len(exec_texts)),
   not miss_d, "; ".join(x[:60] for x in miss_d[:3]))
ok("all {} executive texts present in PDF".format(len(exec_texts)),
   not miss_p, "; ".join(x[:60] for x in miss_p[:3]))
ok("no ellipsis in Word text", "…" not in docx_text)
hu = [s["title"] for s in b["page5"]["sources"]
      if re.search("[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]", s["title"])]
ok("Hungarian characters intact in Word and PDF", all(
    norm(t) in nd and norm(t) in np_ for t in hu), "{} title(s)".format(len(hu)))
print("\n" + ("{} parity check(s) FAILED".format(len(FAILS)) if FAILS
              else "All PDF/Word parity and integrity checks passed."))
sys.exit(1 if FAILS else 0)
