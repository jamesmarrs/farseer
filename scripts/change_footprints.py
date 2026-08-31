#!/usr/bin/env python3
"""One-shot footprint swap to official KiCad libraries (run with KiCad's bundled python3).

Equivalent of Pcbnew's "Change Footprint" for U2, U3, F1, Q1: keeps position,
orientation, side, reference/value, schematic path link, and pad nets.
"""
import sys

import pcbnew

BOARD = "/Users/james/motorsports/projects/farseer/ki_cad_project/farseer/farseer.kicad_pcb"
FP_ROOT = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"

# ref -> (library.pretty, footprint name, extra pad -> source pad number for net)
SWAPS = {
    "U2": ("Package_TO_SOT_SMD", "TSOT-23-6", {}),
    "U3": ("Package_SO", "SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.95x4.9mm_Mask2.71x3.4mm_ThermalVias", {}),
    "F1": ("Fuse", "Fuseholder_Blade_Mini_Keystone_3568", {}),
    # PowerDI3333-8: pads 1-3 source, 4 gate, 5 merged drain tab.
    # extra is empty: Q1 is already this land; same-number pad nets must
    # not be remapped (the Type-F map 1/2/3<-4, 4<-3, 5<-1 was one-shot).
    "Q1": ("Package_SON", "Diodes_PowerDI3333-8", {}),
}

board = pcbnew.LoadBoard(BOARD)

todo = [sys.argv[1]] if len(sys.argv) > 1 else list(SWAPS)
for ref in todo:
    lib, name, extra = SWAPS[ref]
    old = board.FindFootprintByReference(ref)
    if old is None:
        sys.exit(f"ERROR: {ref} not found on board")

    io = pcbnew.PCB_IO_KICAD_SEXPR()
    new = io.FootprintLoad(f"{FP_ROOT}/{lib}.pretty", name)
    if new is None:
        sys.exit(f"ERROR: could not load {lib}:{name}")

    net_by_pad = {}
    for pad in old.Pads():
        net_by_pad.setdefault(pad.GetNumber(), pad.GetNet())

    flipped = old.IsFlipped()
    new.SetParent(board)
    board.Add(new)
    if flipped:
        new.Flip(old.GetPosition(), False)
    new.SetPosition(old.GetPosition())
    new.SetOrientation(old.GetOrientation())
    new.SetReference(ref)
    new.SetValue(old.GetValue())
    new.SetPath(old.GetPath())
    new.SetAttributes(old.GetAttributes())
    new.Reference().SetPosition(old.Reference().GetPosition())
    new.Value().SetPosition(old.Value().GetPosition())

    unmatched = []
    for pad in new.Pads():
        num = pad.GetNumber()
        src = extra.get(num, num)
        if src in net_by_pad:
            pad.SetNet(net_by_pad[src])
        else:
            unmatched.append(num)
    if unmatched:
        print(f"WARNING {ref}: pads with no net source: {unmatched}")

    board.Remove(old)
    print(f"{ref}: -> {lib}:{name} at {new.GetPosition()} rot {new.GetOrientation().AsDegrees()} flipped={flipped}")

pcbnew.SaveBoard(BOARD, board)
print("Saved", BOARD)
