#!/usr/bin/env bash
# Regenerate every farseer schematic: SVG from schemdraw, then PDF and PNG.
#
#   ./docs/build_schematics.sh              # all schematics
#   ./docs/build_schematics.sh power gnss   # only the ones named
#   ./docs/build_schematics.sh full         # only the combined whole-board sheet
#
# "full" is the whole-board sheet. It assembles itself from the other four
# generators, so it is always current no matter which of them ran last - but it
# is listed after them so a plain run leaves the combined sheet as the last
# thing written.
#
# Requires: python3 with schemdraw, and rsvg-convert (brew install librsvg).
set -euo pipefail

cd "$(dirname "$0")/.."

# generator stem -> output stem -> PNG zoom factor. The combined sheet is
# already several times the size of any single one, so it renders at 1x; at the
# 2x the others use it would be a 21000 px wide PNG.
SCHEMATICS=(
  "power:power-rails:2"
  "mcu:mcu:2"
  "cellular:cellular:2"
  "gnss:gnss:2"
  "full:full:1"
)

command -v rsvg-convert >/dev/null 2>&1 || {
  echo "error: rsvg-convert not found (brew install librsvg)" >&2
  exit 1
}
python3 -c 'import schemdraw' 2>/dev/null || {
  echo "error: schemdraw not installed (pip3 install schemdraw)" >&2
  exit 1
}

wanted=("$@")

want() {
  [ ${#wanted[@]} -eq 0 ] && return 0
  for w in "${wanted[@]}"; do [ "$w" = "$1" ] && return 0; done
  return 1
}

for entry in "${SCHEMATICS[@]}"; do
  IFS=: read -r name stem zoom <<<"$entry"
  want "$name" || continue

  gen="docs/gen_${name}_schematic.py"
  [ -f "$gen" ] || { echo "error: missing $gen" >&2; exit 1; }

  # The generators import docs/schematic_common.py and write paths relative to
  # the repo root, so run them from here with docs/ on the import path.
  PYTHONPATH=docs python3 "$gen"

  svg="docs/${stem}-schematic.svg"
  rsvg-convert -f pdf -o "docs/${stem}-schematic.pdf" "$svg"
  rsvg-convert -f png -z "$zoom" -o "docs/${stem}-schematic.png" "$svg"
  echo "wrote docs/${stem}-schematic.pdf and .png"
done
