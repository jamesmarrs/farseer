# Farseer GNSS BOM

Bill of materials for the GNSS circuit drawn in `gnss-schematic.pdf` (generated
by `gen_gnss_schematic.py`). Design rationale, layout rules, and datasheet
citations live in [gnss-support-circuit.md](gnss-support-circuit.md) — this file
is the **single source of truth for parts and values**; that one explains *why*.

Scope: a **bare u-blox NEO-M9N-00B in the 24-pin LCC**, fed from the `3V3_SYS`
branch designed in [power-supply-bom.md](power-supply-bom.md) §5. Interface is
**UART to the PIC only** — no USB, no I2C, no SPI.

Authoritative sources:

- `datasheets/NEO-M9N-00B_DataSheet_UBX-19014285.pdf` — electrical limits, pins,
  mechanicals.
- `datasheets/NEO-M9N_Integrationmanual_UBX-19014286.pdf` (**R10**, cited below
  as **IM**) — power supply, minimal design, antenna circuits, footprint.

**Status column** matches `power-supply-bom.md`: **Req** mandatory, **Rec**
strongly recommended, **Opt** genuine choice.

> Two BOM lines here are also carried in `power-supply-bom.md` §5 (`C_neo1`,
> `C_neo2`, `C_neoBulk`, `C_bkp`, and the `FB2` ferrite feeding this branch).
> **Same physical parts** — listed there as rail distribution, here as GNSS
> support. Do not order twice.
>
> [full-bom.md](full-bom.md) merges all four BOMs into one ordering list with
> that overlap already resolved. Regenerate it with
> `python3 docs/gen_full_bom.py` after any change here.

---

## 1. Receiver module

| Ref | Qty | Status | Value / description | Suggested MPN (datasheet) | Notes |
|-----|-----|--------|---------------------|---------------------------|-------|
| U4 | 1 | Req | NEO-M9N-00B, **24-pin LCC**, 12.2 × 16.0 × 2.4 mm, 1.1 mm pitch | [u-blox NEO-M9N-00B](https://www.u-blox.com/en/product/neo-m9n-module) | **Perimeter castellations, no hidden thermal pad** — joints are visible and probeable. Footprint and paste mask from IM Figures 37/38, with keep-out for the ≤ 0.5 mm de-panel tabs on one long edge |

---

## 2. Main supply decoupling (VCC, pin 23)

Operating range **2.7–3.6 V**, 100 mA acquisition peak, 28–50 mA typical
(Datasheet Tables 11 and 12).

| Ref | Qty | Status | Value / description | Suggested MPN (datasheet) | Notes |
|-----|-----|--------|---------------------|---------------------------|-------|
| C_neo1 | 1 | Req | **1 µF**, 16 V, X7R, 0603 | generic | IM §4.9.1 asks it as a checklist item verbatim: *"Is there a 1 uF cap right next to the module VCC pin?"* Place as close to the pad as physically possible |
| C_neo2 | 1 | Rec | 100 nF, 16 V, X7R, 0402 | generic | HF companion at VCC |
| C_neoBulk | 1 | Rec | 10 µF, 16 V, X7R, 0805 | generic | Local reservoir for the 100 mA acquisition peak |
| FB2 | 1 | Rec | Ferrite ≈ 600 Ω @ 100 MHz, **DCR < 0.2 Ω** | Murata BLM18 series (**select on DCR**) | Isolates the GNSS branch from the PIC rail. Also listed in `power-supply-bom.md` §5. **Hard limit:** IM §4.2.1 forbids > 0.2 Ω series resistance in the VCC line |

Two specs that damage or degrade the part if missed:

- **Series resistance in VCC must stay under 0.2 Ω** (IM §4.2.1, §4.9.1). A
  typical 600 Ω @ 100 MHz bead easily exceeds that — pick by DCR.
- **VCC ramp rate must be 20–8000 µs/V** (Datasheet Table 10, note 7), i.e. a
  0 → 3.3 V rise between **66 µs and 26.4 ms**. Faster *"may permanently damage
  the device."* Buck B's internal soft-start must be confirmed inside that
  window — checked in [power-rail-notes.md](power-rail-notes.md).

---

## 3. Backup supply (V_BCKP, pin 22) and V_USB (pin 7)

| Ref | Qty | Status | Value / description | Suggested MPN (datasheet) | Notes |
|-----|-----|--------|---------------------|---------------------------|-------|
| C_bkp | 1 | Rec | 10 µF-class hold cap, 16 V (or a supercap) | generic | Keeps RTC + battery-backed RAM alive for hot/warm starts. Backup draw is only **45 µA** typ at 3 V (Datasheet Table 11). Cold start ≈ 24–29 s to fix vs. a couple of seconds hot |
| — | 0 | Req | **If C_bkp is omitted: tie V_BCKP directly to VCC** | — (a net, not a part) | IM §4.2.2. **Never leave pin 22 floating**, and put **no series resistance** on the line — switchover draws a current peak that a resistive path turns into a damaging drop |
| — | 0 | Req | **V_USB (pin 7) tied to GND** | — (a net, not a part) | IM §4.2.3 — required when USB is unused. This is *not* covered by the "unused inputs may be left open" rule and is the single easiest pin on this part to get wrong |

---

## 4. RF front end

One layout serves both antenna types, selected by populate / no-fit. **Do not
fit a DC block or matching network on RF_IN** — the module has both internally,
plus a SAW filter, an LTE band-13 notch, and an LNA (IM §4.4.3, §4.5).

### 4a. Always fitted

| Ref | Qty | Status | Value / description | Suggested MPN (datasheet) | Notes |
|-----|-----|--------|---------------------|---------------------------|-------|
| J_gnss | 1 | Req | U.FL or SMA, **50 Ω** | generic (Hirose U.FL-R-SMT / Amphenol SMA) | Roof- or shell-mount antenna feed |
| D_rf | 1 | **Req** | **Low-capacitance** ESD diode, GNSS-band rated | select for C ≲ 0.5 pF, e.g. an ESD8xxx-class part (verify capacitance) | IM §4.5.2: *"An ESD protection diode should also be connected to the input."* At the connector. Capacitance is the selection criterion — a general-purpose TVS will detune the input |

### 4b. Active antenna — fit these, omit `R_bias0` (IM Figure 33, Table 26)

| Ref | Qty | Status | Value / description | Suggested MPN (datasheet) | Notes |
|-----|-----|--------|---------------------|---------------------------|-------|
| L_bias | 1 | Opt | **27 nH**, Z > 500 Ω at GNSS frequency, rated **> 300 mA** | Murata LQW/LQG RF inductor (verify Z and Irms) | Bias-T choke; isolates RF from the DC path |
| C_bias | 1 | Opt | **100 nF**, X7R, 10%, 16 V, 0402 | generic | Removes HF noise from the DC feed |
| R_bias | 1 | Opt | **22 Ω**, 0.25 W, 0805 | generic | Short-circuit limiter. **Not the 10 Ω in Table 26** — the text below it requires ≥ **19 Ω** at a 3.3 V supply to hold short-circuit current under 150 mA. 22 Ω is the nearest standard value |

### 4c. Passive antenna — fit this instead

| Ref | Qty | Status | Value / description | Suggested MPN (datasheet) | Notes |
|-----|-----|--------|---------------------|---------------------------|-------|
| R_bias0 | 1 | Opt | 0 Ω link, 0402 | generic | Fitted **instead of** `L_bias` / `C_bias` / `R_bias`. Leave `VCC_RF` (pin 9) and `LNA_EN` (pin 14) unconnected |

`VCC_RF` sources **VCC − 0.1 V** typ at up to **50 mA** operating (200 mA abs
max), comfortably covering the 5–20 mA an active antenna draws. Absolute input
limits: **in-band 0 dBm**, **out-of-band +13 dBm**, **max external gain 30 dB** —
do not stack an active antenna with a separate LNA.

The antenna feed is the most likely thing to short in a race car; a chafed coax
against bodywork does it. `R_bias` is what stops that from destroying the bias-T
choke or the module's internal feed inductor.

---

## 5. Digital interface and test points

UART direct to the PIC, **no level shifting and no series resistors specified** —
both parts sit on `3V3_SYS`, and at VCC = 3.3 V the NEO needs Vih ≥ 2.64 V, which
the PIC drives comfortably.

| Ref | Qty | Status | Value / description | Suggested MPN (datasheet) | Notes |
|-----|-----|--------|---------------------|---------------------------|-------|
| TP_safeboot | 1 | Rec | Test point or no-fit pad | generic | `SAFEBOOT_N` (pin 1). Left open in normal operation; brought out for future firmware update |
| TP_pps | 1 | Rec | Test point | generic | `TIMEPULSE` (pin 3) — 1 PPS at **30 ns RMS**, 4 mA drive. Route to a PIC input even though firmware does not use it yet; it is the only way to discipline timestamps better than UART arrival time |

Nets, no parts: `TXD` (20) → PIC RD1 (pin 43, U2RX); `RXD` (21) ← PIC RD0
(pin 42, U2TX); `RESET_N` (8) to a PIC GPIO, **open-drain** against the internal
7–13 kΩ pull-up, no external RC. Default **38400 8N1** NMEA, which
[gps.c](../gps.c) then renegotiates to 115200 for 25 Hz. **No hardware flow
control** exists on this part.

Left open by design: `EXTINT` (4), `USB_DM` (5), `USB_DP` (6), `SDA` (18),
`SCL` (19), and `D_SEL` (2). **`D_SEL` must not be grounded** — that selects SPI.
**Reserved pins 15, 16, 17 must be unconnected.**

---

## Approximate cost (qty 1, USD, distributor list — order of magnitude)

| Block | Rough cost |
|-------|-----------|
| U4 NEO-M9N-00B | ~$30–45 |
| VCC decoupling + ferrite + backup cap | ~$1 |
| Antenna connector + low-cap ESD diode | ~$2–4 |
| Bias-T (active-antenna option only) | ~$1 |
| **Total excluding U4 and the antenna itself** | **~$4–6** |

The module dominates; everything around it is noise by comparison. Budget
separately for the antenna, which for a passive patch is ~$10–20 and for an
active roof-mount considerably more.

---

## Verify before ordering

- [ ] **V_USB (pin 7) tied to GND** — required, not "leave open"
- [ ] **V_BCKP (pin 22) tied to VCC** if no backup cap is fitted — never floating,
      and no series resistance on the line
- [ ] **1 µF sitting directly at the VCC pad**, large pad, generous vias
- [ ] `FB2` selected for **DCR < 0.2 Ω**, per IM §4.2.1 — not just impedance
- [ ] Buck B ramp verified inside **66 µs – 26.4 ms** for the 0 → 3.3 V rise
- [ ] **No DC block and no matching network on RF_IN** — both are internal
- [ ] `D_rf` selected for **low capacitance**, fitted at the connector
- [ ] Exactly one of `R_bias0` **or** the `L_bias`/`C_bias`/`R_bias` set populated
- [ ] `R_bias` ≥ 19 Ω, with power rating checked for the short-circuit case
- [ ] RF_IN as a via-shielded grounded co-planar 50 Ω waveguide, no stubs
- [ ] `D_SEL` (pin 2) open or tied to VCC — **not** grounded
- [ ] Reserved pins 15, 16, 17 left unconnected
- [ ] Total external gain ≤ 30 dB
- [ ] Footprint and paste mask from IM Figures 37/38, de-panel tab keep-out on the
      long edge
- [ ] GNSS antenna sited as far as practical from the BG95 antenna
- [ ] Rebuild the drawing with `./docs/build_schematics.sh gnss` after any change here
