#!/usr/bin/env bash
# Export the schematic PDF and BOM CSV from the KiCad project (the source of
# truth for the circuit) into docs/generated/, write the controlled-impedance
# spec for the fab, then rebuild the JLCPCB assembly BOMs from that CSV.
# Outputs are machine-generated: never hand-edit them, always re-run this
# script after a schematic or board change.
#
# The JLCPCB step is offline - it reuses the LCSC part numbers already in
# docs/generated/jlcpcb-parts.csv and warns if the schematic introduced an MPN
# that has never been looked up. Run scripts/lookup_lcsc.py to resolve those.
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

# Controlled-impedance spec for the JLCPCB order, derived from the RF_IN
# netclass, the GNSS_RF_CPW rule and the board stackup.
python3 "$REPO_ROOT/scripts/export_impedance_spec.py"

python3 "$REPO_ROOT/scripts/export_jlcpcb.py" --quiet
