#!/usr/bin/env bash
# Export the schematic PDF and BOM CSV from the KiCad project (the source of
# truth for the circuit) into docs/generated/. Outputs are machine-generated:
# never hand-edit them, always re-run this script after a schematic change.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCH="$REPO_ROOT/ki_cad_project/farseer/farseer.kicad_sch"
OUT_DIR="$REPO_ROOT/docs/generated"

KICAD_CLI="${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}"
if ! [ -x "$KICAD_CLI" ]; then
  KICAD_CLI="$(command -v kicad-cli || true)"
fi
if [ -z "$KICAD_CLI" ]; then
  echo "error: kicad-cli not found (install KiCad or set KICAD_CLI)" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

"$KICAD_CLI" sch export pdf \
  -o "$OUT_DIR/farseer-schematic.pdf" \
  "$SCH"

"$KICAD_CLI" sch export bom \
  -o "$OUT_DIR/farseer-bom.csv" \
  --fields 'Reference,Value,Footprint,MPN,Manufacturer,Alt MPN,Description,${DNP}' \
  --labels 'Reference,Value,Footprint,MPN,Manufacturer,Alt MPN,Description,DNP' \
  --group-by 'Value,MPN,${DNP}' \
  "$SCH"

echo "Wrote:"
echo "  $OUT_DIR/farseer-schematic.pdf"
echo "  $OUT_DIR/farseer-bom.csv"
