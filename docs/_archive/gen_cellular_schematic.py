#!/usr/bin/env python3
"""Generate the BG95-M3 Mini PCIe host schematic (docs/cellular-schematic.pdf).

Every part in the consolidated BOM of docs/cellular-support-circuit.md appears
here, so the drawing and the BOM correspond 1:1. Only reference designators are
printed; values live in the BOM.

Sheets:
  (1) Socket power - the 470 uF-class burst reservoir and the Figure 3 ladder
      feeding all four VCC_3V3 pins
  (2) J2 signal map - every non-power pin we touch, with its socket pin number
  (3) (U)SIM holder, 1.8 V, built from Quectel Figure 4 (card-detect switch
      wired to USIM_DET for hot-plug)
  (4) LED_WWAN# network status indicator
  (5) USB firmware-update path (optional)

This is the MINI PCIe CARD, not the raw 102-pin LGA module: UART and control
pins are a 3.3 V domain (Table 8 / Table 10), there is no PWRKEY, and the card
carries its own antenna connectors. Only the (U)SIM, PCM and I2C pins are 1.8 V.

Renders with schemdraw's SVG backend; SVG -> PDF/PNG via build_schematics.sh.
"""
import schemdraw.elements as elm

from schematic_common import (AMBER, BLUE, FILL_CELL, FILL_CONN, GREEN, GREY,
                              RED, Sheet, new_drawing, save)

d = new_drawing()
sh = Sheet(d)

TITLE_Y = 5.0
sh.body(TITLE_Y, 'FARSEER CELLULAR SUPPORT CIRCUIT  -  Quectel BG95-M3, Mini PCIe card', 'black')
sh.body(TITLE_Y - 0.8, 'Reference designators shown; component values are in cellular-support-circuit.md')
sh.body(TITLE_Y - 1.5, 'Pin numbers are the 52-pin Mini PCIe edge connector (Mini PCIe Hardware Design V1.0, Table 4)')

# ============================================================================
# SHEET 1 - Socket power
# ============================================================================
sh.banner(1.8, '(1)  SOCKET POWER  :  3V3_CELL -> VCC_3V3 pins 2, 39, 41, 52', RED)

d += (ct := elm.Tag(width=2.0).at((0, 0)).left().label('3V3_CELL').color(RED))
d += elm.Line().right().at(ct.start).length(1.4)
d += (k0 := elm.Dot())
sh.shunt(k0.center, elm.DiodeTVS(), 'D_cell', 'left').color(RED)
d += elm.Line().right().at(k0.center).length(2.6)
d += (k1 := elm.Dot())
sh.shunt(k1.center, elm.Capacitor(polar=True), 'C10 / C11')
d += elm.Line().right().at(k1.center).length(2.8)
d += (k2 := elm.Dot())
sh.shunt(k2.center, elm.Capacitor(), 'C12 / C13')
d += elm.Line().right().at(k2.center).length(2.8)
d += (k3 := elm.Dot())
sh.shunt(k3.center, elm.Capacitor(), 'C14 / C15')
d += elm.Line().right().at(k3.center).length(2.2)

# Fan the rail out to the four VCC_3V3 pins.
d += (bus := elm.Line().right().length(6.6))
for i, pin in enumerate(('2', '39', '41', '52')):
    x = bus.start[0] + 0.6 + 2.0 * i
    d += (stub := elm.Line().up().at((x, 0)).length(1.1))
    d += elm.Dot().at((x, 0))
    sh.note(x, stub.end[1] + 0.45, f'J2 pin {pin}', RED)

sh.note(k1.center[0], -3.6, '3 x 220 uF polymer\n>= 470 uF total', GREY)
sh.note(k2.center[0], -3.6, '10 uF + 100 nF', GREY)
sh.note(k3.center[0], -3.6, '33 pF + 10 pF', GREY)

sh.body(-5.6,
        'Quectel 3.2: in 2G the input peak current reaches 2.7 A, and a LOW-ESR BYPASS CAPACITOR OF NO LESS THAN 470 uF\n'
        'is required to keep the rail from collapsing. C10/C11 is that reservoir; C12-C15 complete the Figure 3 ladder.\n'
        'All four VCC_3V3 pins must be fed - they are spread across the connector deliberately, and feeding only one is a\n'
        'current-density mistake. All fourteen GND pins (4, 9, 15, 18, 21, 26, 27, 29, 34, 35, 37, 40, 43, 50) go to plane.\n'
        'Sizing arithmetic is in power-rail-notes.md. Keep buck A\'s inductor and switch node away from the antenna run.')

# ============================================================================
# SHEET 2 - Signal map
# ============================================================================
JY = -13.0
sh.banner(JY + 2.6, '(2)  J2 SIGNAL MAP  :  every non-power pin we touch', RED)

# (anchor, socket pin, net tag, peer description, colour)
SIGNALS = [
    ('UART_RX', '11', 'CELL_RX', 'from PIC RF4 (U3TX) through R_u3a  -  card RX', GREEN),
    ('UART_TX', '13', 'CELL_TX', 'to PIC RF5 (U3RX) through R_u3b  -  card TX', GREEN),
    ('UART_CTS', '23', 'CELL_RTS', 'from PIC RF7 (U3RTS)  -  Opt, flow control off by default', GREY),
    ('UART_RTS', '25', 'CELL_CTS', 'to PIC RF6 (U3CTS)  -  Opt, flow control off by default', GREY),
    ('PERST_N', '22', 'CELL_PERST', 'from PIC RB0, open-drain  -  VIL <= 0.45 V, hold low 2-3.8 s', RED),
    ('W_DISABLE_N', '20', 'CELL_W_DIS', 'from PIC RB1  -  Opt airplane mode, VIL <= 0.45 V', GREY),
    ('RI', '17', 'CELL_RI', 'to PIC RB2 (INT2)  -  Opt, 120 ms low pulse on a URC', GREY),
    ('DTR', '31', 'n/c', 'sleep control  -  Opt, not routed', GREY),
    ('LED_WWAN_N', '42', 'WWAN_N', 'to sheet 4  -  open collector, sinks up to 40 mA', AMBER),
    ('USB_DM', '36', 'USB_DM', 'to sheet 5  -  Opt, 90 ohm differential', BLUE),
    ('USB_DP', '38', 'USB_DP', 'to sheet 5  -  Opt, 90 ohm differential', BLUE),
    ('USIM_VDD', '8', 'SIM_VDD', 'to sheet 3  -  1.8 V, supplied BY the card', AMBER),
    ('USIM_DATA', '10', 'SIM_IO', 'to sheet 3  -  1.8 V', AMBER),
    ('USIM_CLK', '12', 'SIM_CLK', 'to sheet 3  -  1.8 V', AMBER),
    ('USIM_RST', '14', 'SIM_RST', 'to sheet 3  -  1.8 V', AMBER),
    ('USIM_DET', '44', 'SIM_DET', 'to sheet 3  -  1.8 V domain, card-detect, hot-plug via AT+QSIMDET', AMBER),
]
n = len(SIGNALS)

pins = [elm.IcPin(name='VCC_3V3', pin='2,39,41,52', side='left', slot='2/2'),
        elm.IcPin(name='GND', pin='14x', side='left', slot='1/2')]
pins += [elm.IcPin(name=a, pin=p, side='right', slot=f'{n - i}/{n}')
         for i, (a, p, _, _, _) in enumerate(SIGNALS)]

d += (j2 := elm.Ic(pins=pins, w=7.0, h=13.5, pinspacing=0.9, leadlen=1.1,
                   plblsize=8)
      .fill(FILL_CELL).label('J2   Mini PCIe socket, 52-pin full size + latch', 'top')
      .right().anchor('VCC_3V3').at((3.0, JY)))

NOTE_X = j2.UART_RX[0] + 7.4

sh.net(j2.VCC_3V3, 'left', '3V3_CELL', RED, stub=1.2)
d += (jg := elm.Line().left().at(j2.GND).length(0.8))
d += elm.Ground().at(jg.end)

# The two UART lines carry their 220 ohm series resistors; everything else is
# a direct connection, so only those two rows get a part drawn in them.
SERIES = {'UART_RX': ('R_u3a', 'top'), 'UART_TX': ('R_u3b', 'bottom')}

for anchor, _, net, peer, color in SIGNALS:
    src = getattr(j2, anchor)
    if anchor in SERIES:
        ref, loc = SERIES[anchor]
        d += (r := elm.Resistor().right().at(src).length(2.0)
              .label(ref, loc).color(GREY))
        src = r.end
    sh.net(src, 'right', net, color, stub=0.8, note=peer, note_x=NOTE_X)

sh.body(JY - 17.4,
        'NO LEVEL SHIFTERS. Table 8 puts UART_RX/TX/CTS/RTS in the 3.3 V power domain and Table 10 does the same for RI,\n'
        'DTR, W_DISABLE# and PERST#, so the 3.3 V PIC wires straight across. Do not fit the TXS0108 the raw-LGA guide\n'
        'calls for. Only (U)SIM, PCM and I2C are 1.8 V, and none of those reach the MCU.\n'
        '\n'
        'The UART names are CARD-RELATIVE and therefore ALREADY CROSSED: pin 11 UART_RX is "connect to DTE\'s TX" and pin\n'
        '13 UART_TX is "connect to DTE\'s RX". Wire PIC TX to pin 11 and PIC RX to pin 13; do not cross them a second time.\n'
        '\n'
        'There is NO PWRKEY on this card. Figure 1 shows an automatic power-on circuit, so the card boots whenever\n'
        '3V3_CELL is live - boot order is set by buck A\'s EN pin (PIC RA2, high = on), not by a module key pin.\n'
        '\n'
        'LEFT UNCONNECTED: WAKE# (1), I2C_SCL/SDA (30, 32), PCM_CLK/DOUT/DIN/SYNC (45, 47, 49, 51), and\n'
        'every RESERVED pin (3, 5, 6, 7, 16, 19, 24, 28, 33, 46, 48). Table 4 note 3: keep all reserved and unused pins\n'
        'unconnected - do NOT ground them "to be safe", since several carry repurposed standard Mini PCIe functions.')

# ============================================================================
# SHEET 3 - (U)SIM holder
# ============================================================================
SY = -36.0
sh.banner(SY + 3.6, '(3)  (U)SIM HOLDER  -  1.8 V only, Quectel Figure 4 (holder with card-detect switch)', AMBER)

d += (j3 := elm.Ic(pins=[elm.IcPin(name='VCC', side='left', slot='5/5'),
                         elm.IcPin(name='RST', side='left', slot='4/5'),
                         elm.IcPin(name='CLK', side='left', slot='3/5'),
                         elm.IcPin(name='IO', side='left', slot='2/5'),
                         elm.IcPin(name='SW', side='left', slot='1/5'),
                         elm.IcPin(name='GND', side='bottom')],
                   w=3.2, h=11.6, pinspacing=2.6, leadlen=1.1, plblsize=8)
      .fill(FILL_CONN).label('J3   Nano-SIM holder (hinged, detect switch)', 'top')
      .right().anchor('VCC').at((14.0, SY)))
d += elm.Ground().at(j3.GND)

# VCC: bypass cap only, no series resistor. D_sim hangs off the same row.
d += elm.Line().left().at(j3.VCC).length(2.2)
d += (sv := elm.Dot())
sh.shunt(sv.center, elm.Capacitor().length(1.3), 'C_sim1', 'left')
d += elm.Line().left().at(sv.center).length(2.4)
d += (sesd := elm.Dot())
sh.shunt(sesd.center, elm.DiodeTVS().length(1.3), 'D_sim', 'left').color(RED)
sh.net(sesd.center, 'left', 'SIM_VDD', AMBER, stub=1.8)
sh.leader((sesd.center[0] - 0.25, sesd.center[1] - 0.7),
          (sesd.center[0] - 0.6, sesd.center[1] + 1.9),
          'One TVS array, <= 15 pF, covering all four SIM lines at the holder.',
          'left', RED)

# RST / CLK / IO: direct connection + 33 pF to ground. (Figure 4 draws 0 ohm
# series links here as a debug aid; deliberately omitted from this design.)
for anchor, cref, net in (('RST', 'C_sim2', 'SIM_RST'),
                          ('CLK', 'C_sim3', 'SIM_CLK'),
                          ('IO', 'C_sim4', 'SIM_IO')):
    src = getattr(j3, anchor)
    d += (r := elm.Line().left().at(src).length(2.2))
    d += (nd := elm.Dot().at(r.end))
    sh.shunt(nd.center, elm.Capacitor().length(1.3), cref, 'left')
    d += elm.Line().left().at(nd.center).length(2.4)
    d += (nd2 := elm.Dot())
    if anchor == 'IO':
        # Optional anti-jamming pull-up back to USIM_VDD. Drawn downwards, tag
        # turned sideways so the SW detect row below can pass underneath.
        d += (pu := elm.Resistor().down().at(nd2.center).length(1.4)
              .label('R_simPU', 'left').color(GREY))
        d += elm.Tag(width=1.9).left().at(pu.end).label('SIM_VDD').color(AMBER)
    sh.net(nd2.center, 'left', net, AMBER, stub=1.8)

# Detect switch row: normally open, closes SW to the grounded shell when the
# card is seated. R_det1/R_det2 (51k/51k from 3V3_CELL) bias SIM_DET at
# ~1.65 V because the Mini PCIe card exports no always-on 1.8 V rail.
d += elm.Line().left().at(j3.SW).length(1.6)
d += (da := elm.Dot())
d += (rd2 := elm.Resistor().down().at(da.center).length(1.4)
      .label('R_det2', 'right', ofst=0.2).color(GREY))
d += elm.Ground().at(rd2.end)
d += elm.Line().left().at(da.center).length(1.6)
d += (db := elm.Dot())
d += (rd1 := elm.Resistor().down().at(db.center).length(1.4)
      .label('R_det1', 'left', ofst=0.2).color(GREY))
d += elm.Tag(width=1.9).left().at(rd1.end).label('3V3_CELL').color(RED)
sh.net(db.center, 'left', 'SIM_DET', AMBER, stub=3.4)

sh.body(SY - 17.0,
        'The card supplies USIM_VDD itself at 1.8 V; our board provides the holder and the protection network. C_sim1 must\n'
        'NOT exceed 1 uF (3.3) and sits at the holder. The 33 pF caps filter EGSM900 interference. Figure 4\'s 0 ohm\n'
        'series links in RST/CLK/DATA (debug aid only) are DELIBERATELY OMITTED - lines run straight to the holder.\n'
        'The holder is a HINGED type (locking stainless cover, no eject spring to bounce under vibration); the Hologram\n'
        'triple-cut SIM is punched to the nano (4FF) cut.\n'
        '\n'
        'CARD DETECT: the switch closes SW to the grounded shell when the card is seated, so SIM_DET reads low = inserted.\n'
        'Quectel Figure 4 pulls USIM_DET to an always-on 1.8 V rail, which this card does not export - R_det1/R_det2 divide\n'
        '3V3_CELL to ~1.65 V instead, inside the 1.8 V domain VIH window (Table 23). Hot-plug is DISABLED BY DEFAULT:\n'
        'firmware sends AT+QSIMDET=1,0 (low = inserted, NV-saved) and AT+QSIMSTAT=1 for insertion/removal URCs.\n'
        '\n'
        'Layout, all mandatory at review: holder as close to the socket as possible with trace length under 200 mm; SIM\n'
        'signals kept away from RF and power-supply traces; ground between socket and holder short and wide, >= 0.5 mm;\n'
        'USIM_DATA and USIM_CLK separated and shielded by surrounding ground. The holder is the only user-accessible\n'
        'connector on this subsystem, so it is the realistic ESD entry point - D_sim is Req, not Rec.')

# ============================================================================
# SHEET 4 - LED_WWAN#
# ============================================================================
WY = -60.0
sh.banner(WY + 1.8, '(4)  LED_WWAN#  -  network status, pin 42, open collector, active low', AMBER)

d += (wt := elm.Tag(width=1.9).at((0, WY)).left().label('3V3_SYS').color(GREEN))
d += (wr := elm.Resistor().right().at(wt.start).length(2.4).label('R_wwan', 'top').color(GREY))
d += (wd := elm.LED().right().at(wr.end).length(2.4).reverse().label('D_wwan', 'top').color(AMBER))
sh.net(wd.end, 'right', 'WWAN_N', AMBER, stub=1.2)
sh.note(wd.end[0] + 3.6, WY, 'to J2 pin 42', GREY, 'right')

sh.body(WY - 2.0,
        'R_wwan IS NOT OPTIONAL if D_wwan is fitted: 3.7.4 says a resistor MUST be placed in series, and the pin will sink\n'
        'up to 40 mA and cook the LED without it. 1 kOhm gives about 2 mA. Default pattern (AT+QCFG="ledmode",0): 200 ms\n'
        'low / 1800 ms high = searching, 1800 / 200 = registered and idle, 125 / 125 = data transfer - readable across a paddock.', AMBER)

# ============================================================================
# SHEET 5 - USB firmware-update path
# ============================================================================
UY = -67.0
sh.banner(UY + 2.4, '(5)  USB  -  pins 36 / 38, optional, firmware update path', BLUE)

for anchor, rref, net, yoff in (('DM', 'R_usb1', 'USB_DM', 0.0),
                                ('DP', 'R_usb2', 'USB_DP', -2.8)):
    y = UY + yoff
    tag = elm.Tag(width=1.9).at((0, y)).left().label(net).color(BLUE)
    d += tag
    d += (r := elm.Resistor().right().at(tag.start).length(2.4)
          .label(rref, 'top').color(GREY))
    d += (nd := elm.Dot().at(r.end))
    sh.shunt(nd.center, elm.DiodeTVS().length(1.3), 'D_usb' if yoff == 0 else '', 'right').color(RED)
    d += (ln := elm.Line().right().at(nd.center).length(2.2))
    d += (ind := elm.Inductor2().right().at(ln.end).length(2.2)
          .label('L_usb' if yoff == 0 else '', 'top').color(GREEN))
    sh.net(ind.end, 'right', 'J_usb', BLUE, stub=1.0)

sh.body(UY - 6.4,
        'R_usb1/2 are 0 ohm and NOT MOUNTED by default (Figure 6) - they exist so the pair can be broken out to test\n'
        'points. L_usb is a common-mode choke and belongs close to the socket. Route as a 90 ohm differential pair with\n'
        'ground surround, never under crystals, oscillators, magnetics or RF traces, preferably on an inner layer.')

# ============================================================================
# Text-only notes: RF and mechanical, which have no host-board parts.
# ============================================================================
RY = -69.0
sh.banner(RY, '(6)  RF AND MECHANICAL  -  no host-board parts', GREY)
sh.body(RY - 1.2,
        'RF: NOTHING on our board. The card carries its own 50 ohm main antenna connector and the antenna mates directly\n'
        'to it - no 50 ohm trace, no matching network, no antenna feed on the host PCB. What the board must provide is\n'
        'mechanical: clearance above the card for the U.FL-LP plug and its cable bend radius, a route to the enclosure\n'
        'bulkhead, and strain relief. In a race car that cable sees vibration continuously - anchor it.\n'
        '\n'
        'Mechanical: 51.0 x 30.0 mm full-size card, standard 52-pin Mini PCIe socket (e.g. Molex 679105700) WITH latch.\n'
        'In a vehicle the latch is structural, not convenience; add a retaining screw or bracket. Operating range tops out\n'
        'at +75 C (extended +80 C), which an enclosure near a transmission tunnel can exceed - plan the mounting spot.')

# padding anchors so edge tags and text are not clipped
sh.pad(NOTE_X + 24.0, TITLE_Y + 1.0)
sh.pad(NOTE_X + 24.0, RY - 8.0)
sh.pad(sh.MARGIN, RY - 8.0)

save(d, 'cellular-schematic')
