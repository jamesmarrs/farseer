
# farseer

In-car race telemetry module: GPS uplink over UDP via Quectel BG95-M3, with a
low-volume server downlink.

## Bench wiring

See [docs/bench-wiring.md](docs/bench-wiring.md) for Curiosity Nano + Sixfab
Cellular IoT HAT connections, power rails, and bring-up checklist.

## Custom board

**The KiCad project is the single source of truth for the circuit** —
schematic, nets, reference designators, values, footprints, and MPNs. Open it
with:

```bash
open ki_cad_project/farseer/farseer.kicad_pro
```

Export the rendered schematic PDF and the BOM CSV (into `docs/generated/`,
machine-generated — never hand-edit) with:

```bash
./scripts/export_kicad.sh
```

The design *rationale* — datasheet citations, sizing math, traps, and
trade-offs the schematic cannot carry — lives in `docs/`, one document per
block: [MCU](docs/mcu-support-circuit.md),
[cellular](docs/cellular-support-circuit.md),
[GNSS](docs/gnss-support-circuit.md),
[power](docs/power-support-circuit.md), and
[interconnect](docs/interconnect-and-pin-budget.md) where the pin budget is
reconciled against the 48-pin PPS tables. Off-board parts (antennas, pigtail,
SIM) and cost estimates are in [docs/procurement.md](docs/procurement.md).
Pre-KiCad drawings and BOMs are retained in `docs/_archive/` for history only
and must not be treated as authoritative.

It carries no on-board debugger, so the Curiosity Nano's one-cable-does-everything
arrangement splits in two:

| | Bench (Curiosity Nano) | Custom board |
|---|---|---|
| Program + debug | Micro-USB to the on-board ATSAMD21 | **PICkit 5** on `J_icsp`, a 6-pin ICSP header |
| 115200 console | Same cable, debugger's CDC | **USB-C** on `J_dbg`, via a CP2102N bridge |

USB on the custom board is **data only** — it never powers the board, and the
PICkit must not be asked to power the target either.

## Server UDP tunnel (LocalXpose)

The module sends its telemetry datagrams over UDP to `BG95_SERVER_HOST` /
`BG95_SERVER_PORT` (defined in `bg95.h`). During development that destination is
a [LocalXpose](https://localxpose.io/) (`loclx`) UDP tunnel that forwards public
traffic to a listener on the dev machine.

### One-time setup

```bash
loclx account login                       # authenticate (UDP forwarding needs a paid plan)
loclx endpoint reserve --port 59128 --region us   # reserve us.loclx.io:59128 (once)
```

### Run the tunnel

Start the tunnel BEFORE powering the module, and forward to the same port your
server binds:

```bash
loclx tunnel udp --reserved-endpoint us.loclx.io:59128 --to 127.0.0.1:9000
```

### Gotchas (learned the hard way)

- **Use `127.0.0.1`, never `localhost`, in `--to`.** With `--to localhost:9000`
  loclx does not forward: `localhost` can resolve to IPv6 `::1` while the server
  binds IPv4, so tunneled packets are silently dropped even though the tunnel
  shows "running". Always use the IP literal, e.g. `--to 127.0.0.1:9000`.
- **Keep the port in sync.** The reserved-endpoint port, the module's
  `BG95_SERVER_PORT` in `bg95.h`, and your server's bind port (the `--to` port)
  must all agree. The reserved endpoint's public port and the local `--to` port
  do NOT have to match each other, but the module must target the public port.
- **`--to` port must match the server's bind port**, and the server must listen
  on that UDP port (e.g. `nc -u -l 9000` for a quick stand-in).
- **UDP forwarding is a paid `loclx` feature.** On a free plan the tunnel can
  appear up but never forward UDP.
- **`SEND OK` from the BG95 only means the module handed the datagram to the
  network** — UDP has no delivery ack, so it does not confirm the server (or
  tunnel) received anything.

### Verify the public path

Independently of the module, send a probe to the public endpoint and watch the
server (or a `nc -u -l <port>` stand-in) for it:

```bash
echo "probe" | nc -u -w1 us.loclx.io 59128
```

If the probe lands, the tunnel is good and any remaining delivery gap is on the
module egress side (e.g. BG95 DNS resolution of the host). If it does not land,
the tunnel/endpoint/port/plan is the problem — no firmware change will help.

## Structure

| Path                       | Purpose                                                                                                                             |
|----------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| _build                     | The [CMake build tree](https://cmake.org/cmake/help/latest/manual/cmake.1.html#introduction-to-cmake-buildsystems), can be deleted. |
| cmake                      | Generated [CMake](https://cmake.org/) files. May be deleted if user.cmake has not been added                                        |
| .vscode                    | See [VSCode](https://code.visualstudio.com/docs/getstarted/settings)                                                                |
| .vscode/settings.json      | Workspace specific settings                                                                                                         |
| .vscode/farseer.mplab.json | The MPLAB project file, should not be deleted                                                                                       |
| out                        | Final build artifacts                                                                                                               |
