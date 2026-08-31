# Archive — pre-KiCad artifacts (NOT a source of truth)

Everything in this folder predates the KiCad project and is **superseded** by
[`ki_cad_project/farseer/`](../../ki_cad_project/farseer/). It is retained only
as project history.

**Do not read anything here as authoritative.** The reference designators in
these files (`C_pic1`, `J_icsp`, `U5`, `FB2`, `C10/C11`, …) no longer exist in
the KiCad schematic, and several values are known-stale (e.g. the GNSS bias
choke is drawn here as 27 nH; the real part is `L4` = 47 nH). Do not cite these
files, and do not reconcile the KiCad project against them.

Contents:

- `*-schematic.{svg,png,pdf}` — hand-drawn schemdraw renders of the five old
  schematic sheets.
- `gen_*_schematic.py`, `schematic_common.py`, `build_schematics.sh` — the
  Python/schemdraw pipeline that produced those renders.
- `mcu-bom.md`, `cellular-bom.md`, `gnss-bom.md`, `power-supply-bom.md` — the
  hand-maintained per-block BOMs.
- `gen_full_bom.py`, `full-bom.md`, `full-bom.csv` — the merged-BOM generator
  and its outputs.

Current sources of truth:

- Circuit, nets, designators, values, footprints, MPNs: the KiCad project
  (`ki_cad_project/farseer/farseer.kicad_pro`).
- Rendered schematic PDF and BOM CSV: `docs/generated/`, regenerated with
  `scripts/export_kicad.sh`.
- Design rationale: the `docs/*-support-circuit.md` files.
