#!/usr/bin/env python3
"""Generate the whole-board schematic (docs/full-schematic.pdf).

This drawing owns no circuit detail of its own. It is assembled from the four
subsystem generators in this folder, which stay the single source of truth:

    gen_power_schematic.py     power-rails-schematic.svg
    gen_mcu_schematic.py       mcu-schematic.svg
    gen_cellular_schematic.py  cellular-schematic.svg
    gen_gnss_schematic.py      gnss-schematic.svg

Each one is executed, its Drawing object collected, and the whole drawing
embedded as a single element on a master sheet. Nothing is copied, so the
combined sheet cannot drift from the four individual ones.

Layout:

    (0)  SYSTEM OVERVIEW - a block diagram, drawn here, showing how the four
         subsystems actually connect: the two rails, the three UARTs and the
         handful of control lines. Every link is a real wire, so this is the
         sheet that answers "what talks to what". Under it, the cross-board net
         list naming both ends of every one of those wires.
    (A)-(D)  the four detail sheets, tiled left to right underneath, each in
         its own frame. Within them connections are still made by net-label
         tag, and a tag on one tile means the same net as the identical tag on
         another.

Run from the repo root with docs/ on the import path (build_schematics.sh does
this):  PYTHONPATH=docs python3 docs/gen_full_schematic.py
"""
import runpy

import schemdraw.elements as elm

import schematic_common
from schematic_common import (AMBER, BLUE, FILL_CELL, FILL_CONN, FILL_GNSS,
                              FILL_MCU, GREEN, GREY, RED, Sheet, new_drawing,
                              save)

# The subsystem generators call save() at the end. We only want their Drawing
# objects here, not four rewritten SVGs as a side effect of running them.
schematic_common.SUPPRESS_SAVE = True

d = new_drawing()
sh = Sheet(d)

note = sh.note


# ============================================================================
# Drawing helpers for the overview sheet
# ============================================================================
def block(x, y, w, h, title, pins, fill=FILL_CONN, edge='black'):
    """A labelled rectangle placed by its CENTRE, with anonymous pins.

    Pin names are left blank: on a block diagram the wire label carries the
    signal name, and pin names printed inside the box only compete with the
    block title. The anchors are still named so wires can attach to them.

    Note the box size goes in as `size=`. Ic takes w/h only as part of that
    tuple; passing them as separate keywords is accepted and then ignored, and
    the box silently falls back to auto-sizing itself around its pins.
    """
    ic = (elm.Ic(pins=pins, size=(w, h), leadlen=0.6, plblsize=8)
          .fill(fill).color(edge).label(title, 'center')
          .anchor('center').at((x, y)))
    d.add(ic)
    return ic


def pin(side, anchorname, slot=None):
    return elm.IcPin(name='', side=side, anchorname=anchorname, slot=slot)


def wire(points, color=GREY, lw=1.6):
    """Orthogonal run through an explicit list of points."""
    for a, b in zip(points, points[1:]):
        ln = elm.Line().at(a).to(b).color(color)
        ln.linewidth(lw)
        d.add(ln)


def junction(xy, color=GREY):
    d.add(elm.Dot(radius=0.13).at(xy).color(color))


def frame(x0, y0, x1, y1, color=GREY):
    """Rectangle in absolute coordinates.

    Deliberately four Lines rather than elm.Rect: Rect's corners are LOCAL to
    the element, so an un-anchored Rect lands wherever the drawing cursor
    happens to be - which, after an ElementDrawing, is nowhere useful.
    """
    wire([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], color, lw=1.0)


# ============================================================================
# SHEET 0 - SYSTEM OVERVIEW
# ============================================================================
TITLE_Y = 18.0
sh.body(TITLE_Y, 'FARSEER  -  WHOLE-BOARD SCHEMATIC', 'black')
sh.body(TITLE_Y - 1.0,
        'In-car race telemetry module:  PIC18F57Q84  +  BG95-M3 Mini PCIe (UDP uplink / downlink)  +  NEO-M9N GNSS')
sh.body(TITLE_Y - 1.9,
        'Sheet 0 is the system overview and the cross-board net list. Sheets A-D are the four detail schematics, '
        'unchanged, each generated from its own script and matching its own BOM 1:1.')

sh.banner(TITLE_Y - 3.6,
          '(0)  SYSTEM OVERVIEW  -  every inter-block connection.   Pin numbers: U1 = 48-pin TQFP,  J2 = 52-pin Mini PCIe edge,  U4 = 24-pin LCC.   '
          'Wires that cross WITHOUT a dot are not connected.', BLUE)

# --- lanes -----------------------------------------------------------------
VSYS_X = 12.5    # VSYS riser
SYS_X = 27.5     # 3V3_SYS riser
SIG_X = 46.0     # signal lane between the PIC and the two radio blocks
FAR_X = 64.0     # J2 / U4 centre line
ANT_X = 78.0     # antennas and SIM holder

# --- power chain -----------------------------------------------------------
j1 = block(-4.0, 0.0, 5.4, 3.0, 'J1\nVBAT_IN\n7-18 V', [pin('right', 'OUT')])

prot = block(5.0, 0.0, 7.4, 3.4,
             'F1  Q1  D1\nfuse, reverse polarity,\nload-dump TVS, pi filter',
             [pin('left', 'IN'), pin('right', 'OUT')], FILL_CONN, BLUE)

bucka = block(19.0, 10.0, 8.0, 3.4,
              'U2  TPS54560-Q1\nbuck  3.3 V, >= 4 A',
              [pin('left', 'VIN'), pin('right', 'OUT'), pin('bottom', 'EN')],
              '#fff3e6', RED)

buckb = block(19.0, -10.0, 8.0, 3.4,
              'U3  LMR16006X\nbuck  3.3 V, ~0.6 A',
              [pin('left', 'VIN'), pin('right', 'OUT')], FILL_GNSS, GREEN)

wire([j1.OUT, prot.IN], 'black')
wire([prot.OUT, (VSYS_X, 0.0)], 'black')
junction((VSYS_X, 0.0), 'black')
wire([(VSYS_X, 0.0), (VSYS_X, 10.0), bucka.VIN], 'black')
wire([(VSYS_X, 0.0), (VSYS_X, -10.0), buckb.VIN], 'black')
note(VSYS_X + 1.4, 1.0, 'VSYS', 'black')

# --- MCU -------------------------------------------------------------------
pic = block(38.0, 0.0, 11.0, 11.0,
            'U1   PIC18F57Q84-I/PT\n48-pin TQFP\n\nHFINTOSC 64 MHz,\nno crystal fitted',
            [pin('left', 'VDD', '2/2'), pin('left', 'PWREN', '1/2'),
             pin('right', 'CELL', '3/3'), pin('right', 'GNSS', '1/3'),
             pin('bottom', 'DBG', '1/2'), pin('bottom', 'ICSP', '2/2')],
            FILL_MCU, AMBER)

# --- cellular --------------------------------------------------------------
j2 = block(FAR_X, 10.0, 10.0, 6.0,
           'J2   BG95-M3\nMini PCIe socket, 52-pin\n\nLTE-M / NB-IoT / EGPRS\nno PWRKEY: boots with its rail',
           [pin('left', 'PWR'), pin('bottom', 'SIG'),
            pin('right', 'SIM', '2/2'), pin('right', 'ANT', '1/2')],
           FILL_CELL, RED)

j3 = block(ANT_X, j2.SIM[1], 7.2, 2.4, 'J3\nNano-SIM, 1.8 V', [pin('left', 'IO')])
antl = block(ANT_X, j2.ANT[1], 7.2, 2.4, 'LTE antenna\nU.FL, on the card',
             [pin('left', 'RF')])
wire([j2.SIM, j3.IO], AMBER)
wire([j2.ANT, antl.RF], RED)

# --- GNSS ------------------------------------------------------------------
u4 = block(FAR_X, -10.0, 10.0, 5.0,
           'U4   NEO-M9N-00B\n24-pin LCC\n\nSAW + LNA + band 13 notch,\ninternal DC block and match',
           [pin('left', 'VCC'), pin('top', 'SIG'), pin('right', 'RF')],
           FILL_GNSS, GREEN)

antg = block(ANT_X, -10.0, 7.2, 2.4, 'GNSS antenna\nJ_gnss + bias-T', [pin('left', 'RF')])
wire([u4.RF, antg.RF], RED)

# --- debug and programming -------------------------------------------------
u5 = block(22.0, -19.0, 9.0, 3.4,
           'U5  CP2102N-A02\nUSB-UART bridge,\nruns from 3V3_SYS',
           [pin('left', 'USB'), pin('right', 'UART'), pin('top', 'VDD')],
           FILL_MCU, AMBER)

jdbg = block(7.0, -19.0, 7.4, 3.0, 'J_dbg\nUSB-C\nconsole only', [pin('right', 'D')])
wire([jdbg.D, u5.USB], AMBER)
note((jdbg.D[0] + u5.USB[0]) / 2, -18.1, 'USB CDC,\ndata only', GREY)

jicsp = block(22.0, -25.5, 9.0, 3.0,
              'J_icsp   6-pin ICSP\nPICkit 5: program + debug',
              [pin('right', 'ICSP')], FILL_CONN, BLUE)

# --- rails -----------------------------------------------------------------
# 3V3_CELL: buck A straight across to the socket.
wire([bucka.OUT, j2.PWR], RED)
note((bucka.OUT[0] + j2.PWR[0]) / 2, 10.8, '3V3_CELL   -   absorbs the 2.7 A 2G bursts', RED)

# 3V3_SYS: buck B east to the NEO, with a riser to the PIC and a tap to U5.
wire([buckb.OUT, u4.VCC], GREEN)
wire([(SYS_X, -10.0), (SYS_X, pic.VDD[1]), pic.VDD], GREEN)
wire([(SYS_X, -10.0), (SYS_X, -13.5), (u5.VDD[0], -13.5), u5.VDD], GREEN)
junction((SYS_X, -10.0), GREEN)
note(SYS_X + 4.0, -9.3, '3V3_SYS', GREEN)
note(50.0, -11.3, 'FB2, DCR < 0.2 ohm   |   VCC ramp must land in 66 us - 26.4 ms', GREY)

# --- signal links ----------------------------------------------------------
# Each wire stands for a whole group of nets; both ends are named in the net
# list below the diagram.
wire([pic.CELL, (SIG_X, pic.CELL[1]), (SIG_X, 4.5), (j2.SIG[0], 4.5), j2.SIG], RED)
note((SIG_X + j2.SIG[0]) / 2, 5.2, 'UART3 115200  +  PERST# / W_DISABLE# / RI      7 nets', RED)

wire([pic.GNSS, (SIG_X, pic.GNSS[1]), (SIG_X, -4.5), (u4.SIG[0], -4.5), u4.SIG], GREEN)
note((SIG_X + u4.SIG[0]) / 2, -3.8, 'UART2 38400 then 115200  +  RESET_N  +  1 PPS      4 nets', GREEN)

wire([pic.DBG, (pic.DBG[0], -19.0), u5.UART], AMBER)
note(30.0, -18.3, 'UART1 console, 115200      2 nets', AMBER)

wire([pic.ICSP, (pic.ICSP[0], -25.5), jicsp.ICSP], BLUE)
note((jicsp.ICSP[0] + pic.ICSP[0]) / 2, -24.8, 'ICSPDAT / ICSPCLK / MCLR_N      3 nets', BLUE)

# Rail enable. Crosses the 3V3_SYS riser with no dot: not a connection.
wire([pic.PWREN, (bucka.EN[0], pic.PWREN[1]), bucka.EN], RED)
note(23.5, pic.PWREN[1] - 1.9,
     'CELL_PWR_EN\nRA2 (23) -> buck A EN\nHIGH = rail on = modem on', RED)

# ============================================================================
# Cross-board net list - the same table as section 4 of
# interconnect-and-pin-budget.md, printed here so the sheet stands alone.
# ============================================================================
NL_Y = -31.0
sh.banner(NL_Y, '     CROSS-BOARD NET LIST  -  every signal crossing a block boundary.  '
                'No level shifters anywhere: the card\'s UART and control pins are 3.3 V, and the NEO shares the PIC\'s rail.',
          BLUE)

# Rows are either a (net, connection, note) triple, drawn as three columns, or
# a plain string of prose spanning the whole column. Columns are separate labels
# at fixed offsets rather than one padded string: SVG and PDF collapse runs of
# spaces, so text padded into columns comes out as ragged prose.
COL = [
    (sh.MARGIN, RED, 'U1  <->  J2   BG95-M3 Mini PCIe socket', [
        ('CELL_RX', 'RF4 (12)  ->  J2 pin 11 UART_RX', '220 ohm series'),
        ('CELL_TX', 'RF5 (13)  <-  J2 pin 13 UART_TX', '220 ohm series'),
        ('CELL_RTS', 'RF7 (15)  ->  J2 pin 23 UART_CTS', 'Opt'),
        ('CELL_CTS', 'RF6 (14)  <-  J2 pin 25 UART_RTS', 'Opt'),
        ('CELL_PERST', 'RB0 (8)  ->  J2 pin 22 PERST#', 'open-drain, 2-3.8 s'),
        ('CELL_W_DIS', 'RB1 (9)  ->  J2 pin 20 W_DISABLE#', 'Opt'),
        ('CELL_RI', 'RB2 (10)  <-  J2 pin 17 RI', 'Opt, INT2 wake'),
        '',
        'Card-relative names, ALREADY CROSSED: pin 11 is "connect to',
        'the DTE\'s TX". Do not cross the pair a second time.',
    ]),
    (7.0, GREEN, 'U1  <->  U4   NEO-M9N', [
        ('GNSS_RX', 'RD0 (42)  ->  U4 pin 21 RXD', ''),
        ('GNSS_TX', 'RD1 (43)  <-  U4 pin 20 TXD', ''),
        ('GNSS_RESET', 'RB3 (11)  ->  U4 pin 8 RESET_N', 'open-drain'),
        ('GNSS_1PPS', 'RC2 (40)  <-  U4 pin 3 TIMEPULSE', 'CCP1, 30 ns RMS'),
        '',
        'No hardware flow control exists on the NEO-M9N. TIMEPULSE is',
        'routed even though the firmware does not use it yet: hardware',
        'capture beats UART arrival time by orders of magnitude for',
        'tying a position fix to lap timing.',
    ]),
    (23.0, AMBER, 'U1  <->  U5 / J_icsp   console and programming', [
        ('DBG_TX', 'RF0 (36)  ->  U5 RXD (20)', '220 ohm series'),
        ('DBG_RX', 'RF1 (37)  <-  U5 TXD (21)', '220 ohm series'),
        ('ICSPDAT', 'RB7 (19)  <->  J_icsp pin 4', ''),
        ('ICSPCLK', 'RB6 (18)  <->  J_icsp pin 5', ''),
        ('MCLR_N', 'RE3 (20)  <-  J_icsp pin 1 VPP', ''),
        ('CELL_PWR_EN', 'RA2 (23)  ->  buck A EN', 'HIGH = rail on'),
        '',
        'U5 TXD already drives the PIC RX - do not cross again.',
        'Programming and in-circuit debug are J_icsp with a PICkit 5;',
        'the PIC18F57Q84 has no USB peripheral, so USB-C is console only.',
    ]),
]

#: Left edge of the net / connection / note columns, relative to the column.
FIELD_X = (0.0, 3.4, 8.4)
#: Vertical pitch of one text line, matching the 9-point line spacing the SVG
#: backend emits at fontsize 9. The columns are drawn a line at a time at
#: explicit positions: where a MULTI-line label sits relative to its anchor
#: depends on how many lines it has, which makes stacking two of them - a
#: coloured heading over a grey body - land the heading in the middle of the
#: body. One label per line has no such ambiguity.
LINE = 0.25

for x, color, heading, rows in COL:
    sh.body(NL_Y - 1.6, heading, color, x=x)
    for i, row in enumerate(rows):
        y = NL_Y - 2.4 - i * LINE
        if isinstance(row, str):
            if row:
                sh.body(y, row, GREY, x=x)
            continue
        for dx, field in zip(FIELD_X, row):
            if field:
                sh.body(y, field, GREY, x=x + dx)

# ============================================================================
# Sheet notes
# ============================================================================
LEG_Y = -38.0
sh.body(LEG_Y,
        'RAILS.  VBAT_IN 7-18 V -> VSYS -> two independent bucks. 3V3_CELL absorbs the BG95\'s 2.7 A 2G bursts; 3V3_SYS stays quiet for the PIC, the NEO-M9N and the USB bridge, so a transmit\n'
        'burst cannot brown out the MCU or the GNSS receiver. Both rails are 3.3 V and must stay 3.3 V - raising either one breaks cross-rail logic levels. Single ground plane throughout.')
sh.body(LEG_Y - 1.2,
        'BOOT ORDER.  Buck B is always enabled, so the PIC and the NEO-M9N come up together and can never drive each other while one is unpowered. Buck A\'s EN pull-down holds the modem off while\n'
        'the PIC is in reset; the PIC then drives CELL_PWR_EN high and the card auto-powers on - there is no PWRKEY on this card. PERST# is for recovering a wedged modem, not for boot.', RED)
sh.body(LEG_Y - 2.4,
        'READING SHEETS A-D.  Within them, connections are made by NET-LABEL TAG rather than by long wires, and the same tag name on two tiles is the same net: 3V3_SYS on sheet A is the same copper\n'
        'as 3V3_SYS on sheets B and D. Reference designators only are printed; component values live in the matching BOM markdown. Pin budget and PPS checks: interconnect-and-pin-budget.md.')

# ============================================================================
# SHEETS A-D - the four detail drawings, tiled left to right
# ============================================================================
TILES = [
    ('gen_power_schematic.py', '(A)  POWER RAILS', 'power-supply-bom.md', BLUE),
    ('gen_mcu_schematic.py', '(B)  MCU SUPPORT', 'mcu-support-circuit.md', AMBER),
    ('gen_cellular_schematic.py', '(C)  CELLULAR  -  BG95-M3', 'cellular-support-circuit.md', RED),
    ('gen_gnss_schematic.py', '(D)  GNSS  -  NEO-M9N', 'gnss-support-circuit.md', GREEN),
]

TILE_TOP = LEG_Y - 4.5   # top edge of every frame
GUTTER = 6.0             # gap between frames
PAD = 1.6                # frame inset around the embedded drawing

x_cursor = sh.MARGIN

for script, title, source_doc, color in TILES:
    sub = runpy.run_path(f'docs/{script}', run_name='__embedded__')['d']
    bbox = sub.get_bbox()
    width = bbox.xmax - bbox.xmin
    height = bbox.ymax - bbox.ymin

    # ElementDrawing puts the sub-drawing's own origin at .at(), so shifting by
    # -bbox.xmin / -bbox.ymax lands its top-left corner exactly where we want.
    left = x_cursor + PAD
    d.add(elm.ElementDrawing(sub).at((left - bbox.xmin,
                                      TILE_TOP - PAD - bbox.ymax)))

    frame(x_cursor, TILE_TOP,
          x_cursor + width + 2 * PAD, TILE_TOP - height - 2 * PAD)

    sh.banner(TILE_TOP + 1.4, f'{title}      component values in {source_doc}',
              color, x=x_cursor)
    x_cursor += width + 2 * PAD + GUTTER

# padding anchors so edge text is not clipped on export
sh.pad(sh.MARGIN, TITLE_Y + 1.5)
sh.pad(x_cursor, TITLE_Y + 1.5)

schematic_common.SUPPRESS_SAVE = False
save(d, 'full-schematic')
