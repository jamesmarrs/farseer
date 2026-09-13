#!/usr/bin/env python3
"""Apply the GNSS_RF_IN launch changes to the KiCad board with KiCad's own API.

Run with the Python bundled inside KiCad, not the system interpreter:

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
      scripts/apply_rf_tuning.py

What it does (all idempotent - re-running is a no-op once applied):

  1. J3 pin 1: 2.3 mm roundrect -> 2.05 mm circle, drill unchanged at 1.5 mm.
     Applied to the library footprint in farseer_footprints.pretty and to the
     placed instance on the board. The 2.05 mm figure is KiCad's own pin-1
     pad for the vertical members of this Amphenol family (901-144, 132134),
     same 1.5 mm hole; the Amphenol 132136 drawing specifies holes only.
  2. Rule area "J3_RF_ANTIPAD": 3.0 mm circle on In1.Cu + In2.Cu only, copper
     pour not allowed. Opens the plane antipad around the plated barrel from
     the 2.406 mm the clearance rule produces to 3.0 mm. F.Cu / B.Cu untouched.
  3. Two GND fence vias 1.4 mm along the trace from the pin, closing the gap
     before the existing fence starts at 3.6 mm.
  4. Fab note on User.Comments identifying the controlled-impedance trace.
  5. Refill all zones (pad shape and the rule area both move pour edges) and
     save.

Then run DRC:  kicad-cli pcb drc --severity-all --exit-code-violations \
                   ki_cad_project/farseer/farseer.kicad_pcb

Numbers come from scripts/rf_impedance.py; rationale is in
docs/gnss-support-circuit.md.
"""
import math
import os
import sys

try:
    import pcbnew
except ImportError:
    sys.exit("pcbnew not importable - run with KiCad's bundled python3 (see docstring)")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(REPO, "ki_cad_project", "farseer", "farseer.kicad_pcb")
FP_LIB = os.path.join(REPO, "ki_cad_project", "farseer_footprints.pretty")
FP_NAME = "SMA_Amphenol_901-143_Horizontal"

PAD_DIA_MM = 2.05
ANTIPAD_DIA_MM = 3.0
ANTIPAD_NAME = "J3_RF_ANTIPAD"
VIA_ALONG_MM = 1.4        # from pin centre, along the trace (toward -x)
VIA_OFF_MM = 1.18         # off the trace axis; matches the existing fence
VIA_DIA_MM, VIA_DRILL_MM = 0.6, 0.3
FAB_NOTE = ("GNSS_RF_IN: 50R CPWG, W 0.34 / GAP 0.45, REF L2 (In1.Cu). "
            "CONTROLLED IMPEDANCE - STACKUP JLC04161H-7628")
PAD_NOTE = ("Pin 1 is deliberately the 2.05 mm circular pad from KiCad's "
            "SMA_Amphenol_901-144_Vertical (same 1.5 mm hole): it clears the "
            "L2/L3 antipad. Do not revert to the stock 2.3 mm roundrect.")

def mm(x):
    """mm -> integer nanometres. pcbnew.FromMM(2.05) yields 2049999; round instead."""
    return int(round(x * 1e6))


def set_pad_round(pad):
    if pad.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE and \
       pad.GetSize(pcbnew.F_Cu).x == mm(PAD_DIA_MM):
        return False
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.VECTOR2I(mm(PAD_DIA_MM), mm(PAD_DIA_MM)))
    return True


def update_library_footprint():
    fp = pcbnew.FootprintLoad(FP_LIB, FP_NAME)
    if fp is None:
        sys.exit(f"footprint {FP_NAME} not found in {FP_LIB}")
    changed = set_pad_round(fp.FindPadByNumber("1"))
    descr = fp.GetLibDescription()
    if PAD_NOTE not in descr:
        fp.SetLibDescription(descr.rstrip() + " " + PAD_NOTE)
        changed = True
    if changed:
        pcbnew.FootprintSave(FP_LIB, fp)
    return changed


def update_board_footprint(board):
    j3 = board.FindFootprintByReference("J3")
    if j3 is None:
        sys.exit("J3 not found on board")
    changed = set_pad_round(j3.FindPadByNumber("1"))
    descr = j3.GetLibDescription()
    if PAD_NOTE not in descr:
        j3.SetLibDescription(descr.rstrip() + " " + PAD_NOTE)
        changed = True
    return j3, changed


def add_antipad(board, centre):
    for z in board.Zones():
        if z.GetIsRuleArea() and z.GetZoneName() == ANTIPAD_NAME:
            return False
    zone = pcbnew.ZONE(board)
    zone.SetIsRuleArea(True)
    zone.SetZoneName(ANTIPAD_NAME)
    zone.SetDoNotAllowZoneFills(True)
    zone.SetDoNotAllowTracks(False)
    zone.SetDoNotAllowVias(False)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowFootprints(False)
    layers = pcbnew.LSET()
    layers.addLayer(pcbnew.In1_Cu)
    layers.addLayer(pcbnew.In2_Cu)
    zone.SetLayerSet(layers)
    outline = zone.Outline()
    outline.NewOutline()
    r = mm(ANTIPAD_DIA_MM / 2)
    n = 72
    for i in range(n):
        a = 2 * math.pi * i / n
        outline.Append(int(round(centre.x + r * math.cos(a))),
                       int(round(centre.y + r * math.sin(a))))
    board.Add(zone)
    return True


def add_fence_vias(board, centre, gnd):
    targets = [pcbnew.VECTOR2I(centre.x - mm(VIA_ALONG_MM), centre.y - mm(VIA_OFF_MM)),
               pcbnew.VECTOR2I(centre.x - mm(VIA_ALONG_MM), centre.y + mm(VIA_OFF_MM))]
    existing = [t.GetPosition() for t in board.Tracks() if t.Type() == pcbnew.PCB_VIA_T]
    added = 0
    for pos in targets:
        if any((e - pos).EuclideanNorm() < mm(0.05) for e in existing):
            continue
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pos)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetWidth(mm(VIA_DIA_MM))
        via.SetDrill(mm(VIA_DRILL_MM))
        via.SetNetCode(gnd)
        board.Add(via)
        added += 1
    return added


def add_fab_note(board, centre):
    for d in board.Drawings():
        if d.Type() == pcbnew.PCB_TEXT_T and d.GetText() == FAB_NOTE:
            return False
    t = pcbnew.PCB_TEXT(board)
    t.SetText(FAB_NOTE)
    t.SetLayer(pcbnew.Cmts_User)
    t.SetTextSize(pcbnew.VECTOR2I(mm(0.7), mm(0.7)))
    t.SetTextThickness(mm(0.1))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    # just above the straight run of the trace, clear of the via fence
    t.SetPosition(pcbnew.VECTOR2I(centre.x - mm(2.0), centre.y - mm(3.2)))
    board.Add(t)
    return True


def main():
    lib_changed = update_library_footprint()
    print(f"library footprint {FP_NAME}: {'updated' if lib_changed else 'already up to date'}")

    board = pcbnew.LoadBoard(BOARD)
    j3, fp_changed = update_board_footprint(board)
    pin1 = j3.FindPadByNumber("1").GetPosition()
    gnd = board.GetNetcodeFromNetname("GND")

    ap = add_antipad(board, pin1)
    nv = add_fence_vias(board, pin1, gnd)
    fn = add_fab_note(board, pin1)
    print(f"J3 pin 1 on board: {'updated' if fp_changed else 'already round'}")
    print(f"rule area {ANTIPAD_NAME}: {'added' if ap else 'present'}")
    print(f"fence vias: {nv} added")
    print(f"fab note: {'added' if fn else 'present'}")

    if fp_changed or ap or nv or fn:
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
        pcbnew.SaveBoard(BOARD, board)
        print(f"zones refilled, saved {os.path.relpath(BOARD, REPO)}")
    else:
        print("nothing to do")


if __name__ == "__main__":
    main()
