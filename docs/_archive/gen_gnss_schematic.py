#!/usr/bin/env python3
"""Generate the NEO-M9N support schematic (docs/gnss-schematic.pdf).

Every part in the consolidated BOM of docs/gnss-support-circuit.md appears
here, so the drawing and the BOM correspond 1:1. Only reference designators are
printed; values live in the BOM.

Sheets:
  (1) U4 pinout as wired - all 24 LCC pins with the board action for each
  (2) VCC supply and decoupling off the ferrite-isolated 3V3_SYS branch
  (3) V_BCKP and V_USB, the two pins most often got wrong
  (4) RF front end - one layout serving a passive or an active antenna
  (5) UART, RESET_N and TIMEPULSE to the PIC

The module already contains a SAW filter, an LNA, an LTE band 13 notch, an
internal DC block and 50 ohm matching, so the RF path here is deliberately
almost empty: adding a DC block or matching network would be a mistake.

Renders with schemdraw's SVG backend; SVG -> PDF/PNG via build_schematics.sh.
"""
import schemdraw.elements as elm

from schematic_common import (AMBER, FILL_CONN, FILL_GNSS, GREEN, GREY, RED,
                              Sheet, new_drawing, save)

d = new_drawing()
sh = Sheet(d)

TITLE_Y = 5.0
sh.body(TITLE_Y, 'FARSEER GNSS SUPPORT CIRCUIT  -  u-blox NEO-M9N-00B, 24-pin LCC', 'black')
sh.body(TITLE_Y - 0.8, 'Reference designators shown; component values are in gnss-support-circuit.md')
sh.body(TITLE_Y - 1.5, 'Sources: datasheet UBX-19014285 and integration manual UBX-19014286 (R10)')

# ============================================================================
# SHEET 1 - U4 as wired
# ============================================================================
sh.banner(1.8, '(1)  U4  NEO-M9N-00B  :  all 24 pins, with the board action for each', GREEN)

# (anchor, pin no., net tag, action, colour)
SIGNALS = [
    ('RF_IN', '11', 'RF_IN', '50 ohm to the antenna front end  -  no DC block, no matching', RED),
    ('VCC_RF', '9', 'VCC_RF', 'to the bias-T, active antenna only  -  VCC - 0.1 V, 50 mA', RED),
    ('LNA_EN', '14', 'LNA_EN', 'external LNA enable, ACTIVE HIGH  -  active antenna only', RED),
    ('TXD', '20', 'GNSS_TX', 'to PIC RD1 (U2RX)  -  NMEA out, 38400 then 115200', GREEN),
    ('RXD', '21', 'GNSS_RX', 'from PIC RD0 (U2TX)  -  configuration in', GREEN),
    ('TIMEPULSE', '3', 'GNSS_1PPS', 'to PIC RC2 (CCP1 capture)  -  1 PPS, 30 ns RMS, 4 mA', GREEN),
    ('RESET_N', '8', 'GNSS_RESET', 'from PIC RB3, open-drain  -  internal 7-13 kOhm pull-up', GREEN),
    ('D_SEL', '2', 'open', 'LEAVE OPEN = UART. Grounding it selects SPI', AMBER),
    ('SAFEBOOT_N', '1', 'TP_safeboot', 'leave open; bring to a test point for future firmware update', GREY),
    ('EXTINT', '4', 'open', 'leave open', GREY),
    ('USB_DM', '5', 'open', 'leave open  -  USB unused', GREY),
    ('USB_DP', '6', 'open', 'leave open  -  USB unused', GREY),
    ('SDA', '18', 'open', 'leave open  -  I2C unused', GREY),
    ('SCL', '19', 'open', 'leave open  -  I2C unused', GREY),
    ('RSVD', '15,16,17', 'do not connect', 'reserved  -  must be left unconnected', RED),
]
n = len(SIGNALS)

pins = [elm.IcPin(name='VCC', pin='23', side='left', slot='4/4'),
        elm.IcPin(name='V_BCKP', pin='22', side='left', slot='3/4'),
        elm.IcPin(name='V_USB', pin='7', side='left', slot='2/4'),
        elm.IcPin(name='GND', pin='10,12,13,24', side='left', slot='1/4')]
pins += [elm.IcPin(name=a, pin=p, side='right', slot=f'{n - i}/{n}')
         for i, (a, p, _, _, _) in enumerate(SIGNALS)]

d += (u4 := elm.Ic(pins=pins, w=6.8, h=13.0, pinspacing=0.9, leadlen=1.1,
                   plblsize=8)
      .fill(FILL_GNSS).label('U4   NEO-M9N-00B   24-pin LCC', 'top')
      .right().anchor('VCC').at((3.0, 0)))

NOTE_X = u4.RF_IN[0] + 5.0

sh.net(u4.VCC, 'left', 'NEO_VCC', GREEN, stub=1.2)
sh.net(u4.V_BCKP, 'left', 'NEO_VCC', GREEN, stub=1.2)
d += (vu := elm.Line().left().at(u4.V_USB).length(0.8))
d += elm.Ground().at(vu.end)
d += (gg := elm.Line().left().at(u4.GND).length(0.8))
d += elm.Ground().at(gg.end)

for anchor, _, net, action, color in SIGNALS:
    sh.net(getattr(u4, anchor), 'right', net, color, stub=0.8,
           note=action, note_x=NOTE_X)

sh.body(-15.5,
        'Baseline rule (datasheet 5): all inputs have internal pull-ups and can be left open if unused - which is why most\n'
        'of this pin list is "leave open" rather than a resistor. The two exceptions are V_USB, which must be GROUNDED, and\n'
        'V_BCKP, which must be TIED TO VCC if no backup source is fitted. Neither is covered by the leave-open rule.\n'
        'The LCC package has perimeter castellations at 1.1 mm pitch: joints are visible and probeable, no thermal pad, no\n'
        'X-ray needed. Take the footprint and paste mask from IM Figures 37 and 38, and leave keep-out on the long edge for\n'
        'de-paneling residual tabs up to 0.5 mm.')

# ============================================================================
# SHEET 2 - VCC supply
# ============================================================================
VY = -22.0
sh.banner(VY + 2.4, '(2)  MAIN SUPPLY  :  3V3_SYS -> FB2 -> NEO_VCC  (pin 23)', GREEN)

d += (vt := elm.Tag(width=1.9).at((0, VY)).left().label('3V3_SYS').color(GREEN))
d += (fb2 := elm.Inductor2().right().at(vt.start).length(2.6).label('FB2', 'top').color(GREEN))
d += (v1 := elm.Dot().at(fb2.end))
sh.shunt(v1.center, elm.Capacitor(), 'C_neoBulk')
d += elm.Line().right().at(v1.center).length(3.0)
d += (v2 := elm.Dot())
sh.shunt(v2.center, elm.Capacitor(), 'C_neo2')
d += elm.Line().right().at(v2.center).length(3.0)
d += (v3 := elm.Dot())
sh.shunt(v3.center, elm.Capacitor(), 'C_neo1')
sh.net(v3.center, 'right', 'NEO_VCC', GREEN, stub=1.6)

sh.note(v3.center[0], VY - 3.4, '1 uF, hard against\nthe VCC pad', GREY)

sh.body(VY - 5.0,
        'THREE CONSTRAINTS THAT ARE EASY TO VIOLATE.\n'
        '1. Series resistance in the VCC line must stay UNDER 0.2 OHM (IM 4.2.1 / 4.9.1), or dynamic current generates\n'
        '   input voltage noise. That is a spec on FB2: choose the bead for DCR below 0.2 ohm, not just for impedance at\n'
        '   100 MHz. A typical 600 ohm @ 100 MHz part can easily exceed it.\n'
        '2. VCC ramp rate must land between 20 and 8000 us/V, so a 0 -> 3.3 V rise takes between 66 us and 26.4 ms.\n'
        '   Too fast MAY PERMANENTLY DAMAGE THE DEVICE (datasheet Table 10 note 7). Buck B\'s ramp is checked in\n'
        '   power-rail-notes.md, and must be re-checked if its soft-start ever changes.\n'
        '3. The VCC pad wants copper, not a thin trace: large pad, large vias down to the power layer, C_neo1 as close as\n'
        '   physically possible (IM 4.8.4.2). Peak draw is 100 mA during acquisition.')

# ============================================================================
# SHEET 3 - V_BCKP and V_USB
# ============================================================================
BY = -33.0
sh.banner(BY + 2.4, '(3)  V_BCKP (pin 22) AND V_USB (pin 7)', GREEN)

d += (bt := elm.Tag(width=1.9).at((0, BY)).left().label('NEO_VCC').color(GREEN))
d += elm.Line().right().at(bt.start).length(3.0)
d += (b1 := elm.Dot())
sh.shunt(b1.center, elm.Capacitor(), 'C_bkp')
sh.net(b1.center, 'right', 'V_BCKP', GREEN, stub=2.6)
sh.note(b1.center[0] + 6.2, BY, 'to U4 pin 22', GREY, 'right')

d += (ut := elm.Tag(width=1.9).at((0, BY - 3.2)).left().label('V_USB').color(RED))
d += (ul := elm.Line().right().at(ut.start).length(2.4))
d += elm.Ground().at(ul.end)
sh.note(ul.end[0] + 0.6, BY - 3.2, 'U4 pin 7 straight to the ground plane', RED, 'right')

sh.body(BY - 5.6,
        'V_USB MUST BE TIED TO GND when USB is unused (IM 4.2.3, repeated in the 4.3 minimal design and the 4.9.1\n'
        'checklist). This is not covered by the "inputs may be left open" rule.\n'
        '\n'
        'V_BCKP maintains the RTC and battery-backed RAM, which is the difference between a hot start of a couple of\n'
        'seconds and a 24-29 s cold start every time the car is keyed off in the paddock. Backup draw is only 45 uA typ.\n'
        'If no backup source is fitted, TIE V_BCKP DIRECTLY TO VCC - never leave it floating. Keep the line low-resistance:\n'
        'the switchover from main to backup draws a short current peak, and a resistive path turns that into a damaging\n'
        'voltage drop, so no series resistor "for isolation" here.')

# ============================================================================
# SHEET 4 - RF front end
# ============================================================================
RY = -46.0
sh.banner(RY + 3.0, '(4)  RF FRONT END  -  one layout, passive or active antenna by populate / no-fit', RED)

d += (jg := elm.Ic(pins=[elm.IcPin(name='RF', side='right'),
                         elm.IcPin(name='SHIELD', side='bottom')],
                   w=2.2, h=1.6, plblsize=8)
      .fill(FILL_CONN).label('J_gnss\nU.FL / SMA', 'top').right().anchor('RF').at((2.4, RY)))
d += elm.Ground().at(jg.SHIELD)

d += elm.Line().right().at(jg.RF).length(1.2)
d += (r0 := elm.Dot())
sh.shunt(r0.center, elm.DiodeTVS(), 'D_rf', 'left').color(RED)
d += elm.Line().right().at(r0.center).length(2.4)
d += (r1 := elm.Dot())

# Passive path: a plain link straight through to RF_IN.
d += (rb0 := elm.Resistor().right().at(r1.center).length(3.0)
      .label('R_bias0', 'top').color(GREY))
d += (r2 := elm.Dot().at(rb0.end))
sh.net(r2.center, 'right', 'RF_IN', RED, stub=1.4)
sh.note(r2.center[0] + 4.0, RY, 'to U4 pin 11', GREY, 'right')

# Active path: bias-T injecting VCC_RF into the same node. C_bias is taken off
# to the side before dropping to ground, so it never lands on L_bias below it.
d += (lb := elm.Inductor2().up().at(r1.center).length(2.8)
      .label('L_bias', 'left').color(GREEN))
d += (r3 := elm.Dot().at(lb.end))
d += (rb := elm.Resistor().up().at(r3.center).length(2.4)
      .label('R_bias', 'left').color(GREY))
sh.net(rb.end, 'up', 'VCC_RF', RED, stub=0.6)
d += (cbr := elm.Line().right().at(r3.center).length(1.6))
sh.shunt(cbr.end, elm.Capacitor().length(1.4), 'C_bias', 'right')
sh.note(r3.center[0] + 4.0, r3.center[1] + 0.9,
        'Bias-T, ACTIVE antenna only.\n'
        'Fit L_bias / C_bias / R_bias and omit R_bias0;\n'
        'for a passive antenna do exactly the reverse.', GREY, 'right')

sh.body(RY - 8.0,
        'The module has an internal DC block and internal 50 ohm matching, plus a SAW filter ahead of its LNA and an LTE\n'
        'band 13 notch. DO NOT FIT A DC BLOCK OR A MATCHING NETWORK on RF_IN - they are already inside, and the SAW is what\n'
        'lets an inexpensive passive antenna work next to a BG95 transmitting at ~22 dBm from a few tens of cm away.\n'
        '\n'
        'R_bias is 22 ohm, NOT the 10 ohm in IM Table 26: supplying from VCC_RF at 3.3 V requires >= 19 ohm to hold\n'
        'short-circuit current under 150 mA, and 22 ohm is the nearest standard value. A chafed coax against bodywork is\n'
        'the most likely short in a race car, and this resistor is what stops it destroying the bias-T or the internal feed.\n'
        '\n'
        'D_rf is REQUIRED (IM 4.5.2): an external RF connector is a conduction path for destructive signals. RF_IN routes\n'
        'as a grounded co-planar waveguide referenced to layer 2, matched to 50 ohm, via-shielded along its entire length,\n'
        'with vias around the RF_IN pad and NO STUBS. Absolute limits: 0 dBm in band, +13 dBm out of band, 30 dB max\n'
        'external gain - do not stack an active antenna with a further LNA.')

# ============================================================================
# SHEET 5 - UART and control
# ============================================================================
UY = -62.0
sh.banner(UY + 2.2, '(5)  UART AND CONTROL TO THE PIC  -  direct, no level shifting, no series resistors', GREEN)

LINKS = [('GNSS_TX', 'U4 pin 20 TXD', 'PIC RD1 (pin 43), U2RX', GREEN),
         ('GNSS_RX', 'U4 pin 21 RXD', 'PIC RD0 (pin 42), U2TX', GREEN),
         ('GNSS_RESET', 'U4 pin 8 RESET_N', 'PIC RB3 (pin 11), open-drain', GREEN),
         ('GNSS_1PPS', 'U4 pin 3 TIMEPULSE', 'PIC RC2 (pin 40), CCP1 capture', GREEN)]
for i, (net, left, right, color) in enumerate(LINKS):
    y = UY - 1.5 * i
    d += (t := elm.Tag(width=2.6).at((0, y)).left().label(net).color(color))
    d += elm.Line().right().at(t.start).length(5.0)
    sh.note(-3.0, y, left, GREY, 'left')
    sh.note(5.4, y, right, GREY, 'right')

sh.body(UY - 8.0,
        'Both ends sit on 3V3_SYS, so the levels are comfortable in both directions: the NEO needs Vih >= 0.8 x VCC =\n'
        '2.64 V and swings to within 0.4 V of the rails at 2 mA, and the PIC is on the same rail. Max 5 mA per digital\n'
        'I/O, and NO HARDWARE FLOW CONTROL is supported. TIMEPULSE is worth routing even though the firmware does not use\n'
        'it yet - 30 ns RMS in hardware capture beats UART arrival time by orders of magnitude for correlating position\n'
        'to lap timing.')

# padding anchors so edge tags and text are not clipped
sh.pad(NOTE_X + 26.0, TITLE_Y + 1.0)
sh.pad(NOTE_X + 26.0, UY - 10.0)
sh.pad(sh.MARGIN, UY - 10.0)

save(d, 'gnss-schematic')
