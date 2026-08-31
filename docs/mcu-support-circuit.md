# PIC18F57Q84 support circuit — design rationale

> **KiCad is the source of truth.** The circuit itself — parts, values, nets,
> footprints, MPNs — lives in the KiCad project
> (`ki_cad_project/farseer/farseer.kicad_pro`), on the **root sheet**
> (`farseer.kicad_sch`, the MCU block) and the **`usb_c` sheet**
> (`usb_c.kicad_sch`, the debug console). This document records only the
> reasoning that a schematic cannot carry: datasheet citations, traps,
> trade-offs, and rejected alternatives. If a value here ever disagrees with
> KiCad, KiCad wins.

Authoritative device source:
`pic_resources/PIC18F27-47-57Q84-Microcontroller-Data-Sheet-DS40002213.pdf`
(**DS40002213F**), plus `pic_resources/PIC18F57Q84-Curiosity-Nano-Schematics.pdf`
for reference values Microchip actually shipped.

> **Package warning.** Every pin claim below is from the **48-pin TQFP** column
> of Table 3-2 / Figure 2-7. The datasheet covers 28/40/44/48-pin parts in the
> same tables; numbers from a smaller package do not apply.

---

## 1. The mandatory-connection list, and the trap that isn't there

§4.1 (DS40002213F p. 18) is explicit: **all VDD and VSS pins** (§4.2) and
**MCLR** (§4.3) must always be connected; ICSPCLK/ICSPDAT, OSC pins, and VREF
only if used. That is the entire list. There is **no VCAP pin** on this device
(the word does not appear in DS40002213F), so no external core-regulator
capacitor is required — a common trap when porting from older PIC families
that do have one.

Two package consequences worth designing around: there is **no separate analog
supply** (no AVDD/AVSS pins), so ADC quality depends entirely on how clean
`3V3_SYS` is at the VDD pins — nothing can be filtered separately. And **VREF
is not a dedicated pin**: precision analog would cost RA2 and/or RA3, which are
general I/O in the current design (RA2/RA3 are `CELL_CTS`/`CELL_RTS`).

## 2. Decoupling (C2, C3, C1, C4, C5)

§4.2.1 (p. 19) makes per-VDD-pair decoupling **required**, not recommended
(Table 3-2 note 5 repeats it). `C2`/`C3` are those caps; `C4`/`C5` are the
optional decade pair; `C1` is the §4.2.2 tank cap.

Layout rules from §4.2.1, all pass/fail at review time:

- Cap must be **low-ESR with self-resonance at 200 MHz or higher**; ceramic.
  This rules out bargain-bin Y5V parts.
- Same side of the board as the MCU; if a via is unavoidable, the pin-to-cap
  trace must be **no longer than 0.25 in (6 mm)**.
- Route power **to the capacitor first, then to the device pin**.
- The VDD/VSS pairs (pins 7/6 and 30/31) are on **opposite corners** of the
  package — two separate placements, one shared cap is not compliant.

§4.2.2 makes the tank cap conditional on power runs longer than six inches.
The run from the `3V3_SYS` buck is short, but the NEO-M9N shares the rail and
the BG95 card is a violent switching load nearby, so `C1` (4.7 µF) is kept
anyway.

## 3. MCLR network (R1, R2, C6, JP1)

The board needs field reprogramming, so §4.3's "tie MCLR to VDD" shortcut does
not apply; the Figure 4-1 network does. Why these values and not others:

- **R1 is 10 kΩ, not the Curiosity Nano's 47 kΩ.** The Nano fits only a 47 kΩ
  pull-up (R200) and no capacitor — evidence the simple version works on a
  debugger-driven board, but Figure 4-1 note 1 says **R1 ≤ 10 kΩ**. Follow the
  datasheet, not the dev board.
- **R2 (series into MCLR) must stay ≤ 470 Ω** (Figure 4-1 note 2): it limits
  current from `C6` into the pin on ESD/EOS breakdown.
- **C6 fights the programmer.** §4.3 warns that programmers drive MCLR with
  fast transitions that must not be adversely affected, and Figure 4-2 answers
  with a jumper — that is what `JP1` is for. If the PICkit complains about VPP
  or target detect, lifting `C6` via `JP1` is the knob to reach for.
- **All MCLR components must sit within 0.25 in (6 mm) of pin 20** (§4.3).
- The internal weak pull-up (MCLRE, and LVP forcing MCLR on) gives a working
  reset but **no ESD/EOS protection and no noise filtering** — it is not a
  substitute for the network.

## 4. ICSP header (J1, R3, R5)

**The tool is a PICkit 5, and it is the programmer *and* the debugger** — ICSP
on RB6/RB7 buys programming, halt/single-step, three hardware breakpoints, and
RAM/SFR watch, forever (DS40002213F p. 6). Nothing on the board changes between
programming and debugging: MPLAB manages the `DEBUG` bit (CONFIG7[5]) itself.

> **JTAG cannot do this.** §39 (p. 884): *"The PIC18-Q84 JTAG module does not
> currently support programming over JTAG."* Boundary scan only. ICSP is the
> sole programming and debug path, which is why §4.4's rule is non-negotiable.

- §4.4 is emphatic about what **not** to add: *"Pull-up resistors, series
  diodes and capacitors on the ICSPCLK and ICSPDAT pins are not recommended."*
  RB6/RB7 carry nothing else on this board; `R3`/`R5` are small series
  resistors within §4.4's "tens of ohms, not exceeding 100 Ω" ESD allowance.
- The 6-pin 0.1 in header is the §48.3 (p. 1064) alternative to the RJ-11; the
  PICkit 5 mates directly, its connector pins 7–8 simply go unused. The
  PICkit 5's own 8-pin body is described in no document under
  `pic_resources/`, so the cited 6-pin footprint is the choice here.

Four things that are not obvious from the pinout and each cost an afternoon:

- **Header pin 2 is VDD *sense*, not VDD *supply*.** Leave MPLAB's *"Power
  target circuit from tool"* **off** and power the board from `VSYS` first.
  The tool's supply is meant for a bare MCU; this board hangs the NEO-M9N,
  two bucks, and a BG95 card capable of 2.7 A bursts off the same system. The
  failure is a confusing target-voltage/target-detect error, not an overload
  message — the single most likely first-attempt failure on a new board.
- **Mark pin 1.** The header is unkeyed; reversing it puts VPP where VSS
  should be. Square pad, silkscreen triangle, `VPP` legend.
- **If the tool complains about VPP or target detect, lift `C6` first**
  (`JP1`, §3 above).
- **LVP is a one-way door at 3.3 V.** `LVP` (CONFIG4[5]) erases to `1`, so the
  board programs from VDD alone — what the PICkit does by default and what we
  want. §48.2: while LVP is enabled the MCLR Reset function cannot be
  disabled, and *"the LVP bit can only be reprogrammed to '0' by using the
  High-Voltage Programming mode."* **Do not clear `LVP` in the project
  configuration** — every session after that needs high-voltage entry on VPP,
  and the §3 RC network is the first thing in its way.

## 5. Clock — HFINTOSC, no crystal

The board runs from HFINTOSC at 64 MHz and fits no crystal. The firmware
already assumes 64 MHz Fosc (see the baud derivation in [uart1.c](../uart1.c):
`64 MHz / (16 × 35) = 114286` for `U1BRG = 34`), every UART is asynchronous
with generous margin, and a crystal would cost pins RA6/RA7 for nothing.

> **Gotcha that will brick bring-up if missed.** CONFIG1 resets to all 1s
> (p. 46): **RSTOSC = 111** means "EXTOSC per FEXTOSC" and **FEXTOSC = 111**
> means "external clock above 8 MHz". A factory-fresh or fully erased part
> comes up expecting an **external clock this board does not have**. CONFIG1
> must be programmed with `RSTOSC = 000` (HFINTOSC 64 MHz, CDIV 1:1) for the
> board to run standalone.

If a crystal is ever retrofitted, §4.5 layout rules apply: same side as the
MCU, ≤ 0.5 in (12 mm) from the pins, load caps immediately next to the
crystal, grounded pour routed to MCU ground with no signal traces inside it.

## 6. Pin budget and unused I/O

Firmware pin assignments and the full 48-pin map are reconciled in
[interconnect-and-pin-budget.md](interconnect-and-pin-budget.md) — the single
place the allocation is checked against the **48-pin** PPS legality tables
(Table 21-1/21-2). Net names in KiCad (`CELL_*`, `GNSS_*`, `USB_TXD/RXD`)
match the firmware.

**Unused I/O:** §4.6 (p. 23) — configure as outputs driven low, or tie to VSS
through 1–10 kΩ. Prefer the firmware approach (free); reserve resistors for
pins left floating at a connector. RF3 is unused (no status LED on this board).

## 7. What the Curiosity Nano had that this board deliberately does not

- ATSAMD21E18 on-board debugger and its 3.3 V LDO — replaced by `J1` +
  PICkit 5 (programming/debug) and the `usb_c` sheet (console).
- MIC5353 adjustable LDO and the USB power path — this board is powered from
  the vehicle rail only; USB is data only.
- 74LVC1T45 level shifters between debugger and target — the Nano needs them
  because its target voltage is adjustable 1.8–5.1 V; our rail is fixed 3.3 V,
  so the bridge talks to the PIC directly.
- The 10 MHz crystal and load caps — see §5.
- The debugger's VTG monitoring, which produced the back-power fault
  documented in [bench-wiring.md](bench-wiring.md). On a custom board with
  shared rails that failure mode disappears.

## 8. Debug console — why the `usb_c` sheet looks the way it does

The console is UART1 on RF0/RF1 at 115200 ([uart1.c](../uart1.c)); on the Nano
those pins went into the debugger's CDC virtual COM port. The custom board
replaces that with `U7`, a Silicon Labs **CP2102N-A02-GQFN24** USB-to-UART
bridge on `usb_c.kicad_sch`
(`datasheets/Silabs_CP2102N_USB-UART_Bridge_DataSheet_Rev1.5.pdf`).

### Why a bridge chip and not USB straight to the PIC

**The PIC18F57Q84 has no USB peripheral.** The peripheral summary tables
(pp. 15–17) list CAN FD, every timer and serial block in the family — and no
USB module. The MCU cannot enumerate under any firmware, so a USB-C port is
only possible via a bridge that does the enumerating. The bridge gives the
**CDC half** of what the Nano's debugger did; programming and hardware debug
stay on `J1` with the PICkit 5.

### Powered from `3V3_SYS`, not from VBUS

USB is **data only** — it never powers the board. Since the board must be
running on `VSYS` for a console to be worth reading anyway, the bridge sits on
`3V3_SYS` too, which buys the important property: **when the vehicle rail is
off, `U7` is unpowered and cannot drive the PIC's pins.** A bus-powered bridge
would stay alive off a plugged-in laptop and drive the PIC's RX pin into an
unpowered MCU, parasitically powering it through input protection — the same
class of failure as the bench back-power fault and the failure u-blox warns
about for the NEO in hardware-backup mode. Self-powering avoids it
structurally rather than by adding parts.

The QFN24 variant was chosen because it carries **separate VIO and VDD pins**
(Table 1.1), letting the whole part sit on `3V3_SYS`. The topology is two
datasheet figures at once:

- **Figure 2.3** (regulator unused): `VREGIN` tied to `VDD` on a 3.0–3.6 V
  input (Table 3.6 note 1 states it outright).
- **Figure 2.6** (self-powered): VBUS reaches the **sense pin only**, through
  the divider `R33`/`R34` (22.1 kΩ / 47.5 kΩ). The bus-powered alternative
  (Figure 2.5, VBUS into `VREGIN`) is exactly the wiring this design avoids.

The divider is mandatory, not a refinement. §2.3: the sense pin's absolute
maximum is **VIO + 2.5 V** while the attach threshold is **VIH = VIO − 0.6 V**,
so at VIO = 3.3 V the tap must land between 2.7 V and 5.8 V —
5 V × 47.5/(22.1 + 47.5) = **3.41 V** does. The same note explains the second
job: the divider's current limit prevents VBUS leakage damage from a live
cable against a **dead board** — in a race car, the normal state of affairs.

Two parts that are easy to leave off, both fitted: the **1 kΩ `RSTb` pull-up
to VIO** (`R35`; §2.1 is unconditional), and **4.7 µF + 0.1 µF at each of the
three power pins** — six capacitors (`C25`–`C30`), not two. The 0.1 µF halves
(`C26`/`C28`/`C30`) stay 0402 GCM X7R. The 4.7 µF halves (`C25`/`C27`/`C29`)
are **0603 GRT188C71C475KE13** (X7S 16 V, AEC-Q200 infotainment): GCM X7R
4.7 µF 16 V does not exist smaller than 0805, and three 0805s will not sit on
the QFN24 power pins. That is a size/rating trade for a debug console, not a
drop of the per-pin pair. The MCU tank `C1` stays the 0805 GCM part.

### USB-C specifics that are easy to get wrong

- **Two 5.1 kΩ CC resistors (`R29`, `R32`), one per CC pin.** One shared
  resistor is a common shortcut and it breaks attach detection.
- **D+/D− to both A6/A7 and B6/B7** on `J4` — a USB-2.0-only receptacle still
  has two data pairs, one per orientation; wire both or the cable only works
  one way up. `U6` (USBLC6-2SC6) carries the ESD on the pairs.
- **The shell gets an RC to ground** (`R25`/`C23`), not a hard short: ESD
  needs a path, but a DC connection between car chassis and laptop ground is a
  loop you do not want in a vehicle.

### The cross, once

`U7` TXD → PIC RF1 (`USB_TXD` net into the PIC's RX) and `U7` RXD ← PIC RF0.
The Nano wires it the same way (DS50003011 Figure 3-1). The names are already
crossed — crossing them a second time in layout is the identical trap to the
BG95's pin 11/13 naming in
[cellular-support-circuit.md](cellular-support-circuit.md).

### The console has to work in both directions

Today the traffic is one-way (`printf` out of RF0). But the server URL should
eventually be field-settable, and the device has **1024 bytes of Data EEPROM**
sitting unused — enough for host, port, and APN many times over, rewritable
without a programmer. What matters at board level:

- **The receive path is not decorative.** `U7` TXD through its series
  resistor to RF1 must stay populated even though nothing currently listens on
  UART1; dropping it makes the console output-only and the EEPROM config path
  unreachable without a PICkit.
- **No auto-reset circuit.** Do not wire DTR/RTS through an RC into MCLR: it
  would put a capacitor on MCLR outside the §3 network, fight the PICkit for
  the pin, and hand a laptop the ability to reset a module in a moving car.
  Reset belongs to `J1`.

---

## 9. Bring-up checklist (process, not values)

- [ ] CONFIG1 programmed with `RSTOSC = 000` — an erased device expects an
      external clock and a crystal-less board will not run
- [ ] MPLAB *"Power target circuit from tool"* left **off**; board powered
      from `VSYS` before the PICkit connects
- [ ] `LVP` left at its erased `1` — clearing it forces high-voltage entry on
      VPP forever after
- [ ] If the programmer objects to the MCLR RC, lift `C6` via `JP1`
- [ ] Every unused pin driven low in firmware or pulled to VSS via 1–10 kΩ
- [ ] All PPS assignments re-checked against the **48-pin** port tables
      (Table 21-1/21-2), not the 28/40-pin columns
