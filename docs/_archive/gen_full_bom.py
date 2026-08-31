#!/usr/bin/env python3
"""Assemble the whole-board BOM from the four per-block BOMs.

    docs/power-supply-bom.md   docs/mcu-bom.md
    docs/cellular-bom.md       docs/gnss-bom.md
        |
        +--> docs/full-bom.md    one ordering list, de-duplicated
        +--> docs/full-bom.csv   the same rows, flat, for a spreadsheet

Those four files stay the single source of truth for parts and values; this
script only reads them, so the combined list cannot drift from them. It is the
BOM counterpart of gen_full_schematic.py, which assembles the whole-board
drawing from the four schematic generators.

The interesting part is de-duplication. Several groups are deliberately carried
in TWO of the source files - the BG95 socket group and the 3V3_SYS distribution
group appear in power-supply-bom.md as rail distribution and again in the
subsystem BOM that consumes them - and each is one physical part to buy once.
DUPLICATES below names every one of those, and the script fails if it finds a
reference designator in two files that is not declared there, so a part added
to one file and forgotten in another cannot silently double up.

Run from the repo root:  python3 docs/gen_full_bom.py
"""
import csv
import pathlib
import re
import sys

DOCS = pathlib.Path('docs')

#: Rows of the 'Approximate cost' table in power-supply-bom.md that price parts
#: owned by another block - the same overlap DUPLICATES handles for the part
#: rows. Excluded from the board total so those parts are costed once.
COST_DUPLICATES = {
    'power': ('Mini PCIe socket + SIM holder + reservoir caps',
              '`3V3_SYS` distribution (ferrite + decoupling)'),
}

#: key -> (source file, heading used in the combined BOM)
BLOCKS = [
    ('power', 'power-supply-bom.md', 'Power  -  vehicle input, protection, two bucks'),
    ('mcu', 'mcu-bom.md', 'MCU  -  PIC18F57Q84, reset, ICSP, USB console'),
    ('cellular', 'cellular-bom.md', 'Cellular  -  BG95-M3 Mini PCIe, SIM, USB'),
    ('gnss', 'gnss-bom.md', 'GNSS  -  NEO-M9N, supply, RF front end'),
]

#: Rows carried in two source files. (file, ref) is dropped in favour of
#: (owner file, owner ref); they are the same physical parts. An owner ref of
#: None means the owning file documents it in a row with no designator - a net
#: rather than a part.
DUPLICATES = [
    ('power', 'J2', 'cellular', 'J2'),
    ('power', 'C10, C11', 'cellular', 'C10, C11'),
    ('power', 'C12, C13', 'cellular', 'C12, C13'),
    ('power', 'C14, C15', 'cellular', 'C14, C15'),
    ('power', 'J3', 'cellular', 'J3'),
    ('power', 'FB2', 'gnss', 'FB2'),
    ('power', 'C_neo1, C_neo2', 'gnss', 'C_neo1'),
    ('power', 'C_neoBulk', 'gnss', 'C_neoBulk'),
    ('power', 'C_bkp', 'gnss', 'C_bkp'),
    ('power', 'C_vusb', 'gnss', None),
    ('power', 'C_pic', 'mcu', 'C_pic1'),
    ('power', 'C_picBulk', 'mcu', 'C_picBulk'),
]

#: Groups where fitting one option means NOT fitting the other, so the totals
#: below would otherwise count parts that never coexist on a board.
EXCLUSIVE = [
    ('GNSS antenna feed', ['L_bias', 'C_bias', 'R_bias'], ['R_bias0'],
     'active antenna (bias-T) or passive antenna (0 ohm link) - populate one'),
]

TABLE_HEADER = ('Ref', 'Qty', 'Status', 'Value / description')


class Row:
    def __init__(self, block, section, cells):
        self.block = block
        self.section = section
        self.ref, self.qty, self.status, self.value, self.mpn, self.notes = cells

    @property
    def key(self):
        return (self.block, self.ref)


def parse_bom(block, path):
    """Pull every six-column BOM row out of one markdown file, with its
    section heading. Anything that is not a six-column table row - the prose,
    the pin-map tables, the cost table - is skipped."""
    rows, section = [], '(top)'
    for line in path.read_text().splitlines():
        if line.startswith('## '):
            section = line[3:].strip()
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) != 6:
            continue
        if tuple(cells[:4]) == TABLE_HEADER:
            continue
        if set(''.join(cells)) <= set('-: '):     # the |---|---| separator
            continue
        rows.append(Row(block, section, cells))
    return rows


def parse_costs(path):
    """The two-column 'Approximate cost' table at the end of each file."""
    rows, in_costs = [], False
    for line in path.read_text().splitlines():
        if line.startswith('## '):
            in_costs = line[3:].strip().lower().startswith('approximate cost')
            continue
        if not in_costs or not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) != 2 or cells[0] == 'Block':
            continue
        if set(''.join(cells)) <= set('-: '):
            continue
        rows.append(cells)
    return rows


def plain(text):
    """Markdown to bare text: drop emphasis and code ticks, keep link labels."""
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    return text.replace('**', '').replace('`', '').strip()


def first_url(text):
    m = re.search(r'\]\((https?://[^)]*)\)', text)
    return m.group(1) if m else ''


def qty_range(text):
    """(low, high) from the qty column. high is None for an open-ended '0-n'.

    Quantities are written for humans: '2', '**3**', '0-2' for fit-if-needed,
    '2-3' where a part count is still open, '1+1' for an R-C pair, '0-n' for
    as-many-as-you-need. The low end is what a board needs to work, so that is
    what the totals use.
    """
    t = plain(text).replace('\u2013', '-').replace('\u2014', '-')
    if '+' in t:
        return (sum(int(n) for n in re.findall(r'\d+', t)),) * 2
    m = re.match(r'^(\d+)\s*-\s*(\d+|n)$', t)
    if m:
        return int(m.group(1)), None if m.group(2) == 'n' else int(m.group(2))
    m = re.match(r'^(\d+)$', t)
    if m:
        return int(m.group(1)), int(m.group(1))
    return 0, 0


def money_range(text):
    """(low, high) in dollars from a cost cell: '~$6–9', '~$1', '<$0.50'."""
    t = plain(text).replace('\u2013', '-').replace('\u2014', '-')
    nums = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', t)]
    if not nums:
        return 0.0, 0.0
    if len(nums) == 1:
        return (0.0, nums[0]) if '<' in t else (nums[0], nums[0])
    return nums[0], nums[1]


def board_cost(costs):
    """Board total: every per-block cost row except the running totals and the
    rows that price another block's parts."""
    lo = hi = 0.0
    for block, _, _ in BLOCKS:
        for label, price in costs[block]:
            if 'Total' in label or label in COST_DUPLICATES.get(block, ()):
                continue
            a, b = money_range(price)
            lo, hi = lo + a, hi + b
    return lo, hi


def status_class(text):
    """Req / Rec / Opt, from a status cell that may carry emphasis or a
    condition ('Req if D_wwan fitted')."""
    t = plain(text)
    for cls in ('Req', 'Rec', 'Opt'):
        if t.startswith(cls):
            return cls
    return '?'


def main():
    if not DOCS.is_dir():
        sys.exit('error: run from the repo root (docs/ not found)')

    parsed = {key: parse_bom(key, DOCS / name) for key, name, _ in BLOCKS}
    costs = {key: parse_costs(DOCS / name) for key, name, _ in BLOCKS}

    # --- de-duplicate, and refuse to guess -------------------------------
    dropped = {}
    for src, ref, owner, owner_ref in DUPLICATES:
        if not any(r.ref == ref for r in parsed[src]):
            sys.exit(f'error: DUPLICATES names {src}:{ref}, which no longer exists')
        if owner_ref and not any(r.ref == owner_ref for r in parsed[owner]):
            sys.exit(f'error: DUPLICATES points {src}:{ref} at {owner}:{owner_ref}, '
                     'which no longer exists')
        dropped[(src, ref)] = (owner, owner_ref)

    rows = [r for block, _, _ in BLOCKS for r in parsed[block]
            if r.key not in dropped]

    # Any designator still appearing in two files is an undeclared duplicate.
    seen = {}
    for r in rows:
        if r.ref in ('—', '-', ''):
            continue
        seen.setdefault(r.ref, []).append(r.block)
    clashes = {ref: b for ref, b in seen.items() if len(b) > 1}
    if clashes:
        for ref, blocks in clashes.items():
            print(f'error: {ref} appears in {" and ".join(blocks)} but is not '
                  'declared in DUPLICATES', file=sys.stderr)
        sys.exit(1)

    write_markdown(rows, dropped, costs)
    write_csv(rows)


def totals(rows):
    """Line items and part counts per status class, using the low end of each
    quantity. Rows with no designator are documentation of a net, not parts."""
    out = {}
    for cls in ('Req', 'Rec', 'Opt', '?'):
        sel = [r for r in rows if status_class(r.status) == cls
               and r.ref not in ('—', '-', '')]
        out[cls] = (len(sel), sum(qty_range(r.qty)[0] for r in sel))
    return out


def write_markdown(rows, dropped, costs):
    o = []
    w = o.append
    w('# Farseer whole-board BOM')
    w('')
    w('**Generated — do not edit.** Written by `gen_full_bom.py` from the four')
    w('per-block BOMs, which remain the single source of truth for parts and')
    w('values. Change a part there and re-run `python3 docs/gen_full_bom.py`.')
    w('')
    w('| Block | Source BOM | Rationale | Schematic |')
    w('|-------|-----------|-----------|-----------|')
    w('| Power | [power-supply-bom.md](power-supply-bom.md) | [power-rail-notes.md](power-rail-notes.md) | [power-rails-schematic.pdf](power-rails-schematic.pdf) |')
    w('| MCU | [mcu-bom.md](mcu-bom.md) | [mcu-support-circuit.md](mcu-support-circuit.md) | [mcu-schematic.pdf](mcu-schematic.pdf) |')
    w('| Cellular | [cellular-bom.md](cellular-bom.md) | [cellular-support-circuit.md](cellular-support-circuit.md) | [cellular-schematic.pdf](cellular-schematic.pdf) |')
    w('| GNSS | [gnss-bom.md](gnss-bom.md) | [gnss-support-circuit.md](gnss-support-circuit.md) | [gnss-schematic.pdf](gnss-schematic.pdf) |')
    w('')
    w('Everything on one sheet: [full-schematic.pdf](full-schematic.pdf).')
    w('A flat version of the table below, for a spreadsheet or a distributor')
    w('upload, is in [full-bom.csv](full-bom.csv).')
    w('')
    w('**Status**: **Req** mandatory, **Rec** strongly recommended for')
    w('robustness or EMC, **Opt** a genuine design choice. A quantity written as')
    w('a range (`0–2`, `2–3`) is one the source BOM leaves open — fit-if-needed')
    w('parts, or values still to be pinned down at schematic capture. Quantity')
    w('`0` marks a row that documents a **net rather than a part** (`V_USB` to')
    w('ground) or a deliberate no-fit (the crystal that is not populated).')
    w('')
    w('---')
    w('')

    # --- totals -----------------------------------------------------------
    t = totals(rows)
    w('## Totals')
    w('')
    w('Counted at the low end of each quantity range, excluding rows that')
    w('document a net rather than a part.')
    w('')
    w('| Status | Line items | Parts |')
    w('|--------|-----------|-------|')
    for cls, label in (('Req', 'Req — mandatory'), ('Rec', 'Rec — recommended'),
                       ('Opt', 'Opt — optional')):
        w(f'| {label} | {t[cls][0]} | {t[cls][1]} |')
    w(f'| **Req + Rec** | **{t["Req"][0] + t["Rec"][0]}** | '
      f'**{t["Req"][1] + t["Rec"][1]}** |')
    w('')
    for name, group_a, group_b, note in EXCLUSIVE:
        w(f'**{name}** is mutually exclusive: `' + '` / `'.join(group_a) +
          '` versus `' + '` / `'.join(group_b) + f'` — {note}. Both appear '
          'below; the totals count both, so subtract whichever you do not fit.')
    w('')
    w('The three modules that dominate cost — `U1` PIC18F57Q84, `U4` NEO-M9N,')
    w('and the BG95-M3 Mini PCIe card itself — are counted as ordinary line')
    w('items here. Note the BG95 card is **not** a line in any BOM: it is the')
    w('module that plugs into `J2`, bought as an assembly.')
    w('')
    w('---')
    w('')

    # --- the tables -------------------------------------------------------
    for block, _, title in BLOCKS:
        block_rows = [r for r in rows if r.block == block]
        if not block_rows:
            continue
        w(f'## {title}')
        w('')
        section = None
        for r in block_rows:
            if r.section != section:
                if section is not None:
                    w('')
                section = r.section
                w(f'### {section}')
                w('')
                w('| Ref | Qty | Status | Value / description | Suggested MPN | Notes |')
                w('|-----|-----|--------|---------------------|---------------|-------|')
            w(f'| {r.ref} | {r.qty} | {r.status} | {r.value} | {r.mpn} | {r.notes} |')
        w('')

    # --- what was merged --------------------------------------------------
    w('---')
    w('')
    w('## Parts carried in two source BOMs')
    w('')
    w('Each of these is **one physical part**, listed twice at the source: once')
    w('in `power-supply-bom.md` as rail distribution, and once in the BOM for')
    w('the subsystem it feeds. The row below was dropped in favour of the')
    w('subsystem row, so it is above exactly once. Order once.')
    w('')
    w('| Dropped from | Ref | Kept in | As |')
    w('|--------------|-----|---------|----|')
    files = {key: name for key, name, _ in BLOCKS}
    for (src, ref), (owner, owner_ref) in dropped.items():
        kept = f'`{owner_ref}`' if owner_ref else 'a net, no designator'
        w(f'| {files[src]} | `{ref}` | {files[owner]} | {kept} |')
    w('')

    # --- cost -------------------------------------------------------------
    w('---')
    w('')
    w('## Approximate cost')
    w('')
    lo, hi = board_cost(costs)
    w('Reproduced from each source BOM. Single-unit distributor list prices,')
    w('order-of-magnitude only, and volatile — expect materially lower in volume.')
    w('')
    w(f'**Board total: ~${lo:.0f}–{hi:.0f}.** Every cost row below except the')
    w('per-block totals, and except the two rows in `power-supply-bom.md` that')
    w('price the socket and `3V3_SYS` parts a subsystem BOM already prices')
    w('(the same overlap the part rows have). `U1` and `U4` are included; the')
    w('**BG95-M3 Mini PCIe card**, the **LTE and GNSS antennas**, the PCB, and')
    w('the enclosure are **not** — none of them is a line in any BOM.')
    w('')
    for block, name, title in BLOCKS:
        if not costs[block]:
            continue
        w(f'### {title.split("  -  ")[0]}  ([{name}]({name}))')
        w('')
        w('| Block | Rough cost |')
        w('|-------|-----------|')
        for a, b in costs[block]:
            w(f'| {a} | {b} |')
        w('')
    w('The four **Total** rows above are each scoped differently — GNSS excludes')
    w('its own module, cellular excludes the card — so they cannot simply be')
    w('added. The board total at the top of this section is the sum that does')
    w('account for that.')
    w('')

    out = DOCS / 'full-bom.md'
    out.write_text('\n'.join(o) + '\n')
    print(f'wrote {out} ({len(rows)} rows)')


def write_csv(rows):
    out = DOCS / 'full-bom.csv'
    with out.open('w', newline='') as fh:
        wr = csv.writer(fh)
        wr.writerow(['block', 'section', 'ref', 'qty', 'qty_min', 'qty_max',
                     'status', 'value', 'mpn', 'datasheet', 'notes'])
        for r in rows:
            lo, hi = qty_range(r.qty)
            wr.writerow([r.block, plain(r.section), plain(r.ref), plain(r.qty),
                         lo, '' if hi is None else hi, status_class(r.status),
                         plain(r.value), plain(r.mpn), first_url(r.mpn),
                         plain(r.notes)])
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
