# BG95-M3 Mini PCIe support circuit — design rationale

> **KiCad is the source of truth.** The circuit itself — parts, values, nets,
> footprints, MPNs — lives on the **`cellular` sheet**
> (`ki_cad_project/farseer/cellular.kicad_sch`: socket `J5`, SIM holder `J6`,
> BOM-only latch `MP1`, ESD `U9`, `R54`–`R58`, `C53`–`C61`) with the `3V3_CELL`
> buck on `3v3_cell.kicad_sch`. This document records only the reasoning a
> schematic cannot carry. If a value here ever disagrees with KiCad, KiCad
> wins.

Authoritative device source:
`datasheets/Quectel_BG95-M3_Mini_PCIe_Hardware_Design_V1.0.pdf`.

> **Read the right document.** `datasheets/quectel_bg95_series_hardware_design_v1-6.pdf`
> describes the raw **102-pin LGA module** soldered inside the card. Its pin
> numbers and its **1.8 V** UART levels do **not** apply at the Mini PCIe edge
> connector. Everything below comes from the Mini PCIe document. Getting these
> two confused is the single most expensive mistake available on this board.

---

## 1. The three findings that shape this design

**The card level-shifts internally — no level shifters needed.** Table 8
(p. 23) lists the UART lines as **3.3 V power domain** and the body text says
plainly *"The power domain of UART interface is 3.3 V."* Table 10 (p. 25) puts
`RI`, `DTR`, `W_DISABLE#`, and `PERST#` in the 3.3 V domain too. Only **PCM,
I2C, and the (U)SIM** lines are 1.8 V (Table 22/23 note 1, p. 38). The PIC at
3.3 V connects directly. Do not fit the TXS0108 that the raw-LGA design guide
calls for.

**There is no PWRKEY, and no power-on pulse to generate.** The functional
diagram (Figure 1, §2.3, p. 11) shows `VCC_3V3` feeding a boost circuit and an
**automatic power-on circuit** on the card; `PWRKEY` appears nowhere in the
52-pin map. The card boots when its rail comes up, so boot ordering is
controlled by the **`3V3_CELL` buck's EN** (`CELL_PWR_EN` into `U3` on
`3v3_cell.kicad_sch`), not by a module-side key pin. [bg95.c](../bg95.c)
drives this from RE0 with the matching active-HIGH polarity (HIGH = rail on)
— the inverse of the legacy Sixfab `HAT_PWR_OFF` scheme in
[bench-wiring.md](bench-wiring.md), which this firmware no longer targets.

**The SIM holder is ours.** `USIM_VDD/DATA/CLK/RST/DET` route out to socket
pins 8, 10, 12, 14, and 44 at **1.8 V** (Table 7, p. 19), so the full Quectel
SIM reference circuit exists on our board around `J6`.

## 2. Reading the 52-pin socket (traps, not the map)

The pin-by-pin map is the `J5` symbol in KiCad. What the schematic cannot say:

- **All four `VCC_3V3` pins (2, 39, 41, 52) must be fed.** They are spread
  across the connector deliberately; feeding only one is a current-density
  mistake. All fourteen GND pins go to the plane (Table 6, p. 18).
- Table 4 note 3 is a hard rule: **"Keep all reserved and unused pins
  unconnected."** Do not tie reserved pins to ground "to be safe" — several
  carry standard Mini PCIe functions (COEX, CLKREQ#, PETn0/PETp0, 1.5 V) that
  the card repurposes or leaves internally connected.
- **Standard-name collisions** will confuse anyone reading a generic Mini PCIe
  pinout: pins 11/13 are `REFCLK−`/`REFCLK+` in the PCIe standard but
  **UART_RX/TX** here; 23/25 are `PERn0`/`PERp0` but **UART_CTS/RTS**; 44 is
  `LED_WLAN#` but **USIM_DET**. The schematic uses the Quectel names.

## 3. Rail voltage — `3V3_CELL` stays at 3.3 V

**Decision: 3.3 V nominal. Do not raise the rail toward 3.6 V to buy droop
margin.** Recorded here because it is a tempting and dangerous optimization.

The card's input is 3.3 V ±9% (3.0–3.6 V; Table 21, p. 37), so 3.6 V is the
**ceiling of the tolerance window, not an operating point** — a ±2% buck set
at 3.6 V is already out of spec before ripple or load-release overshoot.

The decisive reason is cross-rail level compatibility. Table 22 (p. 38)
specifies the card's VOH as **`VCC_3V3` − 0.5 V to `VCC_3V3`**, so `UART_TX`
swings to whatever `3V3_CELL` is. That signal drives a PIC input powered from
the **separate `3V3_SYS` rail** at 3.3 V, and PIC I/O is rated to
**VDD + 0.3 V = 3.6 V** (DS40002213 §50.1). Raising `3V3_CELL` to 3.6 V would
sit exactly at the PIC's absolute maximum with zero margin and forward-bias
its ESD clamp on every UART idle. Because the two rails are independent,
raising one silently creates a mismatch no single-rail review would catch.

The correct fix for droop is lowering source impedance — capacitance, ESR,
and copper — which is what §4 does.

Input levels the other way are comfortable (card VIH = 0.7 × 3.3 = 2.31 V; the
PIC drives near 3.3 V), with one exception: **`PERST#` and `W_DISABLE#` have a
VIL maximum of 0.5 V** (Table 22 note 2), tighter than the 0.99 V that applies
elsewhere — drive them from a real push-pull GPIO or open-drain with a firm
pull-down, never through a lossy series resistor.

## 4. Socket power and bulk capacitance (C57–C61, C54–C56)

§3.2 (p. 18) is the governing text: in 2G the input peak current may reach
**2.7 A** during transmit, and a **low-ESR bypass capacitor no less than
470 µF** is required to prevent the voltage from dropping. Quectel's Figure 3
reference puts 470 µF + 100 nF + 33 pF + 10 pF at the card.

The reservoir is implemented as **three 220 µF polymer caps (`C57`–`C59`)**
plus `C60`/`C61` HF decoupling and the ladder's small RF-bypass caps
**`C9` (33 pF) and `C8` (10 pF)** at the socket VCC pins; the droop budget
and ESR arithmetic behind that choice are in
[power-support-circuit.md](power-support-circuit.md). (The 33 pF caps
`C54`–`C56` are *not* part of this ladder — they are the §3.3/Figure 4
EGSM900 filters on the USIM signal lines; see §5.)

Placement: `C8`/`C9` only work at RF if the loop is tiny — smallest cap
nearest the pin, so `C8` (10 pF) closest to `J5` VCC, then `C9`, then
`C61`/`C60`, with the bulk `C57`–`C59` behind them.

For thermals, LTE Cat M1 transmit is far gentler than the 2G burst — Table 21
(p. 41) gives 235–260 mA average and 495–618 mA max across bands. **The 2.7 A
figure is the EGPRS/2G case**, and it is what sets the rail.

Also from §3.2, a placement-time constraint: keep the switching supply's
power devices and routing **away from the antennas**. The `3V3_CELL` buck
(`U3`, its inductor `L3`, and catch diode `D4` on `3v3_cell.kicad_sch`) is a
switcher — keep its switch-node copper away from the card's antenna
connectors and the antenna cable run.

## 5. (U)SIM interface (J6, C53–C56, U9, R54–R56)

Only **1.8 V (U)SIM cards are supported** (§3.3, p. 19). The card supplies
`USIM_VDD` itself; our board provides the holder and protection, built from
**Figure 4** (holder with card-detect switch, p. 20).

- **Why a hinged holder** (`J6`, GCT SIM8060): the stainless cover locks over
  the card, so there is no eject spring for in-car vibration to actuate — the
  failure a push-push holder invites. The SIM is a **Hologram Hyper**
  triple-cut card punched to nano (1.62–5.5 V so 1.8 V-capable; industrial
  −40 to +105 °C).
- **Deliberate deviation from Figure 4:** the 0 Ω series links Quectel draws
  in RST/CLK/DATA (a cut/isolate debug aid, no electrical function) are
  omitted — the lines run straight from socket to holder. `R54` (15 kΩ to
  `USIM_VDD`) is the Figure 4 anti-jamming pull-up on `USIM_DATA`.
- **Card detection — why the 51 k/51 k divider (`R55`/`R56`).** Figure 4
  pulls `USIM_DET` to an always-on 1.8 V rail through 51 kΩ; the switch
  grounds it when a card is seated. The Mini PCIe card exports **no always-on
  1.8 V rail** — only `USIM_VDD`, which the modem may power down when no SIM
  is present, corrupting the detect level exactly when detection matters. So
  the bias is synthesised with a 51 k/51 k divider from `3V3_CELL`, giving
  ~1.65 V — inside the 1.2–2.0 V VIH window of the 1.8 V domain (Table 23).
  Card inserted → switch closes → `SIM_DET` = 0 V.
- **Hot-plug is disabled by default** (§3.3): firmware must send
  `AT+QSIMDET=1,0` once (0 = pin low when inserted, matching this wiring;
  saved to NV, effective after reboot) and `AT+QSIMSTAT=1` for
  insertion/removal URCs. With that, a card that bounces under vibration
  re-initialises automatically instead of leaving the modem dead until a
  power cycle — and the URC timestamps the event.
- `C53` on `USIM_VDD` must stay ≤ 1 µF and close to the holder (§3.3); the
  33 pF caps (`C54`–`C56`) filter EGSM900 interference on RST/CLK/DATA;
  `U9` (USBLC6-4SC6Y, ~3 pF/ch, SOT-23-6; same family as `U6`) is the
  §3.3-mandated ESD array.

Layout rules from §3.3, all mandatory in review: holder close to the socket,
**trace length under 200 mm**; SIM signals away from RF and power traces (in a
car, with the antenna cable and a 2.7 A switching rail nearby, this is the
real risk); socket-to-holder ground short and wide (≥ 0.5 mm); `USIM_DATA` and
`USIM_CLK` separated and shielded with ground; all SIM peripheral parts at the
holder, not the socket.

## 6. UART to the PIC (R57, R58)

Direct connection, 3.3 V both ends, **115200 8N1** matching
[uart3.c](../uart3.c) (supported rates 9600–230400, §3.5).

**Watch the naming.** Table 4 says pin 11 `UART_RX` is *"Connect to DTE's TX"*
and pin 13 `UART_TX` is *"Connect to DTE's RX"* — the names are
**card-relative**, already crossed for you. Wire PIC TX (`CELL_RX` net) to
pin 11 and PIC RX (`CELL_TX` net) to pin 13; do not cross them a second time.

`R57`/`R58` (220 Ω series) survive from the bench design: with both ends on
one board the back-power case from [bench-wiring.md](bench-wiring.md) is gone,
but they remain useful for edge-rate and ESD control.

Hardware flow control is disabled by default (`AT+IFC`) and unused by
firmware, but `CELL_CTS`/`CELL_RTS` are routed to spare PIC pins anyway — at
115200 with UDP bursts they are cheap insurance and cannot be retrofitted.

## 7. Control and indication

### PERST# (pin 22)

The only reset available, and the card's boot-order lever alongside the buck
EN. Pulled up on the card, active low (Table 10). Reset requires driving low
for **≥ 2 s and ≤ 3.8 s**, then releasing (Figure 10, p. 27), with
**VIL ≤ 0.45 V** — tighter than the general 3.3 V spec.

Drive it open-drain (`TRIS` toggling against the card's internal pull-up)
rather than push-pull, so the card's pull-up defines the idle state while the
PIC is in reset and there is no contention if the rails skew. A ≥ 2 s low is
an eternity in firmware — implement it in the existing non-blocking state
machine in [bg95.c](../bg95.c), not as a busy-wait.

> **Open item:** the belt-and-braces external pull-up (10 kΩ to `3V3_SYS`)
> and a `PERST#` test point are not currently placed in KiCad — only the
> `CELL_PERST` net. Decide before layout; a 2–3.8 s pulse is worth being able
> to scope.

### W_DISABLE# (pin 20)

Airplane-mode input, pulled up on the card, active low. Left **NC**: the pin
function is disabled by default (needs `AT+QCFG="airplanecontrol",1`), and
`AT+CFUN=4` achieves the same in software. Same 0.5 V VIL limit if ever
driven.

### LED_WWAN# (pin 42)

Open collector, **sinks up to 40 mA**; §3.7.4 requires a series resistor with
the LED (Figure 11: pin → LED → resistor → VCC; ~1 kΩ gives ≈2 mA with a red
LED). The default `AT+QCFG="ledmode",0` pattern (Table 13) is a genuinely
useful trackside diagnostic — 200/1800 ms = searching, 1800/200 ms =
registered, 125/125 ms = data — readable from across the paddock.

> **Open item:** no LED or resistor is currently placed in KiCad. If fitted,
> the resistor is not optional — the pin will sink 40 mA and cook the LED.

### RI (pin 17) and DTR (pin 31)

`RI` pulses **low for 120 ms** on a URC after
`AT+QCFG="risignaltype","physical"` (Figure 9); it is routed (`CELL_RI`) so
firmware can stop polling for downlink URCs via interrupt-on-change. `DTR`
(sleep control) is left NC.

## 8. USB (pins 36, 38) — not fitted

The card's USB 2.0 port carries AT commands, NMEA, debugging, and **firmware
upgrade** (§3.4). The update path is currently not fitted on the board; if it
is ever added: 90 Ω differential with ground surround, common-mode choke close
to the socket, low-cap ESD array, no routing under crystals/RF, minimal stubs
(§3.4, Figure 6). Until then, modem re-flash requires bench access to the
card.

## 9. RF / antenna

**Nothing on our board.** The card carries its own 50 Ω main-antenna
connector (§5.1); no 50 Ω trace, matching network, or antenna feed exists on
the host PCB. What the board must provide is **mechanical**: clearance above
the card for the U.FL plug and cable bend radius (Figure 16), a routing path
to the enclosure bulkhead, and strain relief — in a race car this cable sees
vibration continuously, so anchor it. Mating plug family per §5.4: U.FL-LP.
Off-board antenna parts are in [procurement.md](procurement.md).

## 10. ESD

Table 20 (§6.5) lists the card's own ESD ratings as **TBD**. Treat that as
"unspecified, therefore unprotected" and protect at the host: `U9` on the SIM
lines (the only user-accessible connector on this subsystem, hence the
realistic entry point — mandatory per §3.3). A socket-local rail TVS (former
`D6`) was considered and removed: `3V3_CELL` never leaves the board, load
transients are the job of the `C57`–`C61` bank, and no avalanche TVS clamps
low enough to protect a 3.6 V-max load from a failed buck (the SMAJ family
floor is 5.0 V standoff / ~9.2 V clamp; the regulator's own OVP is the real
mitigation).

## 11. Mechanical

- Full-size Mini PCIe socket (`J5`, Molex 679105700 per Figure 19). Its custom
  footprint combines the stock KiCad 52-pin Mini PCIe connector geometry with
  the remote latch land pattern from Molex drawing `SD-67910-004`: the latch
  datum is 50.40 mm from the socket datum, with Ø1.60/Ø1.10 mm locator holes,
  24.20 mm hole spacing, and four 4.80 × 3.00 mm anchor pads. The latch is
  represented by BOM-only item `MP1` (Molex 48099-5701), currently DNP.
  `MP1` intentionally has no separate PCB footprint because its complete land
  pattern is already part of `J5`. In a vehicle, fit positive retention before
  service; a card that walks out of its socket takes the telemetry link with it.
- Operating range tops out at **+75 °C** (§2.2; extended +80 °C). An
  enclosure in a race car, possibly near the transmission tunnel, can exceed
  that — plan mounting location and airflow accordingly.

---

## 12. Bring-up checklist (process, not values)

- [ ] Every RESERVED pin genuinely **unconnected** — not grounded (Table 4
      note 3)
- [ ] No level shifters anywhere on the UART — the card is 3.3 V (Table 8)
- [ ] PIC TX → pin 11, PIC RX → pin 13 (names are card-relative; do not cross
      twice)
- [ ] `PERST#` drive meets VIL ≤ 0.45 V; firmware holds it low 2–3.8 s in the
      `bg95.c` state machine
- [ ] Firmware sends `AT+QSIMDET=1,0` and `AT+QSIMSTAT=1` once (polarity
      matches the divider wiring)
- [ ] PCM and I2C left NC
- [ ] Buck switch node and inductor kept away from the antenna connector and
      cable route (§3.2 EMI warning)
- [ ] `3V3_CELL` still **3.3 V nominal** — see §3 before anyone "adds margin"
- [ ] Socket latch plus secondary retention for vibration
- [x] 10 pF ladder cap decided: fitted, with 33 pF, as `C8`/`C9` at the
      socket VCC pins (completes the Figure 3 ladder)
- [ ] Open items decided: PERST# pull-up/test point, LED_WWAN# indicator,
      modem USB access
