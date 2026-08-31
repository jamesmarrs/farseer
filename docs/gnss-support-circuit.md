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
through-hole right-angle jack for the roof/shell antenna feed.

RF_IN trace rules (IM §4.8.4.1), layout-review pass/fail:

- Grounded co-planar waveguide referenced to layer 2, matched to 50 Ω.
- Via-shield the trace along its entire length; surround the RF_IN pad.
- No stubs; any RF component close to the RF_IN pin.

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
- [ ] Footprint and paste mask taken from IM Figures 37/38, with de-panel tab
      keep-out on the long edge
- [ ] Total external gain ≤ 30 dB — no active antenna stacked with an extra
      LNA
- [ ] GNSS antenna sited as far as practical from the BG95 antenna (see
      [procurement.md](procurement.md))
