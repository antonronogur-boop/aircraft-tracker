# -*- coding: utf-8 -*-
"""A hivatalos Word fallback template (.dotx) ellenorzese.

Usage: python3 e2e/check_template.py <Command_Air_Intelligence_Brief.dotx>

  * .dotx csomag (template content type), XSD-validacio ha elerheto;
  * a presentation schema MINDEN cimkeje (CB_*) content control — minden
    lista-blokk a schema max_items helyevel;
  * a kitoltendo mezok helyorzok (showingPlcHdr), szerkeszthetok (sdtLocked);
  * a fix design-elemek tartalom-zaroltak; terkep-helyek kep-vezerlok;
  * template-verzio a dokumentum-tulajdonsagokban;
  * LibreOffice megnyitja / PDF-be alakitja, nincs kozel ures koztes oldal.
Microsoft Word automatizalas ebben a kornyezetben NINCS: a Word-kompatibilitast
az ISO/IEC 29500 XSD-validacio es a LibreOffice-render tamasztja ala.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import ac_presentation as P  # noqa: E402

path = sys.argv[1]
FAILS = []


def ok(label, cond, extra=""):
    print("  {} {}{}".format("ok  " if cond else "FAIL", label, "  — " + extra if extra else ""))
    if not cond:
        FAILS.append(label)


schema = P.load()
z = zipfile.ZipFile(path)
names = z.namelist()
ct = z.read("[Content_Types].xml").decode("utf-8")
ok(".dotx content type (wordprocessingml.template)", "wordprocessingml.template.main+xml" in ct)
ok("no folder entries, [Content_Types].xml first", names[0] == "[Content_Types].xml" and not any(n.endswith("/") for n in names))
validator = "/mnt/skills/public/docx/scripts/office/validate.py"
if os.path.exists(validator):
    r = subprocess.run([sys.executable, validator, path], capture_output=True, text=True, timeout=180)
    ok("OOXML XSD validation (ISO/IEC 29500)", "PASSED" in r.stdout, (r.stdout + r.stderr).strip()[-160:])
doc = z.read("word/document.xml").decode("utf-8")
sd = {}
for x in re.findall(r"<w:sdtPr>(.*?)</w:sdtPr>", doc):
    t = re.search(r'<w:tag w:val="([^"]+)"', x).group(1)
    sd.setdefault(t, []).append(x)
want = P.all_tags(schema)
missing = [t for t in want if t not in sd]
ok("every schema tag is a content control ({} tags)".format(len(want)), not missing, ", ".join(missing[:6]))
copy_tags = [f["tag"].replace("{n}", str(i + 1)) for _, blk in P.blocks(schema) for f in P.copy_fields(blk)
             if f.get("tag") for i in range((blk.get("max_items") or 1) if "{n}" in f["tag"] else 1)]
ok("publication-copy fields are placeholders (showingPlcHdr)",
   all(all("<w:showingPlcHdr/>" in x for x in sd[t]) for t in copy_tags if t in sd))
ok("fillable fields are editable (sdtLocked, not content-locked)",
   all(all('w:val="sdtLocked"' in x for x in sd[t]) for t in copy_tags if t in sd))
ok("fixed design text is content-locked",
   sd.get("CB_FIXED") and all('w:val="sdtContentLocked"' in x for x in sd["CB_FIXED"]), str(len(sd.get("CB_FIXED", []))))
ok("map placeholders are picture content controls",
   all(any("<w:picture/>" in x for x in sd.get(t, [])) for t in ("CB_MAP_CEE", "CB_MAP_GLOBAL")))
ok("placeholder text style defined", 'w:styleId="PlaceholderText"' in z.read("word/styles.xml").decode("utf-8"))
custom = z.read("docProps/custom.xml").decode("utf-8")
ok("template version in document properties", "CB_TEMPLATE_VERSION" in custom and schema["template_version"] in custom)
text = "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", doc))
ok("legend and analytical discipline included", all(sec["title"] in text for sec in schema["legend"]) and "Analytical discipline" in text)
footers = "".join(z.read(n).decode("utf-8") for n in names if n.startswith("word/footer"))
ok("micro-legend in the footer of every page", schema["micro_legend"].split(" · ")[0] in footers)
ok("no ellipsis", "…" not in text)
soffice = shutil.which("soffice") or shutil.which("libreoffice")
if soffice:
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "t.docx")
    shutil.copy(path, src)
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, src], capture_output=True, timeout=240)
    pdf = os.path.join(tmp, "t.pdf")
    ok("LibreOffice opens and renders the template", os.path.exists(pdf))
    if os.path.exists(pdf):
        subprocess.run(["pdftoppm", "-r", "30", "-gray", pdf, os.path.join(tmp, "pg")], capture_output=True)
        from PIL import Image  # noqa: E402
        fills = []
        for f in sorted(x for x in os.listdir(tmp) if x.startswith("pg")):
            im = Image.open(os.path.join(tmp, f)).convert("L")
            w, h = im.size
            top, bot = int(h * 0.07), int(h * 0.91)
            px = im.load()
            last = top
            for y in range(top, bot):
                if any(px[x, y] < 200 for x in range(0, w, 2)):
                    last = y
            fills.append(round((last - top) / float(bot - top), 2))
        print("  template render (LibreOffice): {} pages, fill {}".format(len(fills), fills))
        ok("no nearly-empty intermediate pages", not [i for i, f in enumerate(fills[:-1]) if f < 0.45])
print("  NOTE: Microsoft Word automation is not available here — Word compatibility rests on the XSD validation, not on opening the file in Word.")
print("\n" + ("{} template check(s) FAILED".format(len(FAILS)) if FAILS else "All Word template checks passed."))
sys.exit(1 if FAILS else 0)
