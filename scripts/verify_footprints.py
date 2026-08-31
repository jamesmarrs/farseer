#!/usr/bin/env python3
"""Read-only check of the swapped footprints (run with KiCad's bundled python3)."""
import pcbnew

board = pcbnew.LoadBoard("/Users/james/motorsports/projects/farseer/ki_cad_project/farseer/farseer.kicad_pcb")
for ref in ["U2", "U3", "F1", "Q1", "J5"]:
    fp = board.FindFootprintByReference(ref)
    print(ref, fp.GetFPID().GetUniStringLibId(), "pos", fp.GetPosition(), "rot", fp.GetOrientation().AsDegrees())
    for pad in fp.Pads():
        print("   pad", pad.GetNumber(), "->", pad.GetNetname())
