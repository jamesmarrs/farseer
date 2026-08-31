# Power rail notes — socket reservoir sizing and buck A loop

Working notes behind two changes to `power-supply-bom.md` that the support-circuit
work forced. The rail architecture itself (front-end protection, two bucks,
`3V3_CELL` / `3V3_SYS` split) is unchanged.

Trigger: §3.2 of `datasheets/Quectel_BG95-M3_Mini_PCIe_Hardware_Design_V1.0.pdf`
requires *"a low-ESR bypass capacitor **no less than 470 µF**"* at the card's
3.3 V input, against the ~200 µF originally specified for `C10`/`C11`.

---

## 1. What these capacitors actually do

`C10`/`C11` were always the **burst energy reservoir** ("Sources the TX-burst
current locally at the socket"), not a transient filter. This is a resize of an
existing function, not a new requirement. The division of labour at the socket:

| Ref | Job | Frequency domain |
|-----|-----|------------------|
| `C10`, `C11` | Burst energy reservoir | Low — sized by charge |
| `C12`, `C13` | HF decoupling at the power pins | High — sized by impedance |
| `C14`, `C15` | 33 pF / 10 pF, completes Quectel's Figure 3 ladder | RF |
| `C1` | Front-end load-dump reservoir on the harness side | Untouched |

Only `C10`/`C11` change.

---

## 2. Droop budget

The card accepts **3.0 - 3.6 V, typ 3.3 V** (Table 21, p. 37, Mini PCIe design
guide). Feeding 3.3 V leaves 300 mV to the lower limit, but not all of it is
available for droop:

| Term | Allocation | Note |
|------|-----------|------|
| Total 3.3 V → 3.0 V | **300 mV** | Hard floor |
| Buck A setpoint tolerance (±2%) | −66 mV | Reference + 1% divider tolerance |
| Output ripple (design target 30 mV p-p) | −30 mV | |
| **Available for transient droop** | **≈ 204 mV** | |

Allocate roughly 20 mV to ESR and the remainder to capacitance.

---

## 3. ESR term — evaluated first

ESR drop is instantaneous and **no amount of capacitance reduces it**:

```
dV_esr = I_burst x ESR = 2.7 A x ESR
```

| Effective ESR | Drop at 2.7 A |
|---------------|---------------|
| 25 mΩ | 68 mV |
| 20 mΩ | 54 mV |
| 8 mΩ | 22 mV |
| 7 mΩ | 19 mV |

This is why **several smaller polymer capacitors in parallel beat one large
aluminium electrolytic**. Paralleling N identical devices divides both ESR and ESL
by N. A single 470 µF aluminium part would satisfy the capacitance number while
landing in the 25 mΩ-plus range and eating a third of the droop budget on its own.

Target: **effective ESR ≤ 10 mΩ**, giving ≤ 27 mV.

---

## 4. Capacitance term

The reservoir does **not** have to supply the whole 2G burst. Buck A is a 5 A
converter and can carry 2.7 A continuously; the capacitors only bridge the
interval before the control loop responds:

```
dV_c = I_burst x t_response / C
```

With ~184 mV left after the ESR allocation:

| Loop response `t` | Minimum C |
|-------------------|-----------|
| 10 µs | 147 µF |
| 20 µs | 293 µF |
| 30 µs | 440 µF |
| 50 µs | 734 µF |

This is the sanity check that makes Quectel's number make sense: **470 µF
corresponds to roughly 30-50 µs of full-current response**, which is about right
for their reference design's **MIC29302 LDO** (Figure 3, p. 18). A TPS54560-Q1
switching at ~500 kHz responds faster, so 470 µF is conservative here — but it is
the stated minimum and we meet it.

Two effects that do **not** bind:

- **Inductor slew.** At 12 V in, 3.3 V out, 10 µH, current slews at
  (12 − 3.3)/10 µH ≈ 0.87 A/µs, so 2.7 A takes ~3.1 µs. The control loop, not the
  inductor, is the limit.
- **Burst-to-burst recharge.** A GSM slot is 577 µs within a 4.615 ms frame,
  leaving ~4 ms and ~2.3 A of spare converter capability to recharge. Ample.

---

## 5. Selection

**3 × 220 µF polymer, 660 µF total.**

| Term | Value |
|------|-------|
| Capacitance | 660 µF |
| Effective ESR (3 × ~20 mΩ in parallel) | ≈ 6.7 mΩ |
| ESR drop at 2.7 A | ≈ 18 mV |
| Capacitive droop at t = 20 µs | ≈ 82 mV |
| **Total estimated droop** | **≈ 100 mV** vs 204 mV available |

Comfortably inside budget, clears the 470 µF floor with margin, and three
parallel parts keep ESR and ESL low. Rejected alternatives: 5 × 100 µF (lowest
ESR but most board area and placement effort for margin already sufficient) and
2 × 330 µF (fewest parts, highest ESR of the three options).

Verify at purchase: ESR is specified at 100 kHz for the actual MPN, the ripple-
current rating covers the burst, and the voltage rating derates acceptably at
3.3 V.

---

## 6. Buck A loop and soft-start — must be redone

Tripling the output capacitance moves buck A's loop, so the compensation network
is no longer a "finalize during capture" item. It is load-bearing.

**Output pole moves down by the same factor.** With `R_load = 3.3 V / 2.7 A ≈
1.22 Ω`:

| Output capacitance | Output pole |
|--------------------|-------------|
| 200 µF (original) | ≈ 651 Hz |
| 660 µF (new) | ≈ 197 Hz |

For the TPS54560-Q1's current-mode loop, `R_compA` sets the mid-band gain and
`C_compA` sets the compensation zero. With the output pole a factor of 3.3 lower,
the zero must move down with it and the gain must be re-derived for the target
crossover, or the loop loses phase margin. Re-run the datasheet procedure (or TI
WEBENCH) with:

- Output capacitance **660 µF** and effective ESR **≈ 6.7 mΩ**
- Switching frequency as set by `R_rtA`
- Load step **0 → 2.7 A**

Then confirm crossover frequency and phase margin, and check whether `C_comp2A`
(the high-frequency roll-off cap) is still needed against the new ESR zero, which
has moved up to roughly `1 / (2π × 6.7 mΩ × 660 µF) ≈ 36 kHz`.

**Soft-start must cover the larger inrush.** Charging 660 µF adds
`I = C × dV/dt` on top of the load current:

| Soft-start time | Added inrush |
|-----------------|--------------|
| 2 ms | 1.09 A |
| 5 ms | 0.44 A |
| 10 ms | 0.22 A |

Target **≥ 5 ms**, which keeps the extra inrush under half an amp and well clear
of the converter's current limit. Size `C_ssA` from the TPS54560-Q1 soft-start
equation — the constants are TI-specific and must be read from the datasheet
rather than assumed.

**`EN` sequencing still works.** Soft-start of a few milliseconds is irrelevant
next to the modem's own multi-second boot, so gating buck A from `CELL_PWR_EN`
(PIC RA2) behaves exactly as described in
[interconnect-and-pin-budget.md](interconnect-and-pin-budget.md). Keep the `EN`
pull-down so the card stays off while the PIC is in reset.

---

## 7. Buck B and the NEO-M9N ramp — checked, unaffected

The NEO-M9N is on **buck B**, a separate converter, so nothing above changes its
behaviour. Stating it explicitly because the constraint is part-damaging rather
than merely out of spec.

`VCC` ramp must be **20 - 8000 µs/V** (Datasheet Table 10; note 7: exceeding the
ramp speed *"may permanently damage the device"*). For a 0 → 3.3 V rise:

| Bound | Ramp rate | Rise time |
|-------|-----------|-----------|
| Fastest allowed | 20 µs/V | **66 µs** |
| Slowest allowed | 8000 µs/V | **26.4 ms** |

Action: measure or calculate the LMR16006X's internal soft-start ramp on
`3V3_SYS` and confirm it falls inside 66 µs - 26.4 ms. The internal soft-start is
typically a few hundred microseconds to a few milliseconds, comfortably mid-range,
but **the fast bound is the dangerous one** — do not add a fast-start variant or
bypass soft-start. If external soft-start capacitance is ever added to buck B,
re-check the slow bound too.

Related constraint from the same document (IM §4.2.1): series resistance in the
VCC line to the NEO-M9N must stay **below 0.2 Ω**, which makes `FB2` a
DCR-selected part, not just an impedance-selected one.

---

## 8. Changes made to `power-supply-bom.md`

- `C10`, `C11` → **3 × 220 µF** polymer, ≥ 6.3 V, effective ESR ≤ 10 mΩ, with the
  ≥ 470 µF requirement cited.
- `C_compA` / `R_compA` and `C_ssA` notes updated to record that they must be
  recomputed for the new output capacitance.
- `FB2` note updated with the < 0.2 Ω DCR limit.

Not changed: front-end protection, both converters' inductors and diodes,
feedback dividers, `C12`/`C13`, and `gen_power_schematic.py`.
