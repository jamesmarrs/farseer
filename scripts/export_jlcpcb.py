#!/usr/bin/env python3
"""Turn the KiCad BOM into JLCPCB assembly BOMs.

Reads docs/generated/farseer-bom.csv (from export_kicad.sh) and
docs/generated/jlcpcb-parts.csv (from lookup_lcsc.py) and writes, in the column
layout JLCPCB's SMT quote page expects (Comment, Designator, Footprint,
LCSC Part #, MPN):

  docs/generated/farseer-jlcpcb-bom-full.csv  every placeable line
  docs/generated/farseer-jlcpcb-bom-smt.csv   SMT lines only, hand-solder and
                                              wave-solder parts removed

R54 is DNP in the schematic and appears in neither file: JLCPCB places whatever
is listed, so a do-not-populate part has to be left out rather than annotated.

Every LCSC number is an exact-MPN match; a blank LCSC Part # means JLCPCB does
not stock that part and the line needs a decision (substitute, consignment, or
hand assembly) before the order goes in.
"""
import argparse
import csv
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN_DIR = os.path.join(REPO_ROOT, "docs", "generated")
BOM_CSV = os.path.join(GEN_DIR, "farseer-bom.csv")
PARTS_CSV = os.path.join(GEN_DIR, "jlcpcb-parts.csv")
FULL_OUT = os.path.join(GEN_DIR, "farseer-jlcpcb-bom-full.csv")
SMT_OUT = os.path.join(GEN_DIR, "farseer-jlcpcb-bom-smt.csv")

JLC_FIELDS = ["Comment", "Designator", "Footprint", "LCSC Part #", "MPN"]

# Parts JLCPCB's SMT line cannot place: through-hole, wave-soldered, or purely
# mechanical. Excluded from the SMT-only BOM and hand-soldered here instead.
HAND_SOLDER = {
    "F1": "blade fuse holder, through-hole (JLC lists it as wave soldering)",
    "C7": "10 x 10.5 mm radial electrolytic, through-hole",
    "J1": "2.54 mm pin header, through-hole",
    "JP1": "2.54 mm pin header, through-hole",
    "J2": "bare solder-wire pads, no purchased part",
    "J3": "right-angle SMA, through-hole",
    "J5": "Mini PCIe socket, through-hole latch posts",
    "J6": "nano-SIM holder, hinged cover",
    "MP1": "optional Mini PCIe retention latch",
}

# KiCad footprint name -> the package name JLCPCB shows for the part. The
# Footprint column is informational for JLC (placement comes from the CPL), but
# a recognisable package makes the BOM review screen usable.
FOOTPRINT_OVERRIDES = {
    "Capacitor_SMD:CP_Elec_10x10.5": "SMD,D10xL10.2mm",
    "Capacitor_Tantalum_SMD:CP_EIA-7343-31_Kemet-D": "EIA-7343-31 (D)",
    "Diode_SMD:D_SMA": "SMA",
    "farseer_footprints:Littelfuse_DO-218AB": "DO-218AB",
    "farseer_footprints:D_PowerDI-5_SBR8U60P5": "PowerDI5",
    "farseer_footprints:D_0402_1005Metric_PESD0402-140": "0402",
    "Fuse:Fuseholder_Blade_Mini_Keystone_3568": "Mini blade fuse holder",
    "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Horizontal": "Header 1x06 P2.54mm",
    "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical": "Header 1x02 P2.54mm",
    "Connector_Wire:SolderWire-0.5sqmm_1x02_P4.6mm_D0.9mm_OD2.1mm_Relief": "Solder pads 1x02",
    "farseer_footprints:SMA_Amphenol_901-143_Horizontal": "SMA right-angle TH",
    "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal": "USB-C 16P SMD",
    "farseer_footprints:Molex_67910-5700_MiniPCIe": "Mini PCIe socket 52P",
    "farseer_footprints:nanoSIM_GCT_SIM8060-6-1-14-00": "nano-SIM holder 6P",
    "farseer_footprints:Molex_48099-5701_MiniPCIe_Latch": "SMD latch",
    "farseer_footprints:L_Bourns_SRN8040TA": "SMD 8.0x8.0mm",
    "farseer_footprints:L_Bourns_SRN6045TA": "SMD 6.0x6.0mm",
    "Inductor_SMD:L_Coilcraft_XAL6060-XXX": "SMD 6.36x6.56mm",
    "Package_SON:Diodes_PowerDI3333-8": "PowerDI3333-8",
    "farseer_footprints:TQFP-48-1EP_7x7mm_P0.5mm_EP3.5x3.5mm_ThermalVias": "TQFP-48_7x7",
    "farseer_footprints:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.95x4.9mm_Mask2.71x3.4mm_ThermalVias": "SOIC-8-EP",
    "farseer_footprints:ublox_NEO-M9N-00B": "SMD-24P",
    "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm": "QFN-24-EP(4x4)",
    "Package_SON:USON-10_2.5x1.0mm_P0.5mm": "USON-10",
}

# Two-terminal chip packages: C_0402_1005Metric -> 0402.
CHIP_RE = re.compile(r"^[A-Z]{1,3}_(\d{4})_\d{4}Metric$")


def die(msg):
    sys.exit(f"error: {msg}")


def short_footprint(footprint):
    """Reduce a KiCad footprint name to a package name JLCPCB will recognise."""
    if footprint in FOOTPRINT_OVERRIDES:
        return FOOTPRINT_OVERRIDES[footprint]
    bare = footprint.split(":", 1)[-1]
    chip = CHIP_RE.match(bare)
    if chip:
        return chip.group(1)
    # Package_TO_SOT_SMD:SOT-23-6, Diode_SMD:D_SOD-123F -> SOT-23-6, SOD-123F
    return bare[2:] if bare.startswith("D_") else bare


def expand_refs(field):
    """'C9,C54-C56' -> ['C9', 'C54', 'C55', 'C56'] (KiCad collapses runs)."""
    refs = []
    for token in field.split(","):
        token = token.strip()
        run = re.match(r"^([A-Za-z]+)(\d+)-[A-Za-z]*(\d+)$", token)
        if run:
            prefix, start, end = run.groups()
            refs += [f"{prefix}{n}" for n in range(int(start), int(end) + 1)]
        elif token:
            refs.append(token)
    return refs


def read_parts_map():
    if not os.path.exists(PARTS_CSV):
        die(f"{PARTS_CSV} not found - run scripts/lookup_lcsc.py first")
    with open(PARTS_CSV, newline="") as fh:
        return {row["MPN"].strip().upper(): row for row in csv.DictReader(fh)}


def build_lines():
    if not os.path.exists(BOM_CSV):
        die(f"{BOM_CSV} not found - run scripts/export_kicad.sh first")
    parts = read_parts_map()

    lines, dnp, unmatched, no_part, never_looked_up = [], [], [], [], []
    with open(BOM_CSV, newline="") as fh:
        for row in csv.DictReader(fh):
            refs = expand_refs(row["Reference"])
            mpn = row["MPN"].strip()
            part = parts.get(mpn.upper(), {})
            if mpn and mpn.upper() not in parts:
                never_looked_up.append(mpn)
            comment = row["Value"].strip() or mpn or row["Description"].strip()
            line = {
                "Comment": comment,
                "Designator": ",".join(refs),
                "Footprint": short_footprint(row["Footprint"].strip()),
                "LCSC Part #": part.get("LCSC", "").strip(),
                "MPN": mpn,
                "_refs": refs,
                "_qty": len(refs),
                "_class": part.get("PartClass", "").strip(),
                "_stock": part.get("Stock", "").strip(),
                "_price": part.get("UnitPrice", "").strip(),
                "_candidates": part.get("JLCCandidates", "").strip(),
            }
            if row["DNP"].strip():
                dnp.append(line)
                continue
            lines.append(line)
            if not mpn:
                no_part.append(line)
            elif not line["LCSC Part #"]:
                unmatched.append(line)
    return lines, dnp, unmatched, no_part, never_looked_up


def write_bom(path, lines):
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=JLC_FIELDS, extrasaction="ignore", quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerows(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true", help="write the files without the summary")
    args = ap.parse_args()

    lines, dnp, unmatched, no_part, never_looked_up = build_lines()
    smt = [ln for ln in lines if not any(r in HAND_SOLDER for r in ln["_refs"])]
    dropped = [ln for ln in lines if id(ln) not in {id(s) for s in smt}]

    write_bom(FULL_OUT, lines)
    write_bom(SMT_OUT, smt)

    print(f"Wrote:\n  {FULL_OUT} ({len(lines)} lines, {sum(l['_qty'] for l in lines)} placements)")
    print(f"  {SMT_OUT} ({len(smt)} lines, {sum(l['_qty'] for l in smt)} placements)")

    if never_looked_up:
        print(
            f"\nwarning: {len(never_looked_up)} MPN(s) have never been looked up "
            f"({', '.join(sorted(set(never_looked_up)))}).\n"
            "         Run scripts/lookup_lcsc.py before ordering.",
            file=sys.stderr,
        )

    if args.quiet:
        return

    if dnp:
        print("\nDNP in KiCad, omitted from both BOMs:")
        for ln in dnp:
            print(f"  {ln['Designator']:<12} {ln['Comment']} {ln['MPN']}")

    if dropped:
        print("\nHand-solder / mechanical, in the full BOM only:")
        for ln in dropped:
            why = next(HAND_SOLDER[r] for r in ln["_refs"] if r in HAND_SOLDER)
            print(f"  {ln['Designator']:<12} {ln['Comment']:<26} {why}")

    counts = {}
    for ln in lines:
        if ln["LCSC Part #"]:
            counts[ln["_class"] or "?"] = counts.get(ln["_class"] or "?", 0) + 1
    matched = sum(counts.values())
    print(f"\nLCSC coverage: {matched}/{len(lines)} lines matched "
          f"({', '.join(f'{v} {k}' for k, v in sorted(counts.items()))})")

    if no_part:
        print("\nNo purchased part at all (nothing for JLCPCB to source):")
        for ln in no_part:
            print(f"  {ln['Designator']:<12} {ln['Comment']:<12} {ln['Footprint']}")

    low = [ln for ln in lines if ln["LCSC Part #"] and ln["_stock"].isdigit()
           and int(ln["_stock"]) < 20 * ln["_qty"]]
    if low:
        print("\nStock tight relative to per-board quantity (index snapshot, confirm live):")
        for ln in low:
            print(f"  {ln['Designator']:<12} {ln['MPN']:<22} {ln['LCSC Part #']:<10} "
                  f"stock {ln['_stock']} for {ln['_qty']}/board")

    if unmatched:
        print(f"\nNo JLCPCB part ({len(unmatched)} lines) - each needs a decision:")
        for ln in unmatched:
            print(f"  {ln['Designator']:<12} {ln['Comment']:<12} {ln['MPN']:<22} {ln['Footprint']}")
            if ln["_candidates"]:
                print(f"      JLC stocks (unverified): {ln['_candidates'][:120]}")


if __name__ == "__main__":
    main()
