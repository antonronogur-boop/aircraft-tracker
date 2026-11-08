#!/usr/bin/env bash
# Command Brief — teljes ellenorzes egy adatkeszleten (adatbazis nelkul).
#   web/e2e/run_all.sh [rows.json] [week]
# Alapertelmezes: a szintetikus fixture (web/e2e/fixture_rows.json, 2026-W46).
# Kell: `next build` utan; Playwright + Chromium; pdftotext; LibreOffice (opcionalis).
set -u
cd "$(dirname "$0")/.."
ROWS="$(realpath "${1:-e2e/fixture_rows.json}")"
WEEK="${2:-2026-W46}"
OUT="$(pwd)/e2e-out/${WEEK}"
STORE="$(mktemp -d)"
PORT="${PORT:-3311}"
rm -rf "$OUT"; mkdir -p "$OUT"
pkill -f "next-server" >/dev/null 2>&1; sleep 1
AC_REPORT_FIXTURE="$ROWS" AC_DRAFT_STORE="file:$STORE" nohup npx next start -p "$PORT" > "$OUT/server.log" 2>&1 &
for i in $(seq 1 30); do curl -s "http://localhost:$PORT/weekly" >/dev/null && break; sleep 1; done
rc=0
echo "== draft model unit tests"; node e2e/draft.unit.cjs "$ROWS" "$WEEK" || rc=1
echo "== browser E2E";            BASE="http://localhost:$PORT" OUT="$OUT" WEEK="$WEEK" LEGACY_WEEK="${LEGACY_WEEK:-2026-W45}" node e2e/command-brief.e2e.cjs || rc=1
echo "== PDF / Word parity";      python3 e2e/check_parity.py "$OUT/published_brief.json" "$OUT/command_brief.pdf" "$OUT/command_brief.docx" || rc=1
echo "== Word template";          python3 e2e/check_template.py "$OUT/Command_Air_Intelligence_Brief.dotx" || rc=1
pkill -f "next-server" >/dev/null 2>&1
echo "== RESULT: $([ $rc = 0 ] && echo PASS || echo FAIL) ($WEEK)"
exit $rc
