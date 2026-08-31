# Farseer whole-board BOM

**Generated — do not edit.** Written by `gen_full_bom.py` from the four
per-block BOMs, which remain the single source of truth for parts and
values. Change a part there and re-run `python3 docs/gen_full_bom.py`.

| Block | Source BOM | Rationale | Schematic |
|-------|-----------|-----------|-----------|
| Power | [power-supply-bom.md](power-supply-bom.md) | [power-rail-notes.md](power-rail-notes.md) | [power-rails-schematic.pdf](power-rails-schematic.pdf) |
| MCU | [mcu-bom.md](mcu-bom.md) | [mcu-support-circuit.md](mcu-support-circuit.md) | [mcu-schematic.pdf](mcu-schematic.pdf) |
| Cellular | [cellular-bom.md](cellular-bom.md) | [cellular-support-circuit.md](cellular-support-circuit.md) | [cellular-schematic.pdf](cellular-schematic.pdf) |
| GNSS | [gnss-bom.md](gnss-bom.md) | [gnss-support-circuit.md](gnss-support-circuit.md) | [gnss-schematic.pdf](gnss-schematic.pdf) |

Everything on one sheet: [full-schematic.pdf](full-schematic.pdf).
A flat version of the table below, for a spreadsheet or a distributor
upload, is in [full-bom.csv](full-bom.csv).

**Status**: **Req** mandatory, **Rec** strongly recommended for
robustness or EMC, **Opt** a genuine design choice. A quantity written as
a range (`0–2`, `2–3`) is one the source BOM leaves open — fit-if-needed
parts, or values still to be pinned down at schematic capture. Quantity
`0` marks a row that documents a **net rather than a part** (`V_USB` to
ground) or a deliberate no-fit (the crystal that is not populated).

---

## Totals

Counted at the low end of each quantity range, excluding rows that
document a net rather than a part.

| Status | Line items | Parts |
|--------|-----------|-------|
| Req — mandatory | 52 | 74 |
| Rec — recommended | 26 | 30 |
| Opt — optional | 18 | 13 |
| **Req + Rec** | **78** | **104** |

**GNSS antenna feed** is mutually exclusive: `L_bias` / `C_bias` / `R_bias` versus `R_bias0` — active antenna (bias-T) or passive antenna (0 ohm link) - populate one. Both appear below; the totals count both, so subtract whichever you do not fit.

The three modules that dominate cost — `U1` PIC18F57Q84, `U4` NEO-M9N,
and the BG95-M3 Mini PCIe card itself — are counted as ordinary line
items here. Note the BG95 card is **not** a line in any BOM: it is the
module that plugs into `J2`, bought as an assembly.

---

## Power  -  vehicle input, protection, two bucks

### 1. Front-end protection (vehicle input → `VSYS`)

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| J1 | 1 | Req | 2-pin power input connector, automotive-rated | Molex/JST (verify current + keying) | Car harness entry |
| F1 | 1 | Req | Fuse, 3–4 A slow-blow, + holder | Littelfuse 0451 series (size to draw) | ~2.5 A worst-case in at 7 V; 3–4 A gives margin |
| Q1 | 1 | Req | P-ch MOSFET, −60 V, ~110 mΩ, AEC-Q101 | [Diodes DMP6110SFDF-13](https://www.diodes.com/datasheet/download/DMP6110SFDF.pdf) | Reverse-polarity pass FET; −60 V clears the SM8S26A ~42 V clamp |
| R1 | 1 | Rec | Gate resistor ≈ 100 kΩ, 0603 | generic 1% | Q1 gate pull to source |
| Dz1 | 1 | Rec | Gate-protect Zener ≈ 15 V, SOD-123 | Nexperia BZT52C15 | Clamps Q1 V_GS (abs max ±20 V) on transients |
| D1 | 1 | Req | Uni TVS, 26 V standoff, 42.1 V clamp, 7 kW, AEC-Q101 | [Littelfuse SM8S26A](https://www.littelfuse.com/products/tvs-diodes/surface-mount/sm8s.aspx) | Load-dump clamp; standoff > 18 V max, clamp < 60 V buck abs-max |
| FB0 | 1 | Rec | EMI ferrite / pi-filter element (or ≈ 4.7 µH) | Würth WE-MPSB or 4.7 µH power inductor | Keeps switching noise off the harness |
| C0 | 1 | Rec | Pi-filter input cap ≈ 1 µF, 63 V, X7R, 1210 | generic | Before FB0 (harness side) |
| C2, C3 | 2 | Req | ≈ 2.2 µF, 63 V, X7R, 1210 (at `VSYS`) | generic | After FB0; shared input decoupling for both bucks |
| C1 | 1 | Req | Input bulk ≈ 100 µF, 63 V, aluminum electrolytic (low-ESR) | Panasonic FR/FC series | Transient reservoir; 63 V for headroom over 42 V clamp |

### 2. Buck A — `VSYS` → 3.3 V @ ≥ 4 A (BG95 Mini PCIe rail, 2G-capable)

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| U2 | 1 | Req | Wide-Vin buck, 4.5–60 V in, **5 A**, survives 65 V load dump, AEC-Q100 | [TI TPS54560-Q1](https://www.ti.com/lit/ds/symlink/tps54560-q1.pdf) | V_OUT = 3.3 V; 5 A gives headroom over ~4 A 2G burst; non-sync (needs D2) |
| L1 | 1 | Req | Power inductor ≈ 10 µH, I_sat ≥ 7.6 A, I_rms ≥ 7 A | [Coilcraft XAL6060-103MEC](https://www.coilcraft.com/en-us/products/power/shielded-inductors/molded-inductor/xal/xal60xx/) | Margin over 5.7 A peak; verify L vs U2 procedure at chosen fsw |
| D2 | 1 | Req | Schottky catch diode, 60 V, ≥ 5 A | [Diodes B560C-13-F](https://www.diodes.com/datasheet/download/B560C.pdf) | Required for non-sync TPS54560; **verify thermals at sustained 5 A** (bump to a 60 V/8 A part if running max continuously) |
| C_inA | 3 | Req | 2× 10 µF 63 V X7R (1210) + 0.1 µF | generic | At U2 V_IN, tight loop |
| C_outA | 3 | Req | 3× 22 µF 16 V X7R (1206) | generic | At U2 V_OUT; size for 5 A ripple + burst |
| R_fbA1 | 1 | Req | ≈ 31.6 kΩ 1% 0603 (top) | generic | Sets 3.3 V with V_REF 0.8 V (ratio 3.125) |
| R_fbA2 | 1 | Req | 10 kΩ 1% 0603 (bottom) | generic | — |
| R_rtA | 1 | Req | RT/CLK resistor (set ~500 kHz) | per datasheet | ~100 kΩ region; use datasheet fsw equation |
| C_ssA | 1 | **Req** | Soft-start cap (SS/TR), sized for **≥ 5 ms** | per datasheet | Controlled ramp; must cover inrush into the 660 µF socket reservoir (~0.44 A extra at 5 ms). **Recompute** — see `power-rail-notes.md` |
| R_compA, C_compA(, C_comp2A) | 2–3 | Req | Compensation network | per datasheet | Current-mode external comp — loop is unstable without it. **Must be recomputed for C_out = 660 µF / ESR ≈ 6.7 mΩ**: the output pole moved from ≈651 Hz to ≈197 Hz. See `power-rail-notes.md` |
| C_bootA | 1 | Req | Bootstrap ≈ 0.1 µF, 0603 | per datasheet | BOOT-to-SW; drives internal high-side FET. **Verify against TPS54560-Q1 datasheet** (TI's standard BOOT value is 0.1 µF; the earlier 10 nF was under-sized) |
| R_enA1/2 | 1–2 | Opt | EN pull-down (divider optional) | 1% 0603 | EN driven by PIC GPIO; pull-down = default OFF to sequence card after MCU. Divider only if hardware UVLO wanted |

### 3. Buck B — `VSYS` → 3.3 V @ ~0.6 A (PIC + NEO-M9N rail)

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| U3 | 1 | Req | Small wide-Vin buck, 4–60 V in, 0.6 A, 0.7 MHz | [TI LMR16006XDDCR](https://www.ti.com/lit/ds/symlink/lmr16006.pdf) | V_OUT = 3.3 V (V_REF 0.765 V); **X = 0.7 MHz** chosen over Y (2.1 MHz): at 18 V in / 3.3 V out the Y needs an 87 ns on-time vs the 80 ns TON_MIN (§7.6) — pulse-skips at high line. X needs ~196 ns. Integrates comp + soft-start |
| L2 | 1 | Req | Power inductor **22 µH**, I_sat ≥ 1.7 A (≥ max current limit) | Coilcraft XAL5030-223 or similar (verify I_sat) | Eq. 1 at 18 V in, K_IND 0.3, 0.7 MHz → 21.4 µH → 22 µH (datasheet's own starting point, §9.2.2.2). Ripple ≈ 0.18 A, peak ≈ 0.69 A; I_sat ≥ 1.7 A current-limit max so a short can't saturate it |
| D3 | 1 | Req | Schottky catch diode, 60 V, 1 A (SMA) | [onsemi SS16](https://www.onsemi.com/download/data-sheet/pdf/ss16-d.pdf) (auto: SBRA8160, AEC-Q101) | **Required — LMR16006 is non-sync** (datasheet §9.2.2.4: V_BR ≥ 25% over max V_IN → 60 V) |
| C_inB | 2 | Req | 4.7 µF 63 V X7R (1206) + 0.1 µF | generic | At U3 V_IN; input ripple ≈ 46 mV at 0.7 MHz (Eq. 10), OK |
| C_outB | **2** | Req | **2 × 22 µF** 16 V X7R (1206) | generic | At U3 V_OUT. At 0.7 MHz the transient criterion (Eq. 5, 0→0.6 A, 3%) needs ≥ 17.1 µF and overshoot (Eq. 6, 22 µH) ≥ 11.9 µF — a single derated 22 µF is marginal, so two in parallel |
| R_fbB1 | 1 | Req | ≈ 33.2 kΩ 1% 0603 (top) | generic | Sets 3.3 V with V_REF 0.765 V (ratio 3.31) |
| R_fbB2 | 1 | Req | 10 kΩ 1% 0603 (bottom) | generic | — |
| C_bootB | 1 | Req | Bootstrap **100 nF**, ≥ 10 V X7R, 0603 | generic | CB-to-SW; datasheet §9.2.2.6 requires **0.1 µF or larger** (10 nF is too small) |
| R_enB | 1 | Opt | EN series resistor ≈ 100 kΩ (or divider) | generic 1% | Only if tying EN→VSYS. Can instead float EN (internal pull-up = always on). Divider sets custom UVLO |

## MCU  -  PIC18F57Q84, reset, ICSP, USB console

### 1. Microcontroller

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| U1 | 1 | Req | PIC18F57Q84, 48-pin TQFP, 7×7 mm, 0.5 mm pitch | [Microchip PIC18F57Q84-I/PT](https://www.microchip.com/en-us/product/PIC18F57Q84) | `-I/PT` = industrial temp, TQFP. **No VCAP pin** on this device (§4.1) — do not fit a core-regulator cap |

### 2. Decoupling — DS40002213F §4.2.1, Table 3-2 note 5

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| C_pic1 | 1 | Req | 0.1 µF, 16–25 V, **X7R**, low-ESR ceramic, 0402 | generic (select for SRF ≥ 200 MHz) | VDD pin **7** → VSS pin **6**, ≤ 6 mm, same side as U1 |
| C_pic2 | 1 | Req | 0.1 µF, 16–25 V, **X7R**, low-ESR ceramic, 0402 | generic (select for SRF ≥ 200 MHz) | VDD pin **30** → VSS pin **31**. Opposite corner from C_pic1 — **one shared cap is not compliant** |
| C_picBulk | 1 | Rec | 4.7 µF, 16 V, X7R, 0805 | generic | Tank cap, §4.2.2 (4.7–47 µF range). Kept because the NEO-M9N shares this rail and buck A switches hard nearby |
| C_picHF1, C_picHF2 | 0–2 | Opt | 1 nF (0.001 µF), 0402 | generic | Decade pair in parallel with each 0.1 µF. **Fit only if tens-of-MHz noise is measured** — no-fit pads by default |

### 3. MCLR / reset network — DS40002213F §4.3, Figure 4-1

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| R_mclr1 | 1 | Req | **10 kΩ** 1% 0603, pull-up to VDD | generic | Figure 4-1 R1. Note 1 caps it at **R1 ≤ 10 kΩ**. The Curiosity Nano's 47 kΩ (R200) violates this — **follow the datasheet, not the dev board** |
| R_mclr2 | 1 | Rec | **220 Ω** 0603, series into MCLR (100–470 Ω range) | generic | Figure 4-1 R2. Note 2: **R2 ≤ 470 Ω**, limits C_mclr discharge current into the pin on ESD/EOS |
| C_mclr | 1 | Rec | 0.1 µF, 25 V, X7R, 0603 | generic | Figure 4-1 C1. Immunity to spurious reset on rail sag |
| JP_mclr | 1 | Opt | 2-pin 0.1 in jumper, **or** a no-fit pad on C_mclr | generic header | Figure 4-2: lets C_mclr be lifted if the programmer objects to the RC. Costs nothing as a no-fit |

### 4. ICSP programming + debug header — DS40002213F §4.4, Figure 48-2

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| J_icsp | 1 | Req | 6-pin 0.1 in header, **0.025 in square posts**, 0.1 in pitch | generic (Würth/Molex 0.1 in SIL) | PICkit pinout: 1 VPP/MCLR, 2 VDD, 3 VSS, 4 ICSPDAT, 5 ICSPCLK, 6 NC. Figure 48-2 note 1 requires the 0.025 in square post. **Pin 1 must be marked** — square pad + silkscreen triangle + `VPP` legend; the header is unkeyed and Figure 48-2 draws a "Pin 1 Indicator" as part of the definition. The PICkit 5's 8-pin body mates with this; its pins 7–8 are unused |
| R_icsp1, R_icsp2 | 0–2 | Rec | **47 Ω** 0603, series on PGD / PGC | generic | §4.4: "tens of ohms", **must not exceed 100 Ω**. Fit only if the connector is exposed to ESD |
| R_icspPD1, R_icspPD2 | 2 | Rec | 47 kΩ 0603, pull-down on PGD / PGC | generic | Matches the Curiosity Nano debugger side; expected by Microchip tooling |

### 5. Debug console — USB-C + USB-to-UART bridge

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| U5 | 1 | Req | USB 2.0 full-speed to UART bridge, QFN24 4×4 mm | **Silicon Labs CP2102N-A02-GQFN24** (Rev 1.5) | Integrated transceiver, pull-ups, and 48 MHz oscillator — *"no external resistors required"*, *"no external crystal required"* (p. 1). Enumerates as a COM port exactly like the Nano's CDC. `VIO` = `VDD` = `VREGIN` = `3V3_SYS`, per Figure 2.3 |
| J_dbg | 1 | Req | **USB-C receptacle, 16-pin USB-2.0-only**, SMT with through-hole retention tabs | generic (verify footprint) | 16-pin part avoids the unused SuperSpeed pins. Retention tabs are not optional in a vehicle |
| R_cc1, R_cc2 | 2 | Req | **5.1 kΩ** 1% 0402, one on **CC1**, one on **CC2** | generic | Advertises the board as a USB device (sink). **Two separate resistors** — a single shared resistor breaks cable-orientation detection and some hosts will not attach at all |
| D_dbg | 1 | Req | **Low-capacitance** ESD array, D+/D−/VBUS, SOT-23-6 | **ST USBLC6-2SC6** | KiCad: `Power_Protection:USBLC6-2SC6`, footprint `Package_TO_SOT_SMD:SOT-23-6`. **Pins:** 1+6 I/O1 → `USB_DP` (J_dbg D+ / U5 pin 3); 3+4 I/O2 → `USB_DM` (J_dbg D− / U5 pin 4); 5 VBUS → raw J_dbg VBUS (before divider); 2 GND. Place at the connector |
| R_rst | 1 | **Req** | **1 kΩ** 0402, pull-up from `RSTb` (pin 9) to `VIO` | generic | §2.1 p. 5: *"In all cases, a 1 kΩ pull-up on the RSTb pin is recommended. This pull-up should be tied to VIO on devices that have it."* The QFN24 has VIO, so it goes there |
| R_dbg1, R_dbg2 | 2 | Rec | 220 Ω 0603, series in `DBG_TX` / `DBG_RX` | generic | Edge-rate and ESD control, and a current limit if the two supplies ever skew. Matches `R_u3a`/`R_u3b` on the cellular UART. Harmless at DC: the PIC's input leakage is ±125 nA max (DS40002213F D340) |
| R_vbus1, R_vbus2 | 2 | Req | **22.1 kΩ** (high side, VBUS → sense) and **47.5 kΩ** (sense → GND), 1% 0402 | generic | The exact divider drawn in Figures 2.4 / 2.5 / 2.6. **Not optional**: §2.3 p. 9 states *"A resistor divider (or functionally-equivalent circuit) on VBUS is required."* See the arithmetic below |
| C_dbg1a/b, C_dbg2a/b, C_dbg3a/b | 6 | Req | **4.7 µF (`a`) and 0.1 µF (`b`) per power pin** — pairs at `VREGIN` (7), `VDD` (6), `VIO` (5) | generic, X7R | Figures 2.1–2.3: *"4.7 µF and 0.1 µF bypass capacitors required for each power pin placed as close to the pins as possible."* Three power pins means **six capacitors**, not two |
| C_dbg4 | 1 | Rec | 1 µF 16 V X7R 0603 on VBUS | generic | Local VBUS bypass at the connector |
| R_shield, C_shield | 1+1 | Rec | 1 MΩ 0402 ∥ 4.7 nF 2 kV 0603 | generic | Connector shell to GND. The RC lets ESD through to ground while keeping a DC ground loop from forming between the car chassis and a laptop |

### 6. Indication

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| D_led0 | 1 | Opt | LED, low-current, 0603 | generic | Heartbeat on **RF3 (pin 39)**, driven **active low** by `LATFbits.LATF3` in [main.c](../main.c) |
| R_led0 | 1 | Req if D_led0 fitted | 1 kΩ 0603 | generic | ≈2 mA at 3.3 V. Also see `R_wwan` in [cellular-bom.md](cellular-bom.md) — same idea, different reason |

### 7. Clock — not fitted

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| Y_hs | 0 | Opt | 10 MHz crystal, OSC1 (32) / OSC2 (33) | — | Only with HS/XT in CONFIG1. Costs RA6 + RA7 and buys nothing here |
| C_osc1, C_osc2 | 0 | Opt | 18 pF / 22 pF, 0402 | — | Curiosity Nano values for its 12 pF-CL crystal |
| R_s | 0 | Opt | Series drive resistor | — | §12: may be needed for low-drive-level quartz |
| Y_sosc | 0 | Opt | 32.768 kHz, SOSCI (35) / SOSCO (34) | — | Secondary oscillator unused; not populated on the Nano either |

### 8. Unused I/O

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| R_unused | 0–n | Opt | 1 kΩ–10 kΩ 0603 to VSS | generic | §4.6 allows either firmware (drive as output low, **free — prefer this**) or a resistor to VSS. Reserve resistors for pins left floating at a connector |

## Cellular  -  BG95-M3 Mini PCIe, SIM, USB

### 1. Mini PCIe socket and rail decoupling

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| J2 | 1 | Req | Mini PCIe socket, **52-pin, full-size**, with latch | Molex 679105700 (Quectel's own reference, Figure 19) | Card supply on `VCC_3V3` pins **2, 39, 41, 52** — **not pin 24, which is RESERVED** on this card despite being 3.3Vaux in the Mini PCIe standard. GND on 4, 9, 15, 18, 21, 26, 27, 29, 34, 35, 37, 40, 43, 50 (Table 6) |
| C10, C11 | **3** | Req | Bulk reservoir **3 × 220 µF = 660 µF**, ≥ 6.3 V, low-ESR polymer, **effective ESR ≤ 10 mΩ** | Panasonic SP-Cap / Kemet T520 | Sources the TX burst locally at the socket. Sizing math in [power-rail-notes.md](power-rail-notes.md); paralleled to divide ESR and ESL |
| C12, C13 | 2 | Req | 10 µF 16 V X7R (0805) + 100 nF 0402 | generic | HF decoupling at the socket power pins |
| C14, C15 | 2 | Rec | 33 pF + 10 pF, 0402 | generic | Completes the Figure 3 cap ladder |
| D_cell | 1 | Rec | TVS on `3V3_CELL`, low clamp above 3.6 V | select clamp < card abs max (verify) | Socket-local clamp — the front-end TVS `D1` is far away at the harness entry |

### 2. (U)SIM interface — §3.3, Figure 4

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| J3 | 1 | Req | Nano-SIM holder, **hinged locking cover**, 6 contacts + detect switch | **GCT SIM8060-6-1-14-00-A** | Normally-open switch closes `SW` to the grounded shell when the card is seated → `SIM_DET` low = inserted |
| C_sim1 | 1 | Req | **100 nF**, 0402, `USIM_VDD` → GND | Murata GRM155R71C104KA88D | §3.3: decoupling **must not exceed 1 µF** and must sit close to the holder |
| C_sim2..4 | 3 | Req | **33 pF**, 0402, one per RST / CLK / DATA to GND | Murata GRM1555C1H330JA01D | Filters EGSM900 interference |
| D_sim | 1 | Req | TVS array, **parasitic capacitance ≤ 15 pF** | **TI TPD4E02B04DQAR** (~0.25 pF/ch, USON-10) | At the holder, on VDD / IO / CLK / RST. The 15 pF ceiling is the selection criterion |
| R_det1, R_det2 | 2 | Req | **51 kΩ**, 0402 — `SIM_DET` divider from `3V3_CELL` | Yageo RC0402FR-0751KL | See detect note below |
| R_simPU | 1 | Opt | **15 kΩ** 0402 to `USIM_VDD` | Yageo RC0402FR-0715KL | Pull-up on `USIM_DATA`; improves anti-jamming on long or noisy traces. Value per Figure 4/5; fit **DNP** by default |

### 3. UART to the PIC — §3.5

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| R_u3a, R_u3b | 2 | Rec | 220 Ω 0603 | generic | Series on `CELL_RX` / `CELL_TX`. Both ends now share a board, so the back-power case from [bench-wiring.md](bench-wiring.md) is gone; these remain useful for edge-rate and ESD control |

### 4. Control and indication

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| R_perst | 1 | Rec | 10 kΩ 0603 to `3V3_SYS` | generic | Belt-and-braces pull-up on `PERST#` (pin 22); holds reset released while the PIC is itself in reset. The card already pulls up |
| TP_perst | 1 | Rec | Test point | generic | A 2–3.8 s reset pulse is worth being able to scope |
| D_wwan | 1 | Opt | LED, low-current, 0603 | generic | `LED_WWAN#` (pin 42), open collector, active low |
| R_wwan | 1 | **Req if D_wwan fitted** | **1 kΩ** 0603 from `3V3_SYS` | generic | §3.7.4: *"a resistor must be placed in series with the LED."* ≈2 mA at 3.3 V. **Do not omit** — the pin sinks up to 40 mA and will cook the LED |

### 5. USB — Opt, §3.4

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| L_usb | 1 | Rec | Common-mode choke, USB 2.0 rated | Würth WE-CNSW or equivalent | §3.4 recommends one in series for EMI. **Place close to the socket** |
| D_usb | 1 | Rec | Low-capacitance ESD array, 2-line | select for low C on a 90 Ω pair | Per Figure 6 |
| R_usb1, R_usb2 | 2 | Opt | 0 Ω 0402, **not mounted by default** | generic | Series to test points, per Figure 6 |
| J_usb | 1 | Opt | USB connector or 4-pin header | generic | Firmware-update access |

### 6. Mechanical

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| MP1, MP2 | 2 | Req | Card standoffs / mounting posts for a full-size card | per socket vendor | Card is 51.0 × 30.0 mm (§7.2) |
| MP3 | 1 | Rec | Retaining screw or bracket, in addition to the latch | generic | In a vehicle the latch is structural. A card that walks out of its socket over a race weekend takes the telemetry link with it |
| — | 0 | Req | U.FL-LP mating plug, clearance, and cable strain relief | §5.4 recommends the U.FL-LP family | **The antenna connector is on the card** — no 50 Ω trace on our PCB. What the board owes is bend-radius clearance (Figure 16), a cable path to the bulkhead, and an anchor against continuous vibration |

## GNSS  -  NEO-M9N, supply, RF front end

### 1. Receiver module

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| U4 | 1 | Req | NEO-M9N-00B, **24-pin LCC**, 12.2 × 16.0 × 2.4 mm, 1.1 mm pitch | [u-blox NEO-M9N-00B](https://www.u-blox.com/en/product/neo-m9n-module) | **Perimeter castellations, no hidden thermal pad** — joints are visible and probeable. Footprint and paste mask from IM Figures 37/38, with keep-out for the ≤ 0.5 mm de-panel tabs on one long edge |

### 2. Main supply decoupling (VCC, pin 23)

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| C_neo1 | 1 | Req | **1 µF**, 16 V, X7R, 0603 | generic | IM §4.9.1 asks it as a checklist item verbatim: *"Is there a 1 uF cap right next to the module VCC pin?"* Place as close to the pad as physically possible |
| C_neo2 | 1 | Rec | 100 nF, 16 V, X7R, 0402 | generic | HF companion at VCC |
| C_neoBulk | 1 | Rec | 10 µF, 16 V, X7R, 0805 | generic | Local reservoir for the 100 mA acquisition peak |
| FB2 | 1 | Rec | Ferrite ≈ 600 Ω @ 100 MHz, **DCR < 0.2 Ω** | Murata BLM18 series (**select on DCR**) | Isolates the GNSS branch from the PIC rail. Also listed in `power-supply-bom.md` §5. **Hard limit:** IM §4.2.1 forbids > 0.2 Ω series resistance in the VCC line |

### 3. Backup supply (V_BCKP, pin 22) and V_USB (pin 7)

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| C_bkp | 1 | Rec | 10 µF-class hold cap, 16 V (or a supercap) | generic | Keeps RTC + battery-backed RAM alive for hot/warm starts. Backup draw is only **45 µA** typ at 3 V (Datasheet Table 11). Cold start ≈ 24–29 s to fix vs. a couple of seconds hot |
| — | 0 | Req | **If C_bkp is omitted: tie V_BCKP directly to VCC** | — (a net, not a part) | IM §4.2.2. **Never leave pin 22 floating**, and put **no series resistance** on the line — switchover draws a current peak that a resistive path turns into a damaging drop |
| — | 0 | Req | **V_USB (pin 7) tied to GND** | — (a net, not a part) | IM §4.2.3 — required when USB is unused. This is *not* covered by the "unused inputs may be left open" rule and is the single easiest pin on this part to get wrong |

### 4. RF front end

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| J_gnss | 1 | Req | U.FL or SMA, **50 Ω** | generic (Hirose U.FL-R-SMT / Amphenol SMA) | Roof- or shell-mount antenna feed |
| D_rf | 1 | **Req** | **Low-capacitance** ESD diode, GNSS-band rated | select for C ≲ 0.5 pF, e.g. an ESD8xxx-class part (verify capacitance) | IM §4.5.2: *"An ESD protection diode should also be connected to the input."* At the connector. Capacitance is the selection criterion — a general-purpose TVS will detune the input |
| L_bias | 1 | Opt | **27 nH**, Z > 500 Ω at GNSS frequency, rated **> 300 mA** | Murata LQW/LQG RF inductor (verify Z and Irms) | Bias-T choke; isolates RF from the DC path |
| C_bias | 1 | Opt | **100 nF**, X7R, 10%, 16 V, 0402 | generic | Removes HF noise from the DC feed |
| R_bias | 1 | Opt | **22 Ω**, 0.25 W, 0805 | generic | Short-circuit limiter. **Not the 10 Ω in Table 26** — the text below it requires ≥ **19 Ω** at a 3.3 V supply to hold short-circuit current under 150 mA. 22 Ω is the nearest standard value |
| R_bias0 | 1 | Opt | 0 Ω link, 0402 | generic | Fitted **instead of** `L_bias` / `C_bias` / `R_bias`. Leave `VCC_RF` (pin 9) and `LNA_EN` (pin 14) unconnected |

### 5. Digital interface and test points

| Ref | Qty | Status | Value / description | Suggested MPN | Notes |
|-----|-----|--------|---------------------|---------------|-------|
| TP_safeboot | 1 | Rec | Test point or no-fit pad | generic | `SAFEBOOT_N` (pin 1). Left open in normal operation; brought out for future firmware update |
| TP_pps | 1 | Rec | Test point | generic | `TIMEPULSE` (pin 3) — 1 PPS at **30 ns RMS**, 4 mA drive. Route to a PIC input even though firmware does not use it yet; it is the only way to discipline timestamps better than UART arrival time |

---

## Parts carried in two source BOMs

Each of these is **one physical part**, listed twice at the source: once
in `power-supply-bom.md` as rail distribution, and once in the BOM for
the subsystem it feeds. The row below was dropped in favour of the
subsystem row, so it is above exactly once. Order once.

| Dropped from | Ref | Kept in | As |
|--------------|-----|---------|----|
| power-supply-bom.md | `J2` | cellular-bom.md | `J2` |
| power-supply-bom.md | `C10, C11` | cellular-bom.md | `C10, C11` |
| power-supply-bom.md | `C12, C13` | cellular-bom.md | `C12, C13` |
| power-supply-bom.md | `C14, C15` | cellular-bom.md | `C14, C15` |
| power-supply-bom.md | `J3` | cellular-bom.md | `J3` |
| power-supply-bom.md | `FB2` | gnss-bom.md | `FB2` |
| power-supply-bom.md | `C_neo1, C_neo2` | gnss-bom.md | `C_neo1` |
| power-supply-bom.md | `C_neoBulk` | gnss-bom.md | `C_neoBulk` |
| power-supply-bom.md | `C_bkp` | gnss-bom.md | `C_bkp` |
| power-supply-bom.md | `C_vusb` | gnss-bom.md | a net, no designator |
| power-supply-bom.md | `C_pic` | mcu-bom.md | `C_pic1` |
| power-supply-bom.md | `C_picBulk` | mcu-bom.md | `C_picBulk` |

---

## Approximate cost

Reproduced from each source BOM. Single-unit distributor list prices,
order-of-magnitude only, and volatile — expect materially lower in volume.

**Board total: ~$70–108.** Every cost row below except the
per-block totals, and except the two rows in `power-supply-bom.md` that
price the socket and `3V3_SYS` parts a subsystem BOM already prices
(the same overlap the part rows have). `U1` and `U4` are included; the
**BG95-M3 Mini PCIe card**, the **LTE and GNSS antennas**, the PCB, and
the enclosure are **not** — none of them is a line in any BOM.

### Power  ([power-supply-bom.md](power-supply-bom.md))

| Block | Rough cost |
|-------|-----------|
| Front-end protection (F1/Q1/D1/FB0/caps + connector) | ~$6–9 |
| Buck A (TPS54560-Q1 + L1 + D2 + passives) | ~$7–10 |
| Buck B (LMR16006X + L2 + passives) | ~$3–5 |
| Mini PCIe socket + SIM holder + reservoir caps | ~$6–10 |
| `3V3_SYS` distribution (ferrite + decoupling) | ~$1–2 |
| **Total (excl. BG95 card, PIC, NEO modules)** | **~$25–35** |

### MCU  ([mcu-bom.md](mcu-bom.md))

| Block | Rough cost |
|-------|-----------|
| U1 PIC18F57Q84-I/PT | ~$3–5 |
| Decoupling (2× 0.1 µF, 4.7 µF, optional 1 nF pair) | <$0.50 |
| MCLR network + jumper | ~$0.50 |
| ICSP header + series/pull-down resistors | ~$1 |
| Debug console (CP2102N, USB-C, ESD array, 6 decoupling caps, passives) | ~$5–7 |
| Status LED + resistor | ~$0.25 |
| **Total** | **~$10–15** |

### Cellular  ([cellular-bom.md](cellular-bom.md))

| Block | Rough cost |
|-------|-----------|
| J2 Mini PCIe socket + standoffs | ~$2–4 |
| Bulk reservoir (3× 220 µF polymer) + HF caps | ~$4–7 |
| SIM holder + protection network | ~$2–4 |
| UART / PERST# / LED parts | ~$0.75 |
| USB option (choke, ESD, connector) | ~$2–3 |
| **Total (excluding the BG95-M3 card and antenna)** | **~$10–18** |

### GNSS  ([gnss-bom.md](gnss-bom.md))

| Block | Rough cost |
|-------|-----------|
| U4 NEO-M9N-00B | ~$30–45 |
| VCC decoupling + ferrite + backup cap | ~$1 |
| Antenna connector + low-cap ESD diode | ~$2–4 |
| Bias-T (active-antenna option only) | ~$1 |
| **Total excluding U4 and the antenna itself** | **~$4–6** |

The four **Total** rows above are each scoped differently — GNSS excludes
its own module, cellular excludes the card — so they cannot simply be
added. The board total at the top of this section is the sum that does
account for that.

