# Procurement — off-board parts, costs, and pre-order checks

The **on-board** parts list is generated from KiCad — run
`scripts/export_kicad.sh` and use `docs/generated/farseer-bom.csv`
(Reference, Value, Footprint, MPN, Manufacturer, Alt MPN, Description, DNP).
This document covers what a KiCad BOM export cannot: parts that never touch
the host PCB, rough cost expectations, and the ordering checks.

Authoritative sources:

- `datasheets/Quectel_BG95-M3_Mini_PCIe_Hardware_Design_V1.0.pdf` — §5
  (antenna connection): connector type, band list (Table 17), antenna and
  cable-loss requirements (Table 20), U.FL-LP mating-plug recommendation
  (§5.4), mated space factor (Figure 16).
- [Taoglas CAB.011 datasheet](https://cdn.taoglas.com/datasheets/CAB.011.pdf)
- [Taoglas TG.30.8113 datasheet](https://www.taoglas.com/datasheets/TG.30.8113W.pdf)

---

## 1. LTE antenna feed (off-board)

The LTE RF chain is entirely off-board: the BG95-M3 Mini PCIe card carries
its own 50 Ω MAIN antenna receptacle (Hardware Design §5.1, Table 16), so the
path is card receptacle → pigtail → enclosure bulkhead → antenna. Contrast
with the GNSS side, where the connector (`J3`) and ESD diode (`D5`) are real
board parts on `gps.kicad_sch` because the NEO-M9N's RF_IN pin is on our PCB.

| Ref | Qty | Value / description | Suggested MPN | Notes |
|-----|-----|---------------------|---------------|-------|
| X_pigtail | 1 | Pigtail, IPEX MHF I plug → SMA(F) bulkhead straight, 95 mm of 1.13 mm coax, 50 Ω, VSWR ≤ 1.3 to 6 GHz | **Taoglas CAB.011** | MHF I mates the card's U.FL-type MAIN receptacle (§5.4 recommends the U.FL-LP family — **not MHF4**, which looks identical and does not mate). Loss ≈ 0.27 dB at 2 GHz for the 95 mm run plus ~0.2–0.3 dB of connector transitions, well inside the Table 20 budget (< 1 dB low bands / < 1.5 dB high bands). D-cut bulkhead: use a D-hole panel cutout for anti-rotation under vibration |
| X_ant | 1 | LTE antenna, SMA(M), 50 Ω, covering 663–2180 MHz (Cat M1 bands, Table 17) + GSM850/900/DCS1800/PCS1900 | **Taoglas TG.30.8113** (Apex, hinged SMA(M), 600–6000 MHz dipole) | Ground-plane independent, 70 %+ typical efficiency (Table 20 requires > 30 %, VSWR ≤ 2 — verify the per-band VSWR plot for B2/B4/B12/B13 before ordering). Hinge is rated for high-vibration use; the straight TG.30.8111 is an alternative with one less moving part. **Known gap: no coverage checkmarks for B71 (617–698 MHz)** — irrelevant for Cat M1, matters only if NB2 on B71 is ever required |

Nothing electrical goes on our board for this chain: no 50 Ω trace, no
matching network, no DC block, no bias-T (the MAIN receptacle carries no DC).
The card's ESD ratings for its antenna connectors are listed TBD (Table 20,
§6.5), and with no board-side RF node there is nowhere to hang a diode — the
antenna's DC-grounded element is the practical ESD path.

What the *mechanical* design owes these parts (also flagged in
[cellular-support-circuit.md](cellular-support-circuit.md) §9):

- Vertical clearance above the card for the mated MHF I plug and its cable
  bend radius (Figure 16 space factor).
- A **6.35 mm D-hole** panel cutout at the enclosure wall for the SMA(F)
  bulkhead (¼-36 UNS thread, nut + washer supplied with CAB.011).
- Cable anchoring — in a race car this cable sees vibration continuously.
- Route the pigtail away from the `3V3_CELL` buck's inductor and switch node
  (§3.2 EMI warning) and do **not** bundle it with the GNSS coax for long
  parallel runs.

## 2. Other off-board items (no line in any BOM)

- **BG95-M3 Mini PCIe card** — plugs into `J5`; the socket is on the board,
  the card is a purchase.
- **GNSS antenna** — SMA(M) onto `J3`. Passive or active decides the bias-T
  populate option on `gps.kicad_sch`; see
  [gnss-support-circuit.md](gnss-support-circuit.md) §5. Total external gain
  must stay ≤ 30 dB.
- **SIM card** — Hologram Hyper, triple-cut punched to nano (4FF); 1.8 V
  capable, industrial temperature grade.
- **PCB fabrication and the enclosure.**

## 3. Antenna siting (install-time, no parts)

- **LTE antenna ≥ 50 cm from the GNSS antenna** (20 cm absolute floor),
  ideally with body metal between them. The separation rule applies to the
  radiating elements — the two SMA bulkheads may sit adjacent on the
  enclosure.
- The specific threat is **LTE B13 uplink (777–787 MHz), whose 2nd harmonic
  (1554–1574 MHz) lands inside the GNSS band** — the NEO-M9N's on-module B13
  notch (IM §4.4.3) is the last line of defence, not the first.
- Verification once hardware exists: compare NMEA C/N0 with the BG95 idle vs.
  transmitting a sustained uplink on B13; a mean drop > 1–2 dB means more
  separation or re-routed cables.

## 4. Approximate cost (qty 1, USD, distributor list — order of magnitude)

| Item | Rough cost |
|------|-----------|
| On-board parts (full KiCad BOM, incl. `U1` PIC and `U4` NEO-M9N) | ~$70–108 |
| CAB.011 pigtail | ~$5–8 |
| TG.30.8113 antenna | ~$10–15 |

Excluded from all figures: the BG95-M3 card, the GNSS antenna, the SIM, the
PCB, and the enclosure. Prices are volatile — expect materially lower in
volume.

## 5. Verify before ordering

- [ ] Pigtail card end is **MHF I / U.FL-compatible**, not MHF4
- [ ] Mated plug height fits between the card and the enclosure lid
      (Figure 16)
- [ ] 95 mm reaches from the card's MAIN receptacle to the bulkhead with
      slack for strain relief and bend radius — if not, use Taoglas's cable
      builder for a custom length and re-check the loss budget
- [ ] Antenna per-band VSWR ≤ 2 and efficiency > 30 % on B2/B4/B12/B13
      (Table 20 requirements)
- [ ] B71 not required (NB2-only band; TG.30.8113 does not cover it)
- [ ] LTE antenna sited ≥ 50 cm from the GNSS antenna
- [ ] Reservoir caps (`C57`–`C59`): ESR specified at 100 kHz for the actual
      MPN, ripple-current rating covers the 2.7 A burst, voltage derating
      acceptable at 3.3 V (see
      [power-support-circuit.md](power-support-circuit.md) §5)
- [ ] Any `FB1` substitution re-checked for DCR < 0.2 Ω
- [ ] KiCad BOM re-exported (`scripts/export_kicad.sh`) after the last
      schematic change, and DNP column reviewed against the populate
      decisions (GNSS bias-T, open items in the block docs)
