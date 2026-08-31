#!/usr/bin/env python3
"""Shared style and drawing helpers for the farseer schematic generators.

Every `gen_*_schematic.py` in this folder follows the same conventions:

  * Passives are labelled with BOTH the reference designator and the value
    (via `part_lbl`), so the drawing is readable without flipping to the BOM.
    The matching `*-bom.md` remains the source of truth for MPN / status.
  * Rails and inter-sheet signals are joined by net-label tags rather than
    long wires, so sheets can be read independently.
  * Sheets are stacked vertically in one drawing, each with a numbered banner.

Rendered with schemdraw's SVG backend; SVG -> PDF/PNG via rsvg-convert
(see build_schematics.sh).
"""
import schemdraw
import schemdraw.elements as elm

schemdraw.use('svg')

# Shared palette. Colour carries meaning across all sheets:
#   BLUE  - input / protection      RED   - cellular (3V3_CELL) domain
#   GREEN - system (3V3_SYS) domain GREY  - passives, notes, net labels
#   AMBER - MCU domain
BLUE = '#1f5fbf'
RED = '#b00020'
GREEN = '#0a7d33'
GREY = '#555555'
AMBER = '#a86400'

FILL_MCU = '#fff8e6'
FILL_CELL = '#fdeaea'
FILL_GNSS = '#e9f9ee'
FILL_CONN = '#eef4ff'


def part_lbl(ref, value=None):
    """Two-line part label: reference designator, then value underneath.

    Callers that only have a ref-des yet (connectors, ICs) can omit `value`.
    """
    if value is None or value == '':
        return ref
    return f'{ref}\n{value}'


def new_drawing(unit=2.2, fontsize=9, lw=1.4):
    """A drawing configured the same way as the power-rail schematic."""
    d = schemdraw.Drawing()
    d.config(unit=unit, fontsize=fontsize, lw=lw)
    return d


class Sheet:
    """Thin helper bound to one Drawing.

    Wraps the handful of idioms every farseer schematic needs so the
    generators stay readable: annotations, leader lines to notes placed in
    open space, and shunt components dropped to ground.
    """

    def __init__(self, d):
        self.d = d

    #: Left margin every banner and body note is flush against. Text is placed
    #: with loc='right', i.e. running rightwards from the anchor point.
    MARGIN = -9.0

    def note(self, x, y, text, color=GREY, loc='center', halign=None):
        self.d.add(elm.Label().at((x, y))
                   .label(text, loc=loc, halign=halign).color(color))

    def body(self, y, text, color=GREY, x=None):
        """Flush-left paragraph of explanatory text.

        halign is set explicitly: without it a multi-line label centres its
        lines against each other, which reads badly for a paragraph.
        """
        self.note(self.MARGIN if x is None else x, y, text, color, 'right',
                  halign='left')

    def banner(self, y, text, color=BLUE, x=None):
        """Flush-left sheet heading."""
        self.body(y, text, color, x)

    def leader(self, xy_from, xy_to, text, loc='left', color=GREY):
        """Thin leader line from a part/net to a label placed in open space."""
        ln = elm.Line().at(xy_from).to(xy_to).color(color)
        ln.linewidth(0.6)
        self.d.add(ln)
        self.d.add(elm.Dot(radius=0.06).at(xy_from).color(color))
        self.note(xy_to[0], xy_to[1], text, color, loc)

    def shunt(self, start, part, ref, loc='right', color=GREY, value=None):
        """Drop `part` (labelled with ref-des + optional value) from `start` to ground."""
        p = part.down().at(start).label(part_lbl(ref, value), loc).color(color)
        self.d.add(p)
        self.d.add(elm.Ground().at(p.end))
        return p

    def shunt_parallel(self, start, parts, loc='right', color=GREY,
                       spacing=0.9, step='right'):
        """Drop several parts in parallel from `start` to ground.

        `parts` is a sequence of (element_factory_or_instance, ref, value)
        tuples. The first hangs straight down from `start`; each subsequent
        one is stepped sideways by `spacing` (direction `step`) so the labels
        do not collide and so left-side power pins can fan away from the IC.
        """
        first = None
        for i, (part, ref, value) in enumerate(parts):
            if i == 0:
                at = start
            else:
                stub = getattr(elm.Line(), step)().at(start).length(spacing * i)
                self.d.add(stub)
                at = stub.end
            p = part.down().at(at).label(part_lbl(ref, value), loc).color(color)
            self.d.add(p)
            self.d.add(elm.Ground().at(p.end))
            if first is None:
                first = p
        return first

    def shunt_rc(self, start, rref, cref, loc='left', rvalue=None, cvalue=None):
        """Series R-C from `start` down to ground (compensation network)."""
        r = (elm.Resistor().down().at(start)
             .label(part_lbl(rref, rvalue), loc).color(GREY))
        self.d.add(r)
        c = (elm.Capacitor().down().at(r.end)
             .label(part_lbl(cref, cvalue), loc).color(GREY))
        self.d.add(c)
        self.d.add(elm.Ground().at(c.end))
        return c

    def net(self, at, direction, label, color=GREY, stub=0.0, note=None,
            note_x=None):
        """Net-label tag, optionally after a short stub of wire.

        The tag is widened to fit its text, since schemdraw's default tag is
        narrow enough that anything longer than a rail name spills outside the
        outline. Long descriptions belong in `note`, printed as plain text in
        the column at `note_x`, so the tags themselves stay short.
        """
        pos = at
        if stub:
            ln = getattr(elm.Line(), direction)().at(at).length(stub)
            self.d.add(ln)
            pos = ln.end
        width = max(1.1, 0.26 * len(label) + 0.5)
        tag = (getattr(elm.Tag(width=width), direction)()
               .at(pos).label(label).color(color))
        self.d.add(tag)
        if note is not None:
            self.note(note_x, pos[1], note, GREY, 'right')
        return tag

    def pad(self, x, y):
        """Invisible anchor so edge tags/labels are not clipped on export."""
        self.note(x, y, '.', 'white')


#: Set by gen_full_schematic.py, which runs the other generators only to collect
#: their Drawing objects and would otherwise rewrite all four SVGs as a side
#: effect of importing them.
SUPPRESS_SAVE = False


def save(d, stem):
    """Write <stem>.svg next to the generators (paths are repo-relative)."""
    if SUPPRESS_SAVE:
        return
    out = f'docs/{stem}.svg'
    d.save(out)
    print(f'wrote {out}')
