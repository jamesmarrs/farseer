#!/usr/bin/env python3
"""First-pass component placement for farseer.kicad_pcb, grouped by
schematic sheet.

Uses KiCad's own pcbnew API: footprints are moved with FOOTPRINT.SetPosition,
which relocates the entire footprint (pads, silkscreen, courtyard, texts) as
one atomic object, and the board is re-saved by KiCad's native serializer.

Run with KiCad's bundled Python, with the PCB editor CLOSED:

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/\
Versions/Current/bin/python3 scripts/place_pcb.py
"""

import os
import sys

import pcbnew

PCB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "ki_cad_project/farseer/farseer.kicad_pcb")

# ---------------------------------------------------------------------------
# Zones by source schematic sheet. Coordinates in mm, +y is down.
# ANCHORS pin the big parts; everything else auto-packs into rows below its
# sheet's FLOW origin using real courtyard/bounding-box sizes (no overlaps).
# ---------------------------------------------------------------------------

ANCHORS = {
    # power entry (top-left), left -> right
    # NOTE: J2 solder-wire footprint extends ~26 mm right of its origin
    "J2": (32, 33), "F1": (67, 33), "D2": (80, 33), "L1": (91, 33),
    "C7": (102, 33), "Q1": (110, 33), "D1": (116, 33),
    # 3v3_cell buck (feeds the cellular zone below it)
    "U3": (52, 52), "L3": (63, 52), "D4": (72, 52),
    # 3v3_sys buck (feeds the MCU zone)
    "U2": (96, 52), "L2": (103, 52), "D3": (110, 52),
    # cellular
    "J5": (78, 95), "J6": (112, 108), "U9": (100, 80), "D6": (60, 114),
    # MCU
    "U1": (130, 62), "J1": (116, 44), "JP1": (136, 44),
    # GPS (SMA at edge, short RF path)
    "J3": (161, 37), "U4": (148, 42),
    # USB-C
    "J4": (152, 120), "U7": (152, 107), "U6": (141, 107),
    # mounting holes and fiducials
    "H1": (24, 25), "H2": (172, 25), "H3": (40, 126), "H4": (172, 126),
    "FID1": (68, 25), "FID2": (120, 25), "FID3": (46, 121),
}

# Keep the Mini PCIe latch at its exact original offset from the socket.
RELATIVE_TO = {"MP1": "J5"}

# Per-sheet row-packing origin (x, y) and max row width in mm.
FLOW = {
    "power_protection.kicad_sch": (70, 43, 45),
    "3v3_cell.kicad_sch":         (44, 58, 40),  # keep above Mini PCIe card top (y=66.5)
    "3v3_sys.kicad_sch":          (96, 57, 24),
    "cellular.kicad_sch":         (96, 84, 30),
    "farseer.kicad_sch":          (139, 56, 16),
    "gps.kicad_sch":              (156, 52, 18),
    "usb_c.kicad_sch":            (128, 92, 34),
}
GAP = 0.8  # clearance between packed parts, mm


def mm(v):
    return pcbnew.FromMM(v)


def fp_size(fp):
    """Courtyard-ish footprint size in mm (bounding box without text)."""
    try:
        bb = fp.GetBoundingBox(False)          # KiCad 9/10: exclude text
    except TypeError:
        bb = fp.GetBoundingBox(False, False)   # older signature
    return pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())


def main():
    board = pcbnew.LoadBoard(PCB)
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    sheets = {ref: os.path.basename(fp.GetSheetfile()) for ref, fp in fps.items()}

    targets = {}
    for ref, (x, y) in ANCHORS.items():
        if ref in fps:
            targets[ref] = (x, y)
        else:
            print(f"WARNING: anchor {ref} not on board")
    for ref, parent in RELATIVE_TO.items():
        if ref in fps and parent in targets:
            d = fps[ref].GetPosition() - fps[parent].GetPosition()
            px, py = targets[parent]
            targets[ref] = (px + pcbnew.ToMM(d.x), py + pcbnew.ToMM(d.y))

    # Row-pack the remaining parts per sheet using real footprint sizes.
    for sheet, (ox, oy, max_w) in FLOW.items():
        rest = sorted(r for r in fps if sheets[r] == sheet and r not in targets)
        x, y, row_h = ox, oy, 0.0
        for ref in rest:
            w, h = fp_size(ref and fps[ref])
            w, h = w + GAP, h + GAP
            if x + w > ox + max_w and x > ox:
                x, y, row_h = ox, y + row_h, 0.0
            targets[ref] = (x + w / 2, y + h / 2)
            x += w
            row_h = max(row_h, h)

    unplaced = [r for r in fps if r not in targets]
    if unplaced:
        print(f"WARNING: no zone for {unplaced}, left in place")

    for ref, (x, y) in targets.items():
        fps[ref].SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))

    # Pull any Reference/Value label stranded far from its part back home.
    fixed = 0
    for fp in board.GetFootprints():
        for txt, home_y in ((fp.Reference(), -3), (fp.Value(), 3)):
            off = txt.GetFPRelativePosition()
            if max(abs(pcbnew.ToMM(off.x)), abs(pcbnew.ToMM(off.y))) > 12:
                txt.SetFPRelativePosition(pcbnew.VECTOR2I(0, mm(home_y)))
                fixed += 1
    if fixed:
        print(f"Reset {fixed} stranded labels.")

    pcbnew.SaveBoard(PCB, board)
    print(f"Placed {len(targets)} of {len(fps)} footprints. Saved {PCB}")


if __name__ == "__main__":
    sys.exit(main())
