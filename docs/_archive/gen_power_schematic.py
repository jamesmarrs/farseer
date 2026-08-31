#!/usr/bin/env python3
"""Generate the farseer power-rail schematic (docs/power-rails-schematic.pdf).

FULL DETAILED schematic: every part in docs/power-supply-bom.md appears here,
so the drawing and the BOM correspond 1:1. To keep it readable we follow normal
schematic convention: only short REFERENCE DESIGNATORS are printed next to each
part; the component VALUES live in power-supply-bom.md. Rails are joined between
sheets by net-label tags (VBAT_IN / VSYS / 3V3_CELL / 3V3_SYS).

Architecture (BG95-M3 in Mini PCIe form factor):

  VBAT_IN (7-18 V) -> F1 -> Q1 rev-polarity P-FET -> D1 load-dump TVS
                   -> pi filter (C0/FB0/C2/C3) -> C1 bulk -> VSYS
  VSYS -> U2 TPS54560-Q1 buck -> 3V3_CELL -> BG95 Mini PCIe socket (J2) + SIM (J3)
  VSYS -> U3 LMR16006X  buck -> 3V3_SYS  -> PIC VTG + NEO-M9N

Both output rails are 3.3 V but come from independent converters, so a BG95 TX
burst cannot brown out the MCU/GPS. The Mini PCIe card carries its own VBAT
regulation + RF/BB decoupling internally; our board only supplies clean 3.3 V.

Renders with schemdraw's SVG backend; SVG -> PDF/PNG via build_schematics.sh.
Style and drawing helpers are shared with the other generators in
schematic_common.py.
"""
import schemdraw.elements as elm

from schematic_common import (BLUE, GREEN, GREY, RED, Sheet, new_drawing,
                              save)

d = new_drawing()
sh = Sheet(d)

note = sh.note
leader = sh.leader
shunt = sh.shunt
shunt_rc = sh.shunt_rc


# ============================================================================
note(10.0, 3.4, 'FARSEER POWER RAILS - detailed schematic', 'black')
note(10.0, 2.7, 'Reference designators shown; component values are in power-supply-bom.md', GREY)

# ============================================================================
# SHEET 1 - Front-end protection : VBAT_IN -> VSYS
# ============================================================================
note(-1.5, 1.4, '(1)  VEHICLE INPUT -> PROTECTION -> VSYS', BLUE, 'left')

d += (vin := elm.Dot(open=True).at((0, 0)))
note(-0.1, 0.7, 'VBAT_IN (J1)', 'black')
d += (f1 := elm.Fuse().right().at(vin.center).label('F1'))

# Q1 reverse-polarity P-FET as a block with S / D / G pins
d += (q1 := elm.Ic(pins=[elm.IcPin(name='S', side='left'),
                         elm.IcPin(name='D', side='right'),
                         elm.IcPin(name='G', side='bottom')],
                   w=1.8, h=1.4, plblsize=9).fill('#eef4ff').right().anchor('S').at(f1.end))
note(q1.center[0], 1.4, 'Q1  (rev-pol)', GREY)
# gate network: R1 gate->GND, Dz1 gate->source clamp
d += (gstub := elm.Line().down().at(q1.G).length(0.4))
d += (r1 := elm.Resistor().down().at(gstub.end).label('R1', 'right').color(GREY))
d += elm.Ground().at(r1.end)
d += elm.Line().left().at(gstub.end).tox(q1.S[0] - 0.3)
d += (dz := elm.Zener().up().toy(q1.S[1]).label('Dz1', 'left').color(GREY))
d += elm.Line().up().at(dz.end).toy(q1.S[1]).tox(q1.S[0])

# node after Q1: TVS, then pi filter
d += elm.Line().right().at(q1.D).length(0.5)
d += (na := elm.Dot())
shunt(na.center, elm.DiodeTVS(), 'D1', 'left').color(RED)
d += elm.Line().right().at(na.center).length(1.2)
d += (nc0 := elm.Dot())
shunt(nc0.center, elm.Capacitor(), 'C0')
d += (fb0 := elm.Inductor2().right().at(nc0.center).label('FB0').color(GREEN))
d += (vsys := elm.Dot())
note(vsys.center[0] + 0.1, 0.7, 'VSYS', 'black')
shunt(vsys.center, elm.Capacitor(), 'C2/C3')
d += elm.Line().right().at(vsys.center).length(1.4)
d += (nb := elm.Dot())
shunt(nb.center, elm.Capacitor(polar=True), 'C1')
d += elm.Line().right().at(nb.center).length(0.6)
d += elm.Tag().right().label('VSYS').color('black')


# ============================================================================
# Reusable buck output + feedback stage.
# Power path: BOOT/SW -> Cboot, catch diode, L -> Vout -> Cout -> out tag.
# Feedback divider hangs off Vout and connects back to the IC FB pin via a
# net-label (fbnet) so no wire has to cross the IC.
# ============================================================================
def buck_output(ic, lref, dref, coutref, outnet, outcolor,
                fbnet, rfb1ref, rfb2ref):
    # Switch node pushed well clear of the IC so the catch diode has its own gap.
    d.add(elm.Line().right().at(ic.SW).length(1.8))
    sw = elm.Dot(); d.add(sw)
    # Bootstrap cap from BOOT down to the switch node.
    d.add(elm.Line().right().at(ic.BOOT).length(1.8))
    bt = elm.Dot(); d.add(bt)
    d.add(elm.Capacitor().at(bt.center).to(sw.center).label('C_boot', 'right').color(GREY))
    # Catch diode: straight down from SW node to ground (freewheel).
    dd = elm.Diode().down().at(sw.center).length(1.8).reverse().label(dref, 'right').color(RED)
    d.add(dd); d.add(elm.Ground().at(dd.end))
    # Inductor SW -> Vout (long, so L / Cout / diode don't crowd).
    d.add(elm.Inductor2().right().at(sw.center).length(2.6).label(lref, 'top').color(GREEN))
    vo = elm.Dot(); d.add(vo)
    shunt(vo.center, elm.Capacitor(), coutref)
    # Run out to the rail tag.
    d.add(elm.Line().right().at(vo.center).length(2.8))
    vo2 = elm.Dot(); d.add(vo2)
    d.add(elm.Line().right().at(vo2.center).length(1.3))
    d.add(elm.Tag().right().label(outnet).color(outcolor))
    # Feedback divider hangs down from the rail; midpoint -> FB pin via net label.
    r1 = elm.Resistor().down().at(vo2.center).length(1.6).label(rfb1ref, 'right').color(GREY)
    d.add(r1)
    r2 = elm.Resistor().down().at(r1.end).length(1.6).label(rfb2ref, 'right').color(GREY)
    d.add(r2); d.add(elm.Ground().at(r2.end))
    d.add(elm.Dot().at(r1.end))
    d.add(elm.Line().left().at(r1.end).length(0.6))
    d.add(elm.Tag().left().label(fbnet).color(GREY))
    return vo


# ============================================================================
# SHEET 2 - Buck A : VSYS -> 3.3 V >=4 A (TPS54560-Q1)  -> 3V3_CELL
# ============================================================================
AY = -11.5
note(-1.5, AY + 4.8, '(2)  BUCK A  U2 TPS54560-Q1 :  VSYS -> 3.3 V (>=4 A, 2G-capable)  -> 3V3_CELL', RED, 'left')

d += (u2 := elm.Ic(pins=[elm.IcPin(name='VIN', side='left', slot='2/2'),
                         elm.IcPin(name='EN', side='left', slot='1/2'),
                         elm.IcPin(name='BOOT', side='right', slot='3/3'),
                         elm.IcPin(name='SW', side='right', slot='2/3'),
                         elm.IcPin(name='FB', side='right', slot='1/3'),
                         elm.IcPin(name='RT', side='bottom', slot='1/4'),
                         elm.IcPin(name='SS', side='bottom', slot='2/4'),
                         elm.IcPin(name='COMP', side='bottom', slot='3/4'),
                         elm.IcPin(name='GND', side='bottom', slot='4/4')],
                   w=3.4, h=3.0, pinspacing=1.3, leadlen=0.9,
                   plblsize=8).fill('#fff3e6').label('U2', 'center').right().anchor('VIN').at((5.5, AY)))

# VIN: Cin + VSYS tag
d += elm.Line().left().at(u2.VIN).length(1.6)
d += (av := elm.Dot())
shunt(av.center, elm.Capacitor(), 'C_inA', 'left')
d += elm.Line().left().at(av.center).length(0.9)
d += elm.Tag().left().label('VSYS').color('black')

# EN: pulldown + PIC GPIO tag
d += elm.Line().left().at(u2.EN).length(2.4)
d += (ae := elm.Dot())
shunt(ae.center, elm.Resistor(), 'R_enA', 'left')
d += elm.Line().left().at(ae.center).length(0.7)
d += elm.Tag().left().label('EN <- PIC GPIO').color(RED)

# Bottom small-signal pins: RT, SS, COMP + GND
d += elm.Ground().at(u2.GND)
shunt(u2.RT, elm.Resistor().length(1.4), 'R_rt', 'left')
shunt(u2.SS, elm.Capacitor().length(1.4), 'C_ss', 'right')
shunt_rc((u2.COMP[0], u2.COMP[1]), 'R_cmp', 'C_cmp')

# FB pin -> net label back to divider (routed down, clear of the catch diode)
d += elm.Line().right().at(u2.FB).length(0.5)
d += (fba := elm.Dot())
d += elm.Line().down().at(fba.center).length(0.7)
d += elm.Tag().down().label('FBA').color(GREY)

buck_output(u2, 'L1', 'D2', 'C_outA',
            '3V3_CELL', RED, 'FBA', 'R_fbA1', 'R_fbA2')


# ============================================================================
# SHEET 3 - Buck B : VSYS -> 3.3 V ~0.6 A (LMR16006X)  -> 3V3_SYS
# ============================================================================
BY = -23.5
note(-1.5, BY + 3.2, '(3)  BUCK B  U3 LMR16006X :  VSYS -> 3.3 V (~0.6 A)  -> 3V3_SYS   (comp + soft-start internal)', GREEN, 'left')

d += (u3 := elm.Ic(pins=[elm.IcPin(name='VIN', side='left', slot='2/2'),
                         elm.IcPin(name='EN', side='left', slot='1/2'),
                         elm.IcPin(name='BOOT', side='right', slot='3/3'),
                         elm.IcPin(name='SW', side='right', slot='2/3'),
                         elm.IcPin(name='FB', side='right', slot='1/3'),
                         elm.IcPin(name='GND', side='bottom', slot='1/1')],
                   w=3.4, h=3.0, pinspacing=1.3, leadlen=0.9,
                   plblsize=8).fill('#e9f9ee').label('U3', 'center').right().anchor('VIN').at((5.5, BY)))
d += elm.Ground().at(u3.GND)

# VIN: Cin + VSYS tag
d += elm.Line().left().at(u3.VIN).length(1.6)
d += (bv := elm.Dot())
shunt(bv.center, elm.Capacitor(), 'C_inB', 'left')
d += elm.Line().left().at(bv.center).length(0.9)
d += elm.Tag().left().label('VSYS').color('black')

# EN: float-to-enable. Short stub + down tag, with a leader to an explanatory
# note placed in the open space below the IC (clear of C_inB above).
d += elm.Line().left().at(u3.EN).length(0.9)
d += (be := elm.Dot())
d += elm.Line().down().at(be.center).length(0.6)
d += elm.Tag().down().label('EN').color(GREY)
leader((be.center[0], be.center[1] - 1.5),
       (be.center[0] + 0.4, be.center[1] - 3.0),
       'EN floats = ON.  Optional R_enB 100k -> VSYS,\nor a divider to set a custom UVLO.', 'right')

# FB pin -> net label back to divider (routed down, clear of the catch diode)
d += elm.Line().right().at(u3.FB).length(0.5)
d += (fbb := elm.Dot())
d += elm.Line().down().at(fbb.center).length(0.7)
d += elm.Tag().down().label('FBB').color(GREY)

buck_output(u3, 'L2', 'D3', 'C_outB',
            '3V3_SYS', GREEN, 'FBB', 'R_fbB1', 'R_fbB2')


# ============================================================================
# SHEET 4 - 3V3_CELL -> BG95-M3 Mini PCIe socket (J2) + SIM (J3)
# ============================================================================
CY = -33.0
note(-1.5, CY + 2.6, '(4)  3V3_CELL -> BG95-M3 MINI PCIe SOCKET', RED, 'left')

d += (bc := elm.Tag().at((0, CY)).left().label('3V3_CELL').color(RED))
d += elm.Line().right().at(bc.start).length(1.2)
d += (cc1 := elm.Dot())
shunt(cc1.center, elm.Capacitor(polar=True), 'C10/C11')
d += elm.Line().right().at(cc1.center).length(2.4)
d += (cc2 := elm.Dot())
shunt(cc2.center, elm.Capacitor(), 'C12/C13')
d += elm.Line().right().at(cc2.center).length(1.8)

d += (j2 := elm.Ic(pins=[elm.IcPin(name='3V3', side='left', slot='3/3'),
                         elm.IcPin(name='W_DIS', side='left', slot='2/3'),
                         elm.IcPin(name='PERST', side='left', slot='1/3'),
                         elm.IcPin(name='GND', side='bottom'),
                         elm.IcPin(name='UART_USB', side='right', slot='2/2'),
                         elm.IcPin(name='USIM', side='right', slot='1/2')],
                   w=3.4, h=3.0, pinspacing=1.2, leadlen=0.8,
                   plblsize=8).fill('#fdeaea').label('J2  Mini PCIe', 'center').right().anchor('3V3'))
d += elm.Ground().at(j2.GND)
note(j2.center[0], CY - 3.6, '3V3 = pins 2,39,41,52  |  USIM = 1.8 V', GREY)
# SIM holder tag off the USIM pin
d += elm.Line().right().at(j2.USIM).length(1.0)
d += elm.Tag().right().label('J3 SIM').color(GREY)

note(1.0, CY - 2.9,
     'Card is self-contained: on-card VBAT regulation, RF/BB decoupling + ferrite are INSIDE the module.\n'
     'The raw-module VBAT star network (ferrite + MLCC arrays + 2x TVS) is NOT built on our board.',
     GREY, 'left')


# ============================================================================
# SHEET 5 - 3V3_SYS -> PIC VTG + NEO-M9N
# ============================================================================
DY = -39.5
note(-1.5, DY + 1.9, '(5)  3V3_SYS -> PIC VTG + NEO-M9N  (ferrite-isolated GNSS branch)', GREEN, 'left')

d += (b3 := elm.Tag().at((0, DY)).left().label('3V3_SYS').color(GREEN))
d += elm.Line().right().at(b3.start).length(1.2)
d += (n3 := elm.Dot())

# PIC branch (up); decoupling hangs off the horizontal run (right of the riser)
# so the cap doesn't sit on top of the 3V3_SYS junction.
d += elm.Line().up().at(n3.center).toy(DY + 1.1)
d += (p0 := elm.Dot())
d += elm.Line().right().at(p0.center).length(1.3)
d += (pdec := elm.Dot())
shunt(pdec.center, elm.Capacitor(), 'C_pic', 'right')
d += elm.Line().right().at(pdec.center).length(1.6)
d += elm.Tag().right().label('PIC VTG').color(GREEN)

# NEO branch (down)
d += elm.Line().down().at(n3.center).toy(DY - 1.3)
d += (g0 := elm.Dot())
d += (fb2 := elm.Inductor2().right().at(g0.center).label('FB2', 'bottom').color(GREEN))
d += (g1 := elm.Dot())
shunt(g1.center, elm.Capacitor(), 'C_neo')
d += elm.Line().right().at(g1.center).length(1.2)
d += (g2 := elm.Dot())
shunt(g2.center, elm.Capacitor(), 'C_bkp')
d += elm.Line().right().at(g2.center).length(1.2)
d += elm.Tag().right().label('NEO VCC').color(GREEN)

# padding anchors so edge tags are not clipped
note(26.0, 3.4, '.', 'white')
note(26.0, -42.0, '.', 'white')

save(d, 'power-rails-schematic')
