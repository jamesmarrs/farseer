#!/usr/bin/env python3
"""Write the controlled-impedance spec JLCPCB needs at order time.

Reads the numbers from the KiCad project rather than hard-coding them, so the
spec cannot drift from the board:

  - trace width      RF_IN netclass track_width in farseer.kicad_pro
  - gap to ground    GNSS_RF_CPW clearance constraint in farseer.kicad_dru
  - stackup          (stackup ...) block in farseer.kicad_pcb

Output: docs/generated/farseer-impedance-spec.txt. Called by export_kicad.sh;
never hand-edit the output.
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRJ = os.path.join(REPO, "ki_cad_project", "farseer")
OUT = os.path.join(REPO, "docs", "generated", "farseer-impedance-spec.txt")

NET = "/GPS/GNSS_RF_IN"
NETCLASS = "RF_IN"
RULE = "GNSS_RF_CPW"
STACKUP_NAME = "JLC04161H-7628"


def netclass_width():
    pro = json.load(open(os.path.join(PRJ, "farseer.kicad_pro")))
    for nc in pro["net_settings"]["classes"]:
        if nc["name"] == NETCLASS:
            return float(nc["track_width"])
    sys.exit(f"netclass {NETCLASS} not found")


def rule_gap():
    dru = open(os.path.join(PRJ, "farseer.kicad_dru")).read()
    m = re.search(r"\(rule\s+" + RULE + r".*?\(constraint clearance \(min ([\d.]+)mm\)\)", dru, re.S)
    if not m:
        sys.exit(f"rule {RULE} not found in farseer.kicad_dru")
    return float(m.group(1))


def stackup():
    pcb = open(os.path.join(PRJ, "farseer.kicad_pcb")).read()
    blk = pcb[pcb.find("(stackup"):pcb.find("(copper_finish")]
    rows = []
    for m in re.finditer(r'\(layer "([^"]+)"\s*\(type "([^"]+)"\)(?:\s*\(thickness ([\d.]+)\))?'
                         r'(?:\s*\(material "([^"]+)"\))?(?:\s*\(epsilon_r ([\d.]+)\))?', blk):
        name, typ, th, mat, er = m.groups()
        if typ in ("copper", "prepreg", "core"):
            rows.append((name, typ, th, mat or "", er or ""))
    if not any(STACKUP_NAME in r[3] for r in rows):
        sys.exit(f"stackup in farseer.kicad_pcb does not reference {STACKUP_NAME}")
    return rows


def main():
    w = netclass_width()
    s = rule_gap()
    rows = stackup()
    lines = [
        "FARSEER - CONTROLLED IMPEDANCE SPECIFICATION (generated, do not edit)",
        "",
        "Fab: JLCPCB, 4-layer, 1.6 mm. Select 'Impedance Control' = YES and the",
        f"stackup {STACKUP_NAME} at order time. The trace below is sized for this",
        "stackup only; JLC's default 4-layer build is NOT equivalent.",
        "",
        "Controlled net",
        f"  Net name              {NET}",
        "  Layer                 Top (F.Cu, L1)",
        "  Structure             Coplanar waveguide with ground (single-ended)",
        "  Reference plane       L2 (In1.Cu, GND)",
        f"  Trace width           {w:.2f} mm  (base width as drawn; apply your etch compensation)",
        f"  Gap to coplanar GND   {s:.2f} mm  (both sides, F.Cu GND pour)",
        "  Target impedance      50 ohm single-ended",
        "  Tolerance             +/-10 %",
        "  Frequency             1.56-1.61 GHz (GNSS L1 band)",
        "  Marking               text note on User.Comments beside the trace",
        "",
        "Stackup as drawn in farseer.kicad_pcb",
        "  layer            type      thickness  material / er",
    ]
    for name, typ, th, mat, er in rows:
        lines.append(f"  {name:16s} {typ:9s} {th or '':>8s}   {mat}{'  er ' + er if er else ''}")
    lines += [
        "",
        "Design basis: scripts/rf_impedance.py (field solve) and",
        "docs/gnss-support-circuit.md section 5 'ESD and layout'.",
        "",
    ]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(lines))
    print(f"  {OUT}")


if __name__ == "__main__":
    main()
