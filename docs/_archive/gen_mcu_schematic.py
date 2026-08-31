#!/usr/bin/env python3
"""Generate the PIC18F57Q84 support schematic (docs/mcu-schematic.pdf).

Every part in docs/mcu-bom.md appears here with its VALUE printed next to the
reference designator, so the drawing is self-contained for bring-up. The BOM
remains the source of truth for MPN / status / cost.

Sheets:
  (1) U1 pinout as wired - all connected pins with 48-pin TQFP pin numbers
  (2) Supply and decoupling - one 0.1 uF per VDD pin, plus the tank cap
  (3) MCLR reset network (DS40002213F Figure 4-1) with the C_mclr lift jumper
  (4) ICSP program + debug header for a PICkit 5, Microchip PICkit pinout
  (5) USB-C debug console - CP2102N presenting a CDC virtual COM port
  (6) Status LED on RF3, and the deliberately empty clock circuit

Package warning: every pin number is the 48-pin TQFP column of Table 3-2 /
Figure 2-7. Numbers from the 28/40-pin parts do not apply.

Renders with schemdraw's SVG backend; SVG -> PDF/PNG via build_schematics.sh.
"""
import schemdraw.elements as elm

from schematic_common import (AMBER, BLUE, FILL_CONN, FILL_MCU, GREEN, GREY,
                              RED, Sheet, new_drawing, part_lbl, save)

d = new_drawing()
sh = Sheet(d)

TITLE_Y = 5.0
sh.body(TITLE_Y, 'FARSEER MCU SUPPORT CIRCUIT  -  PIC18F57Q84, 48-pin TQFP', 'black')
sh.body(TITLE_Y - 0.8,
        'Every resistor and capacitor shows its VALUE next to the reference designator. '
        'MPN / status / cost: mcu-bom.md')
sh.body(TITLE_Y - 1.5, 'All pin numbers are the 48-pin TQFP column (DS40002213F Figure 2-7 / Table 3-2)')

# ============================================================================
# SHEET 1 - U1 as wired
# ============================================================================
sh.banner(1.6, '(1)  U1  PIC18F57Q84-I/PT  :  every connected pin', AMBER)

# Right-hand signal pins, top to bottom: (anchor, pin no., net, peer, colour)
SIGNALS = [
    ('RF0', '36', 'DBG_TX', 'to U5 RXD  -  console TX  (U1TX)', AMBER),
    ('RF1', '37', 'DBG_RX', 'from U5 TXD  -  console RX  (U1RX)', AMBER),
    ('RD0', '42', 'GNSS_RX', 'to NEO-M9N pin 21 RXD  (U2TX)', GREEN),
    ('RD1', '43', 'GNSS_TX', 'from NEO-M9N pin 20 TXD  (U2RX)', GREEN),
    ('RB3', '11', 'GNSS_RESET', 'to NEO-M9N pin 8 RESET_N, open-drain', GREEN),
    ('RC2', '40', 'GNSS_1PPS', 'from NEO-M9N pin 3 TIMEPULSE  (CCP1 capture)', GREEN),
    ('RF4', '12', 'CELL_RX', 'to J2 pin 11 UART_RX  (U3TX)', RED),
    ('RF5', '13', 'CELL_TX', 'from J2 pin 13 UART_TX  (U3RX)', RED),
    ('RF6', '14', 'CELL_CTS', 'from J2 pin 25 UART_RTS  (U3CTS, Opt)', RED),
    ('RF7', '15', 'CELL_RTS', 'to J2 pin 23 UART_CTS  (U3RTS, Opt)', RED),
    ('RB0', '8', 'CELL_PERST', 'to J2 pin 22 PERST#, open-drain', RED),
    ('RB1', '9', 'CELL_W_DIS', 'to J2 pin 20 W_DISABLE#  (Opt)', RED),
    ('RB2', '10', 'CELL_RI', 'from J2 pin 17 RI  (INT2, Opt)', RED),
    ('RA2', '23', 'CELL_PWR_EN', 'to buck A EN  -  HIGH = rail on', RED),
    ('RB6', '18', 'ICSPCLK', 'to J_icsp pin 5  -  keep clear of everything else', BLUE),
    ('RB7', '19', 'ICSPDAT', 'to J_icsp pin 4  -  keep clear of everything else', BLUE),
    ('RF3', '39', 'LED0', 'status LED, drives low to light', AMBER),
]
n = len(SIGNALS)

pins = [elm.IcPin(name='VDD', pin='7', side='left', slot='5/5'),
        elm.IcPin(name='VDD', pin='30', side='left', slot='4/5', anchorname='VDDb'),
        elm.IcPin(name='VSS', pin='6', side='left', slot='3/5'),
        elm.IcPin(name='VSS', pin='31', side='left', slot='2/5', anchorname='VSSb'),
        elm.IcPin(name='MCLR', pin='20', side='left', slot='1/5')]
pins += [elm.IcPin(name=a, pin=p, side='right', slot=f'{n - i}/{n}')
         for i, (a, p, _, _, _) in enumerate(SIGNALS)]

d += (u1 := elm.Ic(pins=pins, w=6.4, h=15.0, pinspacing=0.9, leadlen=1.1,
                   plblsize=8)
      .fill(FILL_MCU).label('U1   PIC18F57Q84-I/PT   48-pin TQFP', 'top')
      .right().anchor('VDD').at((3.0, -1.6)))

NOTE_X = u1.RF0[0] + 4.4   # flush column for the peer descriptions

for anchor in ('VDD', 'VDDb'):
    sh.net(getattr(u1, anchor), 'left', '3V3_SYS', GREEN, stub=1.2)
for anchor in ('VSS', 'VSSb'):
    d += (gl := elm.Line().left().at(getattr(u1, anchor)).length(0.8))
    d += elm.Ground().at(gl.end)
sh.net(u1.MCLR, 'left', 'MCLR_N', BLUE, stub=1.2)

for anchor, _, net, peer, color in SIGNALS:
    sh.net(getattr(u1, anchor), 'right', net, color, stub=0.8,
           note=peer, note_x=NOTE_X)

sh.body(-19.0,
        'No AVDD / AVSS and no VCAP on this device, so ADC quality depends entirely on how clean 3V3_SYS is at\n'
        'pins 7 and 30 - there is no analog supply to filter separately, and VREF is not a dedicated pin (it would\n'
        'cost RA2 / RA3). Unused I/O: drive low in firmware (DS40002213F 4.6) or tie to VSS through 1-10 kOhm.')

# ============================================================================
# SHEET 2 - Supply and decoupling
# ============================================================================
PY = -24.0
sh.banner(PY + 2.4, '(2)  SUPPLY AND DECOUPLING  :  0.1 uF per VDD pin, REQUIRED (DS40002213F 4.2.1)', GREEN)

d += (pt := elm.Tag(width=1.9).at((0, PY)).left().label('3V3_SYS').color(GREEN))
d += elm.Line().right().at(pt.start).length(1.4)
d += (pb := elm.Dot())
sh.shunt(pb.center, elm.Capacitor(), 'C_picBulk', value='4.7 uF / 16 V X7R')
d += elm.Line().right().at(pb.center).length(3.0)
d += (pd1 := elm.Dot())
sh.shunt(pd1.center, elm.Capacitor(), 'C_pic1', value='0.1 uF X7R')
d += elm.Line().right().at(pd1.center).length(3.0)
d += (pd2 := elm.Dot())
sh.shunt(pd2.center, elm.Capacitor(), 'C_pic2', value='0.1 uF X7R')
d += elm.Line().right().at(pd2.center).length(3.0)
d += (pd3 := elm.Dot())
sh.shunt(pd3.center, elm.Capacitor(), 'C_picHF1/2', value='1 nF (Opt, DNP)')
d += elm.Line().right().at(pd3.center).length(1.2)
sh.net(pd3.center, 'right', 'U1 VDD', GREEN, stub=1.2)

sh.note(pd1.center[0], PY - 3.4, 'VDD 7 / VSS 6', GREY)
sh.note(pd2.center[0], PY - 3.4, 'VDD 30 / VSS 31', GREY)
sh.note(pd3.center[0], PY - 3.4, 'only if HF noise\nis observed', GREY)

sh.body(PY - 4.8,
        'Pins 7/6 and 30/31 sit on OPPOSITE CORNERS of the package, so these are two genuinely separate placements -\n'
        'one shared cap is not compliant. Each cap: ceramic, self-resonant at 200 MHz or above, same side of the board\n'
        'as the MCU, trace no longer than 6 mm, and power routed to the CAP FIRST and then on to the device pin.')

# ============================================================================
# SHEET 3 - MCLR network
# ============================================================================
MY = -33.0
sh.banner(MY + 3.2, '(3)  MCLR RESET NETWORK  (DS40002213F Figure 4-1)', BLUE)

d += (mt := elm.Tag(width=1.9).at((0, MY + 2.2)).left().label('3V3_SYS').color(GREEN))
d += elm.Line().right().at(mt.start).length(1.4)
d += (mr := elm.Resistor().down().at((mt.start[0] + 1.4, MY + 2.2)).length(1.8)
      .label(part_lbl('R_mclr1', '10 kOhm'), 'left').color(GREY))
d += (mnode := elm.Dot().at(mr.end))
d += (ms := elm.Resistor().right().at(mnode.center).length(2.6)
      .label(part_lbl('R_mclr2', '220 Ohm'), 'top').color(GREY))
sh.net(ms.end, 'right', 'MCLR_N', BLUE, stub=0.9)
sh.note(ms.end[0] + 3.6, MY + 0.4, 'to U1 pin 20 (RE3 / VPP)', GREY, 'right')

d += (mc := elm.Capacitor().down().at(mnode.center).length(1.7)
      .label(part_lbl('C_mclr', '0.1 uF'), 'left').color(GREY))
d += (mj := elm.Switch().down().at(mc.end).length(1.5)
      .label('JP_mclr\n(lift C_mclr)', 'left').color(GREY))
d += elm.Ground().at(mj.end)
sh.leader((mj.center[0] + 0.25, mj.center[1]),
          (mj.center[0] + 2.4, mj.center[1] - 0.8),
          'Lift C_mclr here if the programmer objects to the RC (Figure 4-2).\n'
          'A no-fit pad on C_mclr does the same job for free.', 'right')

sh.body(MY - 4.6,
        'All three parts within 6 mm of pin 20 (4.3). R_mclr1 <= 10 kOhm and R_mclr2 <= 470 Ohm are datasheet limits,\n'
        'not suggestions: R_mclr2 caps the current C_mclr can dump into MCLR during an ESD/EOS breakdown. The Curiosity\n'
        'Nano fits 47 kOhm and no capacitor, which violates R1 <= 10 kOhm - follow the datasheet, not the dev board.')

# ============================================================================
# SHEET 4 - ICSP header
# ============================================================================
IY = -44.0
sh.banner(IY + 3.6, '(4)  ICSP PROGRAM + DEBUG HEADER  -  PICkit 5  (Microchip PICkit pinout, Figures 48-1 / 48-2)', BLUE)

d += (jicsp := elm.Ic(pins=[elm.IcPin(name='VPP', pin='1', side='right', slot='6/6'),
                            elm.IcPin(name='VDD_T', pin='2', side='right', slot='5/6'),
                            elm.IcPin(name='VSS', pin='3', side='right', slot='4/6'),
                            elm.IcPin(name='PGD', pin='4', side='right', slot='3/6'),
                            elm.IcPin(name='PGC', pin='5', side='right', slot='2/6'),
                            elm.IcPin(name='NC', pin='6', side='right', slot='1/6')],
                      w=3.0, h=13.5, pinspacing=2.2, leadlen=1.1, plblsize=8)
      .fill(FILL_CONN).label('J_icsp   6-pin 0.1 in header', 'top')
      .right().anchor('VPP').at((1.0, IY)))

sh.net(jicsp.VPP, 'right', 'MCLR_N', BLUE, stub=3.4)
sh.net(jicsp.VDD_T, 'right', '3V3_SYS', GREEN, stub=3.4)
sh.leader((jicsp.VDD_T[0] + 3.4, jicsp.VDD_T[1]),
          (jicsp.VDD_T[0] + 8.6, jicsp.VDD_T[1] + 1.6),
          'SENSE ONLY - leave "Power target circuit from tool" OFF in MPLAB.\n'
          'The board runs the NEO-M9N, two bucks and a 2.7 A BG95 card; the\n'
          'PICkit cannot supply it, and reports a target-voltage error if asked.',
          'right')
sh.note(jicsp.VPP[0] - 2.6, jicsp.VPP[1] + 1.1,
        'pin 1: square pad + silkscreen triangle\n(the header is unkeyed)', GREY,
        'right')
d += (ig := elm.Line().right().at(jicsp.VSS).length(0.7))
d += elm.Ground().at(ig.end)

# The two pull-down nodes are staggered in x, and the lower row carries its
# series-R label underneath, so nothing lands on the row above's ground symbol.
for anchor, rref, pdref, net, peer, rlen, rloc in (
        ('PGD', 'R_icsp1', 'R_icspPD1', 'ICSPDAT', 'to U1 RB7, pin 19', 2.2, 'top'),
        ('PGC', 'R_icsp2', 'R_icspPD2', 'ICSPCLK', 'to U1 RB6, pin 18', 4.0, 'bottom')):
    src = getattr(jicsp, anchor)
    d += (r := elm.Resistor().right().at(src).length(rlen)
          .label(part_lbl(rref, '47 Ohm (Opt)'), rloc).color(GREY))
    d += (nd := elm.Dot().at(r.end))
    sh.shunt(nd.center, elm.Resistor().length(1.2), pdref, 'right', value='47 kOhm')
    sh.net(nd.center, 'right', net, BLUE, stub=1.2,
           note=peer, note_x=jicsp.PGD[0] + 10.2)

sh.note(jicsp.NC[0] + 0.4, jicsp.NC[1], 'no connect', GREY, 'right')

sh.body(IY - 15.5,
        'DS40002213F 4.4 is emphatic about what NOT to add: no pull-UPS, series diodes, or capacitors on ICSPCLK /\n'
        'ICSPDAT - they interfere with programmer communications. R_icsp1/2 are ESD series only and must not exceed\n'
        '100 Ohm; the 47 kOhm pull-DOWNS are what Microchip debug tooling expects. Nothing else may share RB6 / RB7.')
sh.body(IY - 19.0,
        'THIS HEADER IS BOTH PROGRAMMER AND DEBUGGER, permanently, not a manufacturing fixture. The device offers\n'
        'In-Circuit Debug with three breakpoints over the SAME two pins (DS40002213F p. 6); MPLAB clears DEBUG\n'
        '(CONFIG7[5]) for a debug session and no board change is needed. JTAG is not an alternative - 39 states the\n'
        'PIC18-Q84 JTAG module does not support programming. Leave LVP (CONFIG4[5]) at its erased 1: clearing it\n'
        'forces high-voltage VPP entry from then on, and only HV programming can ever set it back.', BLUE)

# ============================================================================
# SHEET 5 - USB-C debug console
# ============================================================================
DY = -70.0
sh.banner(DY + 3.6,
          '(5)  DEBUG CONSOLE  -  USB-C to CP2102N-A02-GQFN24, CDC virtual COM port  (console half of the Curiosity Nano debugger, DS50003011 3.1.2)',
          AMBER)

d += (jdbg := elm.Ic(pins=[elm.IcPin(name='VBUS', pin='A4/B9', side='right', slot='7/7'),
                          elm.IcPin(name='D+', pin='A6/B6', side='right', slot='6/7'),
                          elm.IcPin(name='D-', pin='A7/B7', side='right', slot='5/7'),
                          elm.IcPin(name='CC1', pin='A5', side='right', slot='4/7'),
                          elm.IcPin(name='CC2', pin='B5', side='right', slot='3/7'),
                          elm.IcPin(name='GND', pin='A1/B12', side='right', slot='2/7'),
                          elm.IcPin(name='SHELL', pin='-', side='right', slot='1/7')],
                     w=3.2, h=21.0, pinspacing=3.0, leadlen=1.1, plblsize=8)
      .fill(FILL_CONN).label('J_dbg   USB-C, 16-pin, USB 2.0 only', 'top')
      .right().anchor('VBUS').at((1.0, DY)))

# D_dbg in the main path between J_dbg and U5. Every SOT-23-6 pin is shown and
# tied so the hookup is readable. Parallel ESD: pins 1+6 on D+, 3+4 on D-,
# pin 5 on raw VBUS, pin 2 on GND.
d += (ddbg := elm.Ic(pins=[
        elm.IcPin(name='IO1', pin='1', side='left', slot='6/6'),
        elm.IcPin(name='IO1b', pin='6', side='left', slot='5/6'),
        elm.IcPin(name='IO2', pin='3', side='left', slot='4/6'),
        elm.IcPin(name='IO2b', pin='4', side='left', slot='3/6'),
        elm.IcPin(name='VBUS', pin='5', side='left', slot='2/6'),
        elm.IcPin(name='GND', pin='2', side='left', slot='1/6')],
                     w=4.8, h=12.0, pinspacing=2.0, leadlen=1.1, plblsize=8)
      .fill(FILL_CONN).label('D_dbg   USBLC6-2SC6   SOT-23-6', 'top')
      .right().anchor('IO1').at((9.0, DY - 0.5)))

# J_dbg -> junctions -> into D_dbg (both pins of each I/O pair) and onward to U5.
d += (vb := elm.Line().right().at(jdbg.VBUS).length(1.8))
d += (vbn := elm.Dot())
sh.shunt(vbn.center, elm.Capacitor().length(1.3), 'C_dbg4', value='1 uF')
d += elm.Line().right().at(vbn.center).to(ddbg.VBUS)
d += (rv1 := elm.Resistor().up().at(vbn.center).length(2.2)
      .label(part_lbl('R_vbus1', '22.1 kOhm'), 'right').color(GREY))
d += (rv1h := elm.Line().right().at(rv1.end).length(2.4))
d += (vbd := elm.Dot().at(rv1h.end))
sh.shunt(vbd.center, elm.Resistor().length(1.3), 'R_vbus2', value='47.5 kOhm')
sh.net(vbd.center, 'right', 'VBUS_DET', AMBER, stub=1.0)
sh.leader((rv1h.center[0], rv1h.center[1] + 0.2),
          (rv1h.center[0] + 1.0, rv1h.center[1] + 1.8),
          'Divider REQUIRED (CP2102N 2.3): 22.1k/47.5k -> 3.41 V at U5 pin 8.\n'
          'D_dbg pin 5 clamps raw VBUS (this node), not VBUS_DET.', 'right')

d += (dpp := elm.Line().right().at(jdbg.__getattr__('D+')).length(1.8))
d += (dpn := elm.Dot())
d += elm.Line().right().at(dpn.center).to(ddbg.IO1)
d += elm.Line().at(dpn.center).to(ddbg.IO1b)
sh.net(dpn.center, 'up', 'USB_DP', AMBER, stub=0.9)

d += (dmp := elm.Line().right().at(jdbg.__getattr__('D-')).length(1.8))
d += (dmn := elm.Dot())
d += elm.Line().right().at(dmn.center).to(ddbg.IO2)
d += elm.Line().at(dmn.center).to(ddbg.IO2b)
sh.net(dmn.center, 'up', 'USB_DM', AMBER, stub=0.9)

d += (dg := elm.Line().left().at(ddbg.GND).length(0.9))
d += elm.Ground().at(dg.end)

sh.body(DY - 16.5,
        'D_dbg (USBLC6-2SC6) pin hookup - wire BOTH pins of each I/O pair:\n'
        '  pin 1  I/O1  -+\n'
        '  pin 6  I/O1  -+- USB_DP  =  J_dbg D+ (A6/B6)  =  U5 D+ (pin 3)\n'
        '  pin 3  I/O2  -+\n'
        '  pin 4  I/O2  -+- USB_DM  =  J_dbg D- (A7/B7)  =  U5 D- (pin 4)\n'
        '  pin 5  VBUS  ---- J_dbg VBUS (A4/B9)  ->  R_vbus1/R_vbus2  ->  VBUS_DET  ->  U5 VBUS (pin 8)\n'
        '  pin 2  GND   ---- GND')

# CC pull-downs: one per pin, never shared. 5.1 kOhm = USB-C Rd (UFP / sink).
for anchor, ref in (('CC1', 'R_cc1'), ('CC2', 'R_cc2')):
    d += (ln := elm.Line().right().at(getattr(jdbg, anchor)).length(1.2))
    sh.shunt(ln.end, elm.Resistor().length(1.3), ref, value='5.1 kOhm')

d += (jg := elm.Line().right().at(jdbg.GND).length(0.8))
d += elm.Ground().at(jg.end)

# Shell: RC to ground, so ESD has a path but the car chassis and a laptop do not
# share a DC ground.
d += (rs := elm.Resistor().right().at(jdbg.SHELL).length(2.8)
      .label(part_lbl('R_shield', '1 MOhm'), 'top').color(GREY))
d += (rsn := elm.Dot().at(rs.end))
d += elm.Ground().at(rsn.center)
d += (cs_stub := elm.Line().down().at(jdbg.SHELL).length(1.4))
d += (cs := elm.Capacitor().right().at(cs_stub.end).length(2.8)
      .label(part_lbl('C_shield', '4.7 nF / 2 kV'), 'bottom').color(GREY))
d += elm.Ground().at(cs.end)
sh.leader((rs.center[0], rs.center[1] - 0.3),
          (rs.center[0] + 3.4, rs.center[1] - 2.4),
          'R_shield || C_shield: ESD reaches ground,\n'
          'but the car chassis and the laptop share no DC path', 'right')

# Bridge — QFN24 pin numbers from CP2102N Table 5.2.
d += (u5 := elm.Ic(pins=[elm.IcPin(name='D+', pin='3', side='left', slot='6/6'),
                         elm.IcPin(name='D-', pin='4', side='left', slot='5/6'),
                         elm.IcPin(name='VBUS', pin='8', side='left', slot='4/6'),
                         elm.IcPin(name='VREGIN', pin='7', side='left', slot='3/6'),
                         elm.IcPin(name='VDD', pin='6', side='left', slot='2/6'),
                         elm.IcPin(name='VIO', pin='5', side='left', slot='1/6'),
                         elm.IcPin(name='RSTb', pin='9', side='right', slot='4/4'),
                         elm.IcPin(name='TXD', pin='21', side='right', slot='3/4'),
                         elm.IcPin(name='RXD', pin='20', side='right', slot='2/4'),
                         elm.IcPin(name='GND', pin='2', side='right', slot='1/4')],
                   w=5.4, h=11.0, pinspacing=2.2, leadlen=1.1, plblsize=8)
      .fill(FILL_MCU).label('U5   CP2102N-A02-GQFN24', 'top')
      .right().anchor('D+').at((18.5, DY - 1.0)))

sh.net(u5.__getattr__('D+'), 'left', 'USB_DP', AMBER, stub=1.2)
sh.net(u5.__getattr__('D-'), 'left', 'USB_DM', AMBER, stub=1.2)
sh.net(u5.VBUS, 'left', 'VBUS_DET', AMBER, stub=1.2)
d += (ug := elm.Line().right().at(u5.GND).length(0.8))
d += elm.Ground().at(ug.end)

# One 3V3_SYS spine feeding all three power pins, each with its own 4.7 uF +
# 0.1 uF pair - the datasheet asks for a pair PER POWER PIN, so this is six caps.
# Cap refs: C_dbg1a/b @ VREGIN, C_dbg2a/b @ VDD, C_dbg3a/b @ VIO.
for anchor, cref_bulk, cref_hf in (
        ('VREGIN', 'C_dbg1a', 'C_dbg1b'),
        ('VDD', 'C_dbg2a', 'C_dbg2b'),
        ('VIO', 'C_dbg3a', 'C_dbg3b')):
    d += (vl := elm.Line().left().at(getattr(u5, anchor)).length(1.4))
    d += (vn := elm.Dot())
    sh.shunt_parallel(vn.center, [
        (elm.Capacitor().length(1.3), cref_bulk, '4.7 uF'),
        (elm.Capacitor().length(1.3), cref_hf, '0.1 uF'),
    ], loc='left', spacing=1.1, step='left')
    sh.net(vn.center, 'left', '3V3_SYS', GREEN, stub=1.2)

# RSTb wants a 1 kOhm pull-up "in all cases" (CP2102N 2.1), to VIO on parts that
# have one - and the QFN24 does.
d += (rr := elm.Resistor().right().at(u5.RSTb).length(2.6)
      .label(part_lbl('R_rst', '1 kOhm'), 'top').color(GREY))
sh.net(rr.end, 'right', '3V3_SYS', GREEN, stub=1.0,
       note='1 kOhm to VIO - required in all cases', note_x=rr.end[0] + 4.4)

for anchor, ref, net, peer in (('TXD', 'R_dbg1', 'DBG_RX', 'to U1 RF1, pin 37  (U1RX)'),
                               ('RXD', 'R_dbg2', 'DBG_TX', 'from U1 RF0, pin 36  (U1TX)')):
    d += (r := elm.Resistor().right().at(getattr(u5, anchor)).length(2.6)
          .label(part_lbl(ref, '220 Ohm'), 'top').color(GREY))
    sh.net(r.end, 'right', net, AMBER, stub=1.0,
           note=peer, note_x=r.end[0] + 4.4)

sh.body(DY - 28.0,
        'U5 runs from 3V3_SYS, NOT from VBUS. This is CP2102N Figure 2.3 (internal 5 V regulator unused, so VREGIN is\n'
        'tied to VDD) plus Figure 2.6 (self-powered USB, VBUS reaching the SENSE PIN ONLY). The bus-powered Figure 2.5\n'
        'ties VBUS to VREGIN instead - that is the wiring to avoid, because it would let a laptop run the bridge while\n'
        'the vehicle rail is dead and drive DBG_RX into an unpowered MCU. The back-power failure mode from\n'
        'bench-wiring.md is designed out rather than patched. VBUS only ever tells U5 that a host is attached.')
sh.body(DY - 33.0,
        'THE CROSS IS ALREADY DONE: U5 TXD (21) drives the PIC RX (RF1) and U5 RXD (20) listens to the PIC TX (RF0),\n'
        'exactly as the Nano wires CDC TX to the target UART RX (DS50003011 Figure 3-1). Do not cross it a second time.\n'
        'Both directions must be populated: RF1 is how a server URL will later be written into the 1 KB Data EEPROM,\n'
        'so an output-only console would foreclose it. No DTR/RTS auto-reset circuit - reset belongs to J_icsp, and an\n'
        'RC on MCLR outside the sheet-3 network would fight the PICkit for the pin. Two SEPARATE 5.1 kOhm CC resistors\n'
        'are required, and D+/D- must reach BOTH A6/A7 and B6/B7 for either cable orientation to work. Route the pair\n'
        'at 90 Ohm differential. No series resistors on D+/D-: the CP2102N integrates the transceiver, its matching,\n'
        'and the pull-ups. Programming is NOT here - the PIC18F57Q84 has no USB peripheral, so U5 is the virtual COM\n'
        'port only. Program and debug are on J_icsp with a PICkit 5.', AMBER)

# ============================================================================
# SHEET 6 - Status LED + clock
# ============================================================================
LY = -118.0
sh.banner(LY + 1.8, '(6)  STATUS LED  -  RF3, pin 39, active low', AMBER)

d += (lt := elm.Tag(width=1.9).at((0, LY)).left().label('3V3_SYS').color(GREEN))
d += (lr := elm.Resistor().right().at(lt.start).length(2.4)
      .label(part_lbl('R_led0', '1 kOhm'), 'top').color(GREY))
d += (ld := elm.LED().right().at(lr.end).length(2.4)
      .label(part_lbl('D_led0', '~2 mA'), 'top').color(AMBER))
sh.net(ld.end, 'right', 'LED0', AMBER, stub=1.0)
sh.note(ld.end[0] + 3.2, LY, 'to U1 RF3, pin 39', GREY, 'right')

sh.body(LY - 2.0,
        'RF3 sinks the LED current, so the pin drives LOW to light it - which is what LATFbits.LATF3 already does in main.c.')

sh.banner(LY - 4.0, '(7)  CLOCK  -  nothing fitted', RED)
sh.body(LY - 5.2,
        'HFINTOSC at 64 MHz. Y_hs, C_osc1, C_osc2 and Y_sosc are all quantity ZERO, which leaves OSC1 (32) and\n'
        'OSC2 (33) free as general I/O. CONFIG1 MUST be programmed with RSTOSC = 000: an erased part comes up with\n'
        'RSTOSC = 111, meaning "external clock", and a crystal-less board will simply never run.', RED)

# padding anchors so edge tags and text are not clipped
sh.pad(NOTE_X + 22.0, TITLE_Y + 1.0)
sh.pad(NOTE_X + 22.0, LY - 7.0)
sh.pad(sh.MARGIN, LY - 7.0)

save(d, 'mcu-schematic')
