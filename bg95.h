/**
 * @file bg95.h
 * @author james
 * @brief Quectel BG95-M3 non-blocking AT driver: LTE-M link + UDP uplink/downlink.
 *
 * Drives the BG95 over UART3 with the Quectel Enhanced AT command set. The whole
 * driver is non-blocking: BG95_Task() is a cooperative state machine that must be
 * called every superloop iteration. It brings up the link (forcing LTE-M and
 * disabling power-save), reads back the module IMEI, keeps a UDP socket open,
 * transmits one datagram at a time, monitors signal quality, and delivers
 * downlink data to a callback. It self-heals: PDP/socket drops and repeated send
 * failures trigger a backoff-and-reconnect rather than blocking.
 *
 * The driver holds no outbound queue. Callers build a datagram directly into its
 * single staging buffer via BG95_ClaimTxBuffer(), which is only offered when the
 * link is idle and ready; buffering telemetry across a stall belongs to the
 * layer that owns the data.
 *
 * AT syntax references:
 *   - UDP flow (QICSGP/QIACT/QIOPEN/QISEND) and the downlink URC/QIRD path are
 *     taken from Quectel_BG95BG77BG600L_Series_TCPIP_Application_Note_V1.2.pdf
 *     (QIURC "recv" sec 2.4.2, buffer-access QIRD sec 3.2.3).
 *   - Link config (QCFG "nwscanmode"/"iotopmode", CPSMS, CEDRXS) and QCSQ are in
 *     Quectel_BG95BG77BG600L_Series_AT_Commands_Manual_V2.0.pdf (datasheets/),
 *     sections 6.7 (CPSMS), 6.11 (CEDRXS) and 6.16 (QCSQ).
 *
 * Fill in BG95_APN / BG95_SERVER_HOST / BG95_SERVER_PORT for your deployment
 * before flashing.
 */
#ifndef BG95_H
#define BG95_H

#include <stdbool.h>
#include <stdint.h>

/* --- Deployment configuration (edit these) --------------------------------- */
#define BG95_APN          "hologram"                          /* Hologram IoT SIM APN */
#define BG95_SERVER_HOST  "us.loclx.io"   /* UDP server (hostname or dotted quad) */
#define BG95_SERVER_PORT  59128                              /* UDP server port (LocalXpose public port) */

/* How often to poll signal quality (AT+QCSQ) once the link is up, in ms. */
#define BG95_QCSQ_INTERVAL_MS   5000
/* How often to poll the downlink buffer (AT+QIRD). The "recv" URC is
 * edge-triggered and can be missed, so polling guarantees buffered downlink is
 * always retrieved. */
#define BG95_QIRD_POLL_MS       2000
/* Backoff before a reconnect attempt after a failure, in ms. */
#define BG95_BACKOFF_MS         3000
/* Largest single datagram, in bytes. Must match TLM_MAX_PAYLOAD: the telemetry
 * layer builds packets straight into this driver's staging buffer, and the size
 * is capped there to stay clear of path-MTU fragmentation. */
#define BG95_MSG_MAX            512
/* Consecutive failed sends tolerated before the socket is presumed dead and
 * torn down. One SEND FAIL is ordinary backpressure and one timeout is a lost
 * response; only a run of them means the link itself is wedged, and reacting
 * sooner would destroy a working socket and rebuild it under exactly the poor
 * coverage that makes QIOPEN slowest.
 *
 * Note the two failure modes run at different speeds, because SEND FAIL comes
 * back immediately while a timeout costs BG95_SEND_TIMEOUT_MS. Ten of them is
 * therefore about 2 s of backpressure but about 10 s of silence. That
 * asymmetry is the right way round: backpressure is common and self-clearing,
 * whereas a modem that has stopped answering needs the reopen. */
#define BG95_SEND_FAIL_LIMIT    10
/* How long to wait for the module's verdict after the payload is written. Once
 * SEND FAIL is matched explicitly this covers only a modem that has gone silent,
 * so it is sized against the outbound ring's few seconds of depth rather than
 * against Quectel's 120 s network-determined worst case. */
#define BG95_SEND_TIMEOUT_MS    1000
/* IMEI digit count (3GPP TS 23.003). */
#define BG95_IMEI_LEN           15
/* Hold the cell rail off (RC7/CELL_PWR_EN LOW, 3V3_CELL buck disabled) for this
 * long after PIC init before enabling it, so the BG95 always boots AFTER the
 * PIC and gets a clean power cycle. */
#define BG95_PWR_HOLD_MS        5000
/* Settling time after CELL_PWR_EN goes HIGH before the PIC drives the modem
 * UART or sends the first AT. Covers the 3V3_CELL buck's soft-start ramp so the
 * card is never presented with a driven input while its rail is still rising. */
#define BG95_RAIL_SETTLE_MS     100
/* --------------------------------------------------------------------------- */

/** Latest signal-quality snapshot decoded from AT+QCSQ. */
typedef struct {
    bool    valid;   /* true once at least one QCSQ has been parsed */
    int16_t rssi;    /* dBm */
    int16_t rsrp;    /* dBm */
    int16_t sinr;    /* dB (as reported by the module) */
    int16_t rsrq;    /* dB */
} BG95_Signal;

/**
 * Cumulative uplink statistics, for the health beacon. The round-trip figures
 * cover AT+QISEND from command submission to "SEND OK", which is the number
 * that decides how fast datagrams can be pushed; everything else in the send
 * budget is negligible beside it.
 */
typedef struct {
    uint16_t sent;         /* datagrams acknowledged with SEND OK */
    uint16_t send_fail;    /* SEND FAIL (module buffer full) */
    uint16_t timeouts;     /* no verdict returned before the deadline */
    uint16_t rt_last_ms;   /* most recent round-trip */
    uint16_t rt_min_ms;    /* minimum observed (0 if none yet) */
    uint16_t rt_max_ms;    /* maximum observed */
    uint16_t rt_avg_ms;    /* mean over all successful sends */
} BG95_TxStats;

/** Downlink handler: called with the payload of a received UDP datagram. */
typedef void (*BG95_DownlinkHandler)(const uint8_t *data, uint16_t len);

/**
 * Initialize driver state and hold the cell rail disabled (CELL_PWR_EN LOW).
 * Pass a downlink
 * handler (or NULL to ignore downlink data). Does not block; the link is brought
 * up incrementally by BG95_Task().
 */
void BG95_Init(BG95_DownlinkHandler on_downlink);

/** Advance the link/send/receive state machine. Call every superloop pass. */
void BG95_Task(void);

/** True when the UDP socket is open and datagrams are being serviced. */
bool BG95_IsReady(void);

/**
 * Borrow the driver's outbound staging buffer so a datagram can be built in
 * place. Returns NULL unless the link is ready and no datagram is already
 * awaiting transmission; on success @p max_len receives the buffer size.
 *
 * There is exactly one such buffer, and building into it directly is what keeps
 * it that way: buffering outbound data is the telemetry ring's job, so a second
 * copy here would cost hundreds of bytes of SRAM to duplicate work already done
 * upstream. Because the buffer is only handed out when the driver is idle, the
 * payload is also always built from the freshest available data rather than
 * having gone stale in a queue.
 *
 * Follow a successful claim with BG95_CommitTxBuffer(), or simply drop it -- an
 * unconsumed claim leaves the driver unchanged.
 */
uint8_t *BG95_ClaimTxBuffer(uint16_t *max_len);

/**
 * Hand the staging buffer back with @p len bytes to transmit, which must not
 * exceed the size reported by BG95_ClaimTxBuffer(). The datagram is sent once,
 * and is dropped rather than retried if the module rejects it: recovering lost
 * packets is handled upstream by transmitting each fix in several consecutive
 * datagrams.
 */
void BG95_CommitTxBuffer(uint16_t len);

/** Return the most recent signal-quality snapshot. */
BG95_Signal BG95_GetSignal(void);

/** Copy the cumulative uplink statistics into @p out. */
void BG95_GetTxStats(BG95_TxStats *out);

/**
 * The module's IMEI as BG95_IMEI_LEN ASCII digits plus a NUL terminator. Reads
 * as all zeros until AT+GSN has been answered during bring-up; check
 * BG95_ImeiValid() to tell a real reading from the placeholder.
 */
const char *BG95_GetImei(void);

/** True once the IMEI has been read back from the module. */
bool BG95_ImeiValid(void);

#endif /* BG95_H */
