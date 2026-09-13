# NEO-M9N support circuit — design rationale

> **KiCad is the source of truth.** The circuit itself — parts, values, nets,
> footprints, MPNs — lives on the **`gps` sheet**
> (`ki_cad_project/farseer/gps.kicad_sch`: module `U4`, antenna connector
> `J3`, ESD `D5`, supply ferrite `FB1`, bias-T `L4`/`C52`/`R50`, decoupling
> `C48`–`C51`). This document records only the reasoning a schematic cannot
> carry. If a value here ever disagrees with KiCad, KiCad wins.

Authoritative device sources:

- `datasheets/NEO-M9N-00B_DataSheet_UBX-19014285.pdf` — electrical limits,
  pin definitions, package mechanicals.
- `datasheets/NEO-M9N_Integrationmanual_UBX-19014286.pdf` (**R10**, "IM") —
  the design chapter: power supply, minimal design, antenna circuits,
  footprint, layout.

---

## 1. Package — LCC, not LGA

The NEO form factor is a 24-pin **LCC** (leadless chip carrier) with 1.1 mm
pitch perimeter castellations (Datasheet §6, Table 20, Figure 5). This is a
friendly package to assemble: pads run along the outside edges, not under the
body, so joints are visible and probeable; there is no hidden thermal pad and
nothing needs X-ray inspection. Reflow with a stencil is ideal; hot air works.

Two footprint notes: use the suggested copper and paste-mask geometry from
IM §4.8.3 (Figures 37 and 38) rather than rolling your own, and allow keep-out
for the **de-paneling residual tabs** (up to 0.5 mm) that may protrude on one
long edge (Datasheet §6 note, p. 17).

## 2. Pin handling — the two that defy the "leave open" rule

The pin-by-pin connections are the `U4` symbol in KiCad. The datasheet's
baseline rule (§5, p. 12) is that *"all the inputs have internal pull-up
resistors in normal operation and can be left open if not used"* — with traps:

- **`D_SEL` (pin 2) must not be grounded.** Open selects UART + I2C (what the
  firmware uses); GND selects SPI. No external resistor needed — the internal
  pull-up is 30–130 kΩ.
- **`V_USB` (pin 7) must be tied to GND**, not left open — see §4.
- Reserved pins 15–17: do not connect.
- `RESET_N` (pin 8) has an internal 7–13 kΩ pull-up and no external RC is
  specified; it is driven open-drain from the PIC (`GNSS_RESET`).
- `TIMEPULSE` (pin 3) is routed (`GNSS_1PPS`) even though firmware does not
  use it yet — see §6.

## 3. Main supply (VCC)

Key electrical facts (Datasheet Tables 10–12): operating range 2.7–3.6 V,
**100 mA** acquisition peak, 28–50 mA average. Three constraints that are
easy to violate:

- **Series resistance in the VCC line must stay under 0.2 Ω.** IM §4.2.1 and
  §4.9.1: anything more generates input voltage noise under dynamic current.
  This directly constrains `FB1`, the ferrite on the GNSS branch — it was
  **selected for DCR below 0.2 Ω**, not just for its 600 Ω @ 100 MHz
  impedance. A typical bead of that impedance class can easily exceed 0.2 Ω;
  check DCR on any substitution.
- **The VCC ramp rate is a part-damaging spec.** 20–8000 µs/V (Table 10)
  means a 0 → 3.3 V rise must take between **66 µs and 26.4 ms**; too fast
  *"may permanently damage the device"* (note 7). The `3V3_SYS` buck (`U2`,
  LMR16006X) has internal soft-start; its ramp is checked against this window
  in [power-support-circuit.md](power-support-circuit.md), and must be
  re-checked if the rail's output capacitance ever changes.
- **The VCC pad wants copper, not a thin trace.** IM §4.8.4.2: large pad, low
  impedance, large vias to the power layer, with the 1 µF (`C50`) as close to
  the pad as physically possible. `C49` is the HF companion; `C48` is the
  local reservoir for the 100 mA acquisition peak.

## 4. V_BCKP and V_USB — "unused" does not mean "open"

**V_USB must be tied to GND.** IM §4.2.3: *"If the USB interface is not used,
the V_USB pin must be connected to GND."* Repeated in the §4.3 minimal design
and the §4.9.1 checklist. This is **not** covered by the inputs-may-float
rule.

**V_BCKP is tied to VCC** (IM §4.2.2: *"If no backup supply voltage is
available, connect the V_BCKP pin to VCC"* — never floating). What that
choice costs: without an independent backup source the receiver **cold-starts
at every power-up**, roughly 24–29 s to first fix versus a couple of seconds
hot (Datasheet Table 2) — felt every time the car is keyed off in the
paddock. Backup current is only 45 µA typ at 3 V, so a hold cap or supercap
is a cheap future upgrade; `C51` sits on the V_BCKP tie today.

Two rules if a real backup source is ever fitted:

- **No series resistance on V_BCKP** — the main-to-backup switchover draws a
  short current peak that a resistive path turns into a damaging drop
  (IM §4.2.2).
- In hardware backup mode (V_BCKP alive, VCC down), *"all I/O including
  UART"* must float or be high-impedance, or the chip gets parasitically
  powered through its own pins — the PIC's RD0 must not drive the NEO's RXD
  while the NEO's VCC is down. Today both parts share `3V3_SYS` and power
  down together, so the situation does not arise; it becomes a real
  constraint if GNSS ever moves to a switched rail.

## 5. RF front end — passive and active from one layout

Design goal: **either antenna works**, selected by populate / no-fit of the
bias-T (`L4`, `C52`, `R50`).

### What the module already provides

IM §4.4.3 and §4.5: a **SAW filter**, an **LTE band 13 notch filter**, and an
**LNA** on-module — with the SAW *before* the LNA, so strong out-of-band
interferers cannot saturate it — plus *"an internal DC block and 50 Ω
impedance matching for GNSS signal input."*

So **do not fit a DC block or a matching network on RF_IN** — both are
already inside — and an inexpensive passive antenna genuinely works (§4.5).
The internal SAW-first ordering matters in this vehicle: the BG95 transmits
at up to ~22 dBm from an antenna that may be tens of centimetres from the
GNSS antenna, and out-of-band immunity is a constant +13 dBm except close to
the GNSS band (IM §4.5.3, Figure 34).

### Bias-T choices (active-antenna case)

- **Why `L4` is 47 nH, not the 27 nH in IM Figure 33.** The governing spec is
  impedance **> 500 Ω at the GNSS frequency** (~1575 MHz) at > 300 mA; the
  47 nH part meets it with margin where a generic 27 nH can fall short.
  Verify the impedance curve, not just the inductance, on any substitution.
- **Why `R50` is 22 Ω and not the 10 Ω in IM Table 26.** The text below
  Table 26 qualifies it: when the module supplies bias from `VCC_RF`, short
  circuit current must stay below 150 mA — *"a value of 19 Ω or more is
  required at a module supply of 3.3 V."* 22 Ω is the nearest standard value.
  Check the power rating for the sustained-short case, and remember the
  bias-T inductor DCR (1–2 Ω) and the module's internal feed inductor (1.2 Ω)
  are part of that loop. The antenna feed is the most likely thing to short
  in a race car — a chafed coax against bodywork does it — and this resistor
  is what stops that from destroying the bias-T inductor or the module's
  internal feed.
- `VCC_RF` outputs VCC − 0.1 V at up to 50 mA operating (200 mA abs max),
  comfortably covering the 5–20 mA a typical active antenna draws
  (IM §4.5.2). `LNA_EN` is **active high**. If a future active antenna needs
  a voltage other than 3.3 V, IM §4.5.2 says to use a filtered external
  supply rather than `VCC_RF`.
- **Passive antenna:** no DC bias needed — the antenna connects straight to
  RF_IN (§4.5.1); the bias-T goes no-fit.

### ESD and layout

`D5` (PESD0402-140, low-capacitance, GNSS-band rated) sits at the antenna
connector: IM §4.5.2 requires ESD at the input, and an external RF connector
is a conduction path for destructive signals (§4.9.3). `J3` is a 50 Ω SMA
through-hole right-angle jack for the roof/shell antenna feed — Amphenol RF
`132136`, drawing `SMA6252A2-3GTSGP-50`, filed as
`datasheets/components/J3/Amphenol_132136_SMA6252A2-3GTSGP-50.pdf`. That
PDF is an image-only drawing with no text layer: `pdftotext` returns
nothing, so rasterise it (`pdftoppm -r 200 -png`) to read it.

RF_IN trace rules (IM §4.8.4.1), layout-review pass/fail:

- Grounded co-planar waveguide referenced to layer 2, matched to 50 Ω.
- Via-shield the trace along its entire length; surround the RF_IN pad.
- No stubs; any RF component close to the RF_IN pin.

**Sizing basis (the numbers KiCad carries).** The board is built on the
JLCPCB **JLC04161H-7628** 1.6 mm 4-layer stack: 35 µm top copper over a
single 7628 prepreg, **h = 0.2104 mm, εr 4.4** (JLC impedance-control
spec), to the L2 ground plane. On that stack the grounded CPW of
**W = 0.34 mm, gap S = 0.45 mm** to the F.Cu ground pour, referenced to
In1.Cu, field-solves to **49.8–51.1 Ω** (`scripts/rf_impedance.py line`).
The two figures are the same cross-section solved with electric-wall and
magnetic-wall outer boundaries; they bracket the open-region answer, and
the model cannot resolve inside that ±1 Ω, so quoting a single number here
would overstate what is known. Width is held by the `RF_IN` netclass, gap
by the `GNSS_RF_CPW` rule in `farseer.kicad_dru`.

Two things in that solve are easy to leave out and cost real ohms:

- **Soldermask is worth ≈ 4 Ω.** Bare copper solves to 54–55 Ω; with 20 µm
  of εr 3.6 mask over and between the conductors it drops to the figure
  above. A calculator that ignores mask will tell you this trace is high and
  push you to widen it — do not.
- **Copper thickness** is included (35 µm). Zero-thickness closed forms read
  1–2 Ω higher again.

Cross-check against the fab's own numbers for this exact stackup: JLC's
calculator returns 0.330 mm width for a 0.340 mm gap at 50 Ω, and a
0.345 mm / 0.508 mm design on the same stack has been VNA-verified to
3 GHz. Both sit within 1 Ω of the 0.34 / 0.45 mm drawn here, so the width
was left alone. Confirm on the order form anyway — JLC does the etch
compensation and measures the coupon, so their model wins if it disagrees.

Sensitivity (same solver, one variable at a time from nominal):

| variable | range | Z0 |
|---|---|---|
| prepreg height | ±10 % | 48.4 – 53.6 Ω |
| trace width | ±0.02 mm etch | 52.6 – 49.6 Ω |
| prepreg εr | 4.2 – 4.6 | 52.0 – 50.2 Ω |
| gap | 0.30 – 0.70 mm | 49.8 – 51.7 Ω |

Prepreg height dominates and is the one you cannot see on the Gerbers.
**This is why the board is ordered with JLC's controlled-impedance option
and the stackup pinned to JLC04161H-7628** — they hold ±10 % against their
measured stack; without it the prepreg tolerance alone spreads Z0 across
48–54 Ω, more than everything else on this page combined. The order-time
spec is `docs/generated/farseer-impedance-spec.txt`, regenerated by
`scripts/export_kicad.sh` from the netclass, the rule and the stackup so it
cannot drift from the board, and a matching note sits on `User.Comments`
beside the trace. The gap is a weak knob and exists for shielding, as the IM
asks, not for tuning.

Two traps this replaces:

- The 0.2 mm width the net started life with is a zero-thickness result on a
  0.1 mm prepreg. With 35 µm copper it is ~42–45 Ω on that stack and
  **~63–68 Ω on the JLC stack**. Prepreg height dominates: change fab or
  stack and re-run `scripts/rf_impedance.py` before touching anything else.
- The run is **26.6 mm**, and at L1 (1575.42 MHz) λ0 = 190 mm, εeff ≈ 3.4,
  so **λg ≈ 103 mm** and the trace is **≈ λ/4 (93°)**. A quarter-wave line
  shows any Z0 error at full strength (Z_in = Z0²/50): the old 0.2 mm trace
  would have presented 79–92 Ω to the module (RL 11–13 dB, 0.2–0.4 dB lost
  ahead of the LNA). At the fab's ±10 % the worst case is Z_in ≈ 40 or 60 Ω,
  RL ≈ 20 dB, a few hundredths of a dB. Getting Z0 right matters more here
  than on a short stub would, but the controlled-impedance order is what
  makes it stick.

**`J3` launch.** The pin-1 through-hole is the one discontinuity on the line
that was genuinely off, and it was not visible from the pad outline. An
axisymmetric solve of the whole launch (`scripts/rf_impedance.py launch`:
plated barrel through the full 1.6 mm, both annular pads, both inner planes,
both outer pours) put the stock footprint at **1.21 pF, ≈ 12.7 dB return
loss**. The dominant term is the 1.5 mm barrel coupling coax-fashion to the
In1/In2 plane edges, and that edge was only 2.406 mm across — the pad has
`remove_unused_layers`, so KiCad measured the 0.45 mm clearance from the
hole, not the pad, which made the inner antipad *smaller* than the outer
pour opening. Two changes, both applied by `scripts/apply_rf_tuning.py`:

- **Pin 1 is a 2.05 mm circle, not the stock 2.3 mm roundrect.** Same
  1.5 mm hole. The dimension is KiCad's own pin-1 pad for the vertical
  members of this Amphenol family (`901-144`, `132134`); the `132136`
  drawing specifies holes only (Ø1.5 centre, 4 × Ø1.7 on a 5.08 mm square,
  Ø1.27 pin) and every one of them already matched, so nothing mechanical
  moved. Annular ring 0.275 mm against JLC's 0.15 mm minimum. Do not swap in
  the vertical footprint itself — `J3` is the right-angle jack and the
  vertical outline, courtyard and 3D model are wrong for it.
- **Rule area `J3_RF_ANTIPAD`: 3.0 mm circle, In1.Cu + In2.Cu only, no
  copper pour.** Coax capacitance goes as 1/ln(b/a), so 2.4 → 3.0 mm is
  worth 0.22 pF, 3.0 → 4.0 mm only 0.06 pF, and past that nothing. 3.0 mm is
  the knee, and it stops before the void undercuts the trace (0.35 mm past
  the pad edge, ≈ 1° electrical) or crowds the four ground barrels (inner
  pad edges at 2.34 mm radius). F.Cu and B.Cu keep their pours: the bottom
  ring is the solder joint and both outer pours are the coplanar reference.

Together: 1.21 → 0.77 pF, **≈ 12.7 → 17.9 dB** return loss, net of the
0.25 pF a 50 Ω line carries over that footprint anyway. That is where to
stop — the connector is specified at VSWR 1.3 max (17.7 dB) over DC–6 GHz,
so the launch is no longer the limit. The whole change is worth under
0.2 dB of signal; it is cheap and correct, not decisive.

Via fence: 0.6 mm / 0.3 mm GND vias, centres ≈ 1.1 mm off the trace axis on
both sides, pitch ≤ 1.6 mm along the run (λg/20 ≈ 5.2 mm is the ceiling),
including the `D5`/`L4`/`J3` stretch. A pair at 1.4 mm from the `J3` pin
closes the gap before the fence proper starts at 3.6 mm; the connector's
own ground barrels at 2.54 mm offset bracket the pad as the IM asks. `D5`
and `L4` tap the line with their pads centred on the trace axis, so they add
shunt capacitance (~0.6 pF, RL ≈ 17 dB) but no stub. The 0.8 mm-wide `U4`
RF_IN pad is an inherent, electrically short (<10°) discontinuity and is
left alone.

Absolute limits: in-band 0 dBm, out-of-band +13 dBm, and **max external gain
30 dB** (Tables 10/11 note 8). A high-gain active antenna plus an extra LNA
can exceed 30 dB — do not stack them.

## 6. UART to the PIC

Direct connection, no level shifting, no series resistors specified. Default
**38400 baud, 8N1** NMEA (Table 19), matching the bring-up sequence in
[gps.c](../gps.c), which then negotiates to 115200 for 25 Hz operation.
Levels at 3.3 V are comfortably compatible both ways (Vih = 0.8 × VCC =
2.64 V; outputs swing within 0.4 V of the rails); max 5 mA per digital I/O;
**no hardware flow control** exists (Datasheet §5.1).

`TIMEPULSE` (`GNSS_1PPS`) is routed even though firmware does not use it yet:
1 PPS with **30 ns RMS** accuracy gives a way to discipline timestamps far
better than UART arrival time — exactly what correlating position to lap
timing wants.

---

## 7. Bring-up checklist (process, not values)

- [ ] Populate decision made: passive (bias-T no-fit) vs. active (`L4`,
      `C52`, `R50` fitted, `VCC_RF`/`LNA_EN` in play)
- [ ] `3V3_SYS` ramp verified inside 66 µs – 26.4 ms for the 0 → 3.3 V rise
- [ ] Any `FB1` substitution re-checked for DCR < 0.2 Ω
- [ ] RF_IN laid out as a via-shielded grounded co-planar 50 Ω waveguide,
      no stubs, no DC block, no matching network
- [ ] RF_IN geometry re-checked against the fab stack actually ordered:
      W 0.34 mm / S 0.45 mm assumes JLC04161H-7628 (0.2104 mm 7628 prepreg,
      εr 4.4); any other prepreg height changes the width
- [ ] Footprint and paste mask taken from IM Figures 37/38, with de-panel tab
      keep-out on the long edge
- [ ] Total external gain ≤ 30 dB — no active antenna stacked with an extra
      LNA
- [ ] GNSS antenna sited as far as practical from the BG95 antenna (see
      [procurement.md](procurement.md))
