# Power rails — design rationale

> **KiCad is the source of truth.** The circuit itself lives on three sheets
> of `ki_cad_project/farseer/`: **`power_protection.kicad_sch`** (battery
> input `J2`, fuse `F1`, load-dump clamp `D2`, reverse-polarity FET `Q1`,
> pi filter `L1`/`C31`–`C33`, front-end reservoir `C7`),
> **`3v3_cell.kicad_sch`** (`U3` TPS54560-Q1 → `3V3_CELL`), and
> **`3v3_sys.kicad_sch`** (`U2` LMR16006X → `3V3_SYS`). The modem's burst
> reservoir (`C57`–`C59`) sits on `cellular.kicad_sch`, at the socket where
> the current is drawn. This document records the sizing arithmetic and
> trade-offs behind those values. If a value here ever disagrees with KiCad,
> KiCad wins.

Trigger for the reservoir analysis: §3.2 of
`datasheets/Quectel_BG95-M3_Mini_PCIe_Hardware_Design_V1.0.pdf` requires *"a
low-ESR bypass capacitor **no less than 470 µF**"* at the card's 3.3 V input.

---

## 1. What the socket capacitors actually do

The division of labour at the Mini PCIe socket (all on `cellular.kicad_sch`):

| Refs | Job | Frequency domain |
|------|-----|------------------|
| `C57`–`C59` (3 × 220 µF polymer) | Burst energy reservoir | Low — sized by charge |
| `C60`/`C61` (10 µF + 100 nF) | HF decoupling at the power pins | High — sized by impedance |
| `C54`–`C56` (33 pF) | Quectel Figure 3 RF ladder | RF |
| `C7` (on `power_protection`) | Front-end load-dump reservoir, harness side | Untouched by this analysis |

The reservoir is deliberately **at the socket, not at the converter** — the
22 µF ceramics at `U3` (`C43`–`C45`) are only local output capacitance.

## 2. Droop budget

The card accepts **3.0–3.6 V, typ 3.3 V** (Table 21, Mini PCIe design guide).
Feeding 3.3 V leaves 300 mV to the lower limit, but not all of it is
available for droop:

| Term | Allocation | Note |
|------|-----------|------|
| Total 3.3 V → 3.0 V | **300 mV** | Hard floor |
| Buck setpoint tolerance (±2%) | −66 mV | Reference + 1% divider tolerance |
| Output ripple (design target 30 mV p-p) | −30 mV | |
| **Available for transient droop** | **≈ 204 mV** | |

Allocate roughly 20 mV to ESR and the remainder to capacitance.

## 3. ESR term — evaluated first

ESR drop is instantaneous and **no amount of capacitance reduces it**:

```
dV_esr = I_burst × ESR = 2.7 A × ESR
```

| Effective ESR | Drop at 2.7 A |
|---------------|---------------|
| 25 mΩ | 68 mV |
| 20 mΩ | 54 mV |
| 8 mΩ | 22 mV |

This is why **several smaller polymer capacitors in parallel beat one large
aluminium electrolytic**: paralleling N identical devices divides both ESR
and ESL by N. A single 470 µF aluminium part would satisfy the capacitance
number while landing in the 25 mΩ-plus range and eating a third of the droop
budget on its own. Target: **effective ESR ≤ 10 mΩ**, giving ≤ 27 mV.

## 4. Capacitance term

The reservoir does **not** have to supply the whole 2G burst. `U3` is a 5 A
converter and can carry 2.7 A continuously; the capacitors only bridge the
interval before the control loop responds:

```
dV_c = I_burst × t_response / C
```

With ~184 mV left after the ESR allocation:

| Loop response `t` | Minimum C |
|-------------------|-----------|
| 10 µs | 147 µF |
| 20 µs | 293 µF |
| 30 µs | 440 µF |
| 50 µs | 734 µF |

This is the sanity check that makes Quectel's number make sense: **470 µF
corresponds to roughly 30–50 µs of full-current response**, about right for
their reference design's MIC29302 **LDO**. A TPS54560-Q1 switching at 500 kHz
responds faster, so 470 µF is conservative here — but it is the stated
minimum and we meet it.

Two effects that do **not** bind:

- **Inductor slew.** At 12 V in, 3.3 V out, 10 µH (`L3`), current slews at
  (12 − 3.3)/10 µH ≈ 0.87 A/µs, so 2.7 A takes ~3.1 µs. The control loop,
  not the inductor, is the limit.
- **Burst-to-burst recharge.** A GSM slot is 577 µs within a 4.615 ms frame,
  leaving ~4 ms and ~2.3 A of spare converter capability to recharge. Ample.

## 5. Selection — why 3 × 220 µF

| Term | Value |
|------|-------|
| Capacitance | 660 µF |
| Effective ESR (3 × ~20 mΩ in parallel) | ≈ 6.7 mΩ |
| ESR drop at 2.7 A | ≈ 18 mV |
| Capacitive droop at t = 20 µs | ≈ 82 mV |
| **Total estimated droop** | **≈ 100 mV** vs 204 mV available |

Comfortably inside budget, clears the 470 µF floor with margin, and three
parallel parts keep ESR and ESL low. **Rejected alternatives:** 5 × 100 µF
(lowest ESR, but most board area and placement effort for margin already
sufficient) and 2 × 330 µF (fewest parts, highest ESR of the three options).

Verify at purchase: ESR specified at 100 kHz for the actual MPN, ripple
current rating covers the burst, voltage rating derates acceptably at 3.3 V.

## 6. `3V3_CELL` loop compensation — re-derived for 660 µF

Tripling the output capacitance moved the converter's loop, so compensation
was not a "finalize during capture" item. With `R_load = 3.3 V / 2.7 A ≈
1.22 Ω`, the output pole moved from ≈ 651 Hz (at the original 200 µF) down to
≈ **197 Hz** at 660 µF, and the ESR zero sits at
`1 / (2π × 6.7 mΩ × 660 µF) ≈ 36 kHz`.

The compensation network in KiCad (`R47`, `C46`, `C47` on
`3v3_cell.kicad_sch`) **was re-derived for this** — the Design Notes on those
parts record the TPS54560-Q1 datasheet equations used: Equation 46 for
mid-band gain with Cout ≈ 700 µF (660 µF polymer plus derated local ceramic)
at a 4.4 kHz target crossover, Equation 47 placing the zero at the ~207 Hz
modulator pole, and Equation 48 for the high-frequency pole against the
34 kHz ESR zero. Re-run those equations if the reservoir ever changes again.

**Soft-start / inrush — still verify at bring-up.** Charging 660 µF adds
`I = C × dV/dt` on top of the load current:

| Soft-start time | Added inrush |
|-----------------|--------------|
| 2 ms | 1.09 A |
| 5 ms | 0.44 A |
| 10 ms | 0.22 A |

Target **≥ 5 ms**, keeping the extra inrush under half an amp and clear of
the current limit. Confirm what the TPS54560-Q1's SS/TR arrangement in KiCad
actually delivers — the constants are TI-specific and must be read from the
datasheet, not assumed.

**`EN` sequencing still works.** Soft-start of a few milliseconds is
irrelevant next to the modem's own multi-second boot, so gating the rail from
`CELL_PWR_EN` (PIC RE0, through the series resistor into `U3` EN) behaves as
described in [interconnect-and-pin-budget.md](interconnect-and-pin-budget.md).
The EN pull-down (see its Design Note in KiCad) keeps the card off while the
PIC is in reset.

## 7. `3V3_SYS` and the NEO-M9N ramp — checked, unaffected

The NEO-M9N is on `U2` (LMR16006X), a separate converter, so nothing above
changes its behaviour. Stated explicitly because the constraint is
**part-damaging** rather than merely out of spec.

NEO `VCC` ramp must be **20–8000 µs/V** (Datasheet Table 10; note 7: too fast
*"may permanently damage the device"*). For a 0 → 3.3 V rise:

| Bound | Ramp rate | Rise time |
|-------|-----------|-----------|
| Fastest allowed | 20 µs/V | **66 µs** |
| Slowest allowed | 8000 µs/V | **26.4 ms** |

Action at bring-up: measure the LMR16006X's soft-start ramp on `3V3_SYS` and
confirm it falls inside that window. Internal soft-start is typically a few
hundred microseconds to a few milliseconds, comfortably mid-range, but **the
fast bound is the dangerous one** — do not fit a fast-start variant or bypass
soft-start. If output capacitance on this rail ever grows, re-check the slow
bound too.

Related constraint from the NEO integration manual (§4.2.1): series
resistance in the VCC line must stay **below 0.2 Ω**, which makes `FB1` on
`gps.kicad_sch` a DCR-selected part, not just an impedance-selected one — see
[gnss-support-circuit.md](gnss-support-circuit.md).

## 8. Q1 reverse-polarity pass FET

`Q1` sits on `power_protection.kicad_sch` between the fused battery node
(`D2` cathode) and the pi-filter input (`L1`). It carries the **whole board
input current** — `L1`'s Design Notes already put that at **~2.5 A worst
case at 7 V in**, and `F1` is 5 A.

The original `DMP6110SFDF` (U-DFN2020-6 Type F, 110 mΩ max @ −10 V, −3.5 A)
dissipated **I²R ≈ 0.69 W** in a 2 × 2 mm DFN at that current. That was the
thermal bottleneck, not the gate network (`R41` + `D1` 10 V clamp; `VGSS` is
still ±20 V).

KiCad now uses `DMP6023LFGQ-13` (PowerDI3333-8, AEC-Q101):

| | Old `DMP6110SFDF` | New `DMP6023LFGQ` |
|---|---|---|
| `RDS(on)` max | 110 mΩ @ −10 V | 25 mΩ @ −10 V / 33 mΩ @ −4.5 V |
| Continuous `ID` | −3.5 A | −7.7 A (25 °C) / −6.2 A (70 °C) |
| Dissipation at 2.5 A | 0.69 W | 0.16–0.21 W |
| Package | 2.0 × 2.0 mm DFN | 3.3 × 3.3 mm PowerDI3333-8 |

At 2.5 A and 33 mΩ, even the datasheet minimum-pad `RθJA` of 123 °C/W
(Note 5) is only ~26 °C rise. `VDSS` is still −60 V, which clears the
`SM8S26A` clamp at ~42 V. Pinout is **not** the old DFN: pins 1–3 source,
pin 4 gate, pad 5 merged drain tab.
