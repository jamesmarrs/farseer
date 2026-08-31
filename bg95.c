/**
 * @file bg95.c
 * @author james
 * @brief Quectel BG95-M3 non-blocking AT driver implementation.
 *
 * Everything here is cooperative and non-blocking. BG95_Task() pumps bytes out
 * of the interrupt-fed UART3 ring buffer, runs a one-command-at-a-time AT engine
 * (at_submit/at_poll), and drives a link state machine from power-on through an
 * open UDP socket. In the READY state it services, in priority order: pending
 * downlink reads (AT+QIRD), a staged outbound datagram (AT+QISEND), and a
 * periodic signal-quality poll (AT+QCSQ). Unsolicited result codes (+QIURC) are
 * parsed off the same byte stream at any time and trigger reconnects.
 *
 * Payloads are arbitrary binary, which shapes two details that would not matter
 * for text: the QISEND echo is disabled at bring-up, and the response
 * accumulator refuses to store NUL bytes. Both are commented at the point of
 * use, and either one alone being wrong would break every send.
 *
 * AT syntax verified against Quectel_BG95BG77BG600L_Series_TCPIP_Application_
 * Note_V1.2.pdf:
 *   - AT+QICSGP=1,1,"<APN>","","",1        configure PDP context   (sec 2.1.1)
 *   - AT+QIACT=1                            activate context        (sec 2.1.2)
 *   - AT+QIOPEN=1,0,"UDP","<ip>",<port>,0,0 open UDP client        (sec 3.10.1)
 *   - AT+QISEND=0,<len> then <len> bytes    fixed-length send       (sec 2.3.7)
 *   - AT+QISDE=0                            disable the send echo   (sec 2.3.16)
 *   - +QIURC: "recv",0 then AT+QIRD=0       buffered downlink       (sec 2.4.2 / 3.2.3)
 * Link config (QCFG "nwscanmode"/"iotopmode", CPSMS, CEDRXS) and QCSQ are from
 * the Quectel BG95 AT Commands Manual (not in datasheets/); VERIFY before use.
 *
 * Raw module responses are echoed to the UART1 terminal for debugging.
 */
#include <xc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "uart1.h"
#include "uart3.h"
#include "timer.h"
#include "bg95.h"

/* ------------------------------------------------------------------------- */
/* AT engine                                                                 */
/* ------------------------------------------------------------------------- */

#define AT_BUF_LEN 200

/* at_poll() return codes. */
typedef enum {
    AT_BUSY = 0,   /* still waiting */
    AT_OK,         /* expect token seen */
    AT_FAIL,       /* error token seen */
    AT_RETRY,      /* transient-failure token seen; the command may be reissued */
    AT_TMO         /* deadline elapsed */
} at_result_t;

typedef enum { ATS_IDLE, ATS_PENDING, ATS_DONE } at_state_t;

static char        at_buf[AT_BUF_LEN];   /* accumulates response text for matching */
static uint16_t    at_len;
static const char *at_expect;
static const char *at_err;
static const char *at_retry;
static uint32_t    at_start;
static uint32_t    at_timeout;
static at_state_t  at_state;
static at_result_t at_done_result;

/* Downlink URC state and reconnect requests raised by the URC parser. */
typedef enum { DROP_NONE = 0, DROP_SOCKET, DROP_PDP } drop_t;
static volatile bool pending_recv;
static drop_t        link_drop;

/* Line buffer used purely for URC line dispatch. */
#define LINE_LEN 96
static char    line[LINE_LEN];
static uint8_t line_len;

/* Begin waiting for a response without sending anything (used after the QISEND
 * data prompt, where the module is already mid-transaction).
 *
 * Three outcomes can be matched because AT+QISEND has three: success, a hard
 * error, and SEND FAIL, which merely reports a full transmit buffer. Collapsing
 * the last two would turn ordinary backpressure into a socket teardown. Pass
 * NULL for @p err or @p retry to leave that outcome unmatched. */
static void at_wait(const char *expect, const char *err, const char *retry,
                    uint32_t timeout_ms)
{
    at_expect  = expect;
    at_err     = (err != NULL) ? err : "";
    at_retry   = (retry != NULL) ? retry : "";
    at_start   = millis();
    at_timeout = timeout_ms;
    at_len     = 0;
    at_buf[0]  = '\0';
    at_state   = ATS_PENDING;
}

/* Send a command (a "\r" is appended) and begin waiting for expect / err. */
static void at_submit(const char *cmd, const char *expect, const char *err,
                      uint32_t timeout_ms)
{
    UART3_WriteStr(cmd);
    UART3_WriteStr("\r");
    at_wait(expect, err, NULL, timeout_ms);
}

/* Discard anything still sitting in the UART3 ring, used after a transaction is
 * abandoned. Without this a response that arrives late would be matched against
 * the *next* command: a stale "SEND OK" would mark an unfinished send complete,
 * and the driver would stay one transaction behind from then on. */
static void at_flush_rx(void)
{
    char c;
    while (UART3_TryReadByte(&c)) {
        UART1_Write(c);   /* keep the debug terminal a faithful log */
    }
    line_len = 0;
}

static void bg95_handle_urc(const char *l)
{
    if (strstr(l, "+QIURC: \"recv\"") != NULL) {
        pending_recv = true;
    } else if (strstr(l, "+QIURC: \"closed\"") != NULL) {
        link_drop = DROP_SOCKET;
    } else if (strstr(l, "+QIURC: \"pdpdeact\"") != NULL) {
        link_drop = DROP_PDP;
    } else if (strstr(l, "+QSIMSTAT:") != NULL) {
        /* "+QSIMSTAT: <enable>,<inserted>" - hot-plug report (AT manual 5.9).
         * The holder switch grounds USIM_DET when the card is seated
         * (AT+QSIMDET=1,0). On (re)insertion the module re-initialises the SIM
         * by itself; if the link was up when the card bounced, the resulting
         * network detach surfaces as a pdpdeact/closed URC and the existing
         * recovery path handles it, so logging is all that is needed here. */
        const char *comma = strchr(l, ',');
        if (comma != NULL) {
            printf("\r\n[BG95] SIM %s\r\n",
                   (comma[1] == '1') ? "inserted" : "removed");
        }
    }
}

/* Drain UART3 into the AT match buffer and the URC line buffer. */
static void bg95_pump(void)
{
    char c;
    while (UART3_TryReadByte(&c)) {
        UART1_Write(c);   /* echo raw module output to the debug terminal */

        /* Never store a NUL. at_buf is matched with strstr(), so a 0x00 would
         * terminate the string early and hide every token that followed it --
         * the response would still be in the array, invisible, until the
         * transaction timed out. The module does not emit NULs in normal
         * responses, but an echoed binary payload would be full of them (see the
         * AT+QISDE=0 step in bring-up), and so could line noise. */
        if (at_state == ATS_PENDING && c != '\0') {
            if (at_len >= (AT_BUF_LEN - 1)) {
                /* Keep the buffer bounded but retain the tail so a token that
                 * spans the boundary is not lost. */
                memmove(at_buf, at_buf + (AT_BUF_LEN / 2), AT_BUF_LEN / 2);
                at_len = AT_BUF_LEN / 2;
                at_buf[at_len] = '\0';
            }
            at_buf[at_len++] = c;
            at_buf[at_len]   = '\0';

            /* Success first, so a token that contains another still resolves the
             * way the caller intended. */
            if (strstr(at_buf, at_expect) != NULL) {
                at_done_result = AT_OK;
                at_state       = ATS_DONE;
            } else if (at_err[0] != '\0' && strstr(at_buf, at_err) != NULL) {
                at_done_result = AT_FAIL;
                at_state       = ATS_DONE;
            } else if (at_retry[0] != '\0' && strstr(at_buf, at_retry) != NULL) {
                at_done_result = AT_RETRY;
                at_state       = ATS_DONE;
            }
        }

        if (c == '\n' || c == '\r') {
            if (line_len > 0) {
                line[line_len] = '\0';
                bg95_handle_urc(line);
                line_len = 0;
            }
        } else if (line_len < (LINE_LEN - 1)) {
            line[line_len++] = c;
        } else {
            line_len = 0;   /* overrun: drop the malformed line */
        }
    }
}

static at_result_t at_poll(void)
{
    if (at_state == ATS_DONE) {
        at_state = ATS_IDLE;
        return at_done_result;
    }
    if (at_state == ATS_PENDING) {
        if ((millis() - at_start) >= at_timeout) {
            at_state = ATS_IDLE;
            return AT_TMO;
        }
        return AT_BUSY;
    }
    return AT_TMO;
}

/* ------------------------------------------------------------------------- */
/* Outbound datagram staging buffer                                          */
/* ------------------------------------------------------------------------- */

/* One buffer, filled in place by the caller through BG95_ClaimTxBuffer(). The
 * driver deliberately keeps no queue: at BG95_MSG_MAX bytes a queue would cost
 * half a kilobyte per slot to duplicate buffering the telemetry ring already
 * does, and a pre-built backlog would put stale positions on the air ahead of
 * fresh ones. */
static uint8_t  tx_buf[BG95_MSG_MAX];
static uint16_t tx_len;         /* bytes to send; only meaningful when tx_ready */
static bool     tx_ready;       /* a committed datagram is awaiting transmission */

/* Uplink statistics and the consecutive-failure counter that decides when a run
 * of bad sends stops being noise and starts meaning the socket is dead. */
static BG95_TxStats tx_stats;
static uint32_t     tx_rt_total_ms;   /* sum of round-trips, for the mean */
static uint32_t     send_start_ms;    /* when the current AT+QISEND began */
static uint8_t      consec_send_fail;

/* The module's IMEI, read once at bring-up and stamped into every uplink packet.
 * This is the device identity: it cannot be misconfigured the way a hand-assigned
 * car number can, and unlike source IP and port it survives the carrier-grade NAT
 * rebinding that would otherwise make a fleet of modules indistinguishable at the
 * server. Reads as zeros until AT+GSN has been answered. */
static char imei[BG95_IMEI_LEN + 1] = "000000000000000";
static bool imei_valid;

/* Pull the IMEI out of an AT+GSN response, which returns the bare digits framed
 * by CR/LF and followed by OK (AT Commands Manual V2.0 sec 2.8). Scanning for the
 * first long-enough digit run rather than indexing at a fixed offset keeps this
 * insensitive to the exact framing and to any URC that lands mid-response. */
static void parse_gsn(const char *s)
{
    while (*s != '\0') {
        if (*s < '0' || *s > '9') {
            s++;
            continue;
        }

        uint8_t n = 0;
        while (s[n] >= '0' && s[n] <= '9') {
            n++;
        }
        if (n >= BG95_IMEI_LEN) {
            memcpy(imei, s, BG95_IMEI_LEN);
            imei[BG95_IMEI_LEN] = '\0';
            imei_valid = true;
            return;
        }
        s += n;
    }
}

/* ------------------------------------------------------------------------- */
/* Signal quality                                                            */
/* ------------------------------------------------------------------------- */

static BG95_Signal signal_snapshot;
static uint32_t    last_qcsq_ms;
static uint32_t    last_qird_ms;   /* periodic downlink-buffer poll timer */

/* Parse "+QCSQ: <mode>,<rssi>,<rsrp>,<sinr>,<rsrq>" out of the response buffer.
 * The mode is a quoted string containing no digits, so scanning for signed
 * integers after the tag reliably picks off the four numeric fields. */
static void parse_qcsq(const char *buf)
{
    const char *p = strstr(buf, "+QCSQ:");
    if (p == NULL) {
        return;
    }
    p += 6;

    int16_t vals[4];
    uint8_t n = 0;
    while (n < 4) {
        while (*p != '\0' && *p != '-' &&
               !(*p >= '0' && *p <= '9') && *p != '\r' && *p != '\n') {
            p++;
        }
        if (*p == '\0' || *p == '\r' || *p == '\n') {
            break;
        }
        char *end;
        vals[n++] = (int16_t)strtol(p, &end, 10);
        if (end == p) {
            break;
        }
        p = end;
    }

    if (n == 4) {
        signal_snapshot.rssi  = vals[0];
        signal_snapshot.rsrp  = vals[1];
        signal_snapshot.sinr  = vals[2];
        signal_snapshot.rsrq  = vals[3];
        signal_snapshot.valid = true;
        printf("\r\n[BG95] signal RSSI=%d RSRP=%d SINR=%d RSRQ=%d dBm\r\n",
               vals[0], vals[1], vals[2], vals[3]);
    }
}

/* ------------------------------------------------------------------------- */
/* Downlink parse                                                            */
/* ------------------------------------------------------------------------- */

static BG95_DownlinkHandler downlink_cb;

/* Parse an AT+QIRD response of the form:
 *   +QIRD: <len>\r\n<data>\r\nOK
 * and deliver <data> to the downlink callback. Returns true if a datagram was
 * delivered (len > 0), so the caller can immediately read again and fully drain
 * the socket buffer. */
static bool parse_qird(const char *buf)
{
    const char *p = strstr(buf, "+QIRD:");
    if (p == NULL) {
        return false;
    }
    p += 6;

    long len = strtol(p, NULL, 10);
    if (len <= 0) {
        return false;   /* no data available */
    }

    const char *nl = strchr(p, '\n');
    if (nl == NULL) {
        return false;
    }
    const uint8_t *data = (const uint8_t *)(nl + 1);

    if (downlink_cb != NULL) {
        downlink_cb(data, (uint16_t)len);
    }
    printf("\r\n[BG95] downlink %ld byte(s)\r\n", len);
    return true;
}

/* ------------------------------------------------------------------------- */
/* Link + service state machine                                              */
/* ------------------------------------------------------------------------- */

/* RC7/CELL_PWR_EN levels for the 3V3_CELL buck's EN pin: HIGH = rail (and
 * modem) on, LOW = off. */
#define CELL_PWR_ON   1
#define CELL_PWR_OFF  0

typedef enum {
    ST_PWR_HOLD,        /* hold CELL_PWR_EN LOW so the module boots after the PIC */
    ST_PWR_WAIT,        /* poll AT until the module answers */
    ST_ATE0,
    ST_GSN,             /* read back the IMEI (device identity) */
    ST_CFG_SIMDET,      /* enable SIM hot-plug detect (NV-saved, one-time) */
    ST_CFG_SIMSTAT,     /* enable +QSIMSTAT insertion/removal URCs */
    ST_CPIN,
    ST_CFG_SCANMODE,    /* force LTE (nwscanmode) */
    ST_CFG_IOTOPMODE,   /* force Cat-M1 (iotopmode) */
    ST_CFG_PSM,         /* disable Power Save Mode */
    ST_CFG_EDRX,        /* disable eDRX */
    ST_CFUN,
    ST_CGATT,
    ST_CFG_QISDE,       /* disable the QISEND payload echo */
    ST_QICSGP,
    ST_QIACT,
    ST_QICLOSE,         /* best-effort close of a stale socket 0 before opening */
    ST_QIOPEN,
    ST_READY,
    ST_BACKOFF
} link_state_t;

/* READY sub-activity: only one AT transaction runs at a time. */
typedef enum {
    RS_IDLE,
    RS_SEND_PROMPT,   /* waiting for the "> " data prompt */
    RS_SEND_WAIT,     /* waiting for "SEND OK" after writing the payload */
    RS_QIRD_WAIT,     /* waiting for the AT+QIRD response */
    RS_QCSQ_WAIT      /* waiting for the AT+QCSQ response */
} ready_sub_t;

static link_state_t state;
static ready_sub_t  ready_sub;
static bool         cmd_active;         /* an at_submit is outstanding for `state` */
static uint32_t     backoff_until;
static link_state_t backoff_next;
static char         cmd_buf[96];
static uint32_t     pwr_hold_start;     /* start of the power-off hold in ST_PWR_HOLD */
static uint32_t     rail_up_ms;         /* when CELL_PWR_EN went HIGH in ST_PWR_HOLD */
static bool         tx_enabled;         /* RA1 handed to U3TX once the rail settled */

static void enter_backoff(link_state_t next)
{
    printf("\r\n[BG95] backoff %lu ms then retry\r\n",
           (unsigned long)BG95_BACKOFF_MS);
    backoff_until = millis() + BG95_BACKOFF_MS;
    backoff_next  = next;
    cmd_active    = false;
    state         = ST_BACKOFF;
}

/* Run one attach step: submit its command on entry, then advance/backoff on the
 * result. `on_ok` is the next state; failures route through backoff to
 * `on_fail`. */
static void step(const char *cmd, const char *expect, const char *err,
                 uint32_t timeout_ms, link_state_t on_ok, link_state_t on_fail)
{
    if (!cmd_active) {
        at_submit(cmd, expect, err, timeout_ms);
        cmd_active = true;
        return;
    }
    switch (at_poll()) {
    case AT_OK:
        cmd_active = false;
        state = on_ok;
        break;
    case AT_FAIL:
    case AT_TMO:
        enter_backoff(on_fail);
        break;
    default:
        break;      /* AT_BUSY: keep waiting */
    }
}

/* Config steps are best-effort: a firmware that rejects a QCFG/CPSMS/CEDRXS
 * variant should not wedge the whole bring-up, so failures just advance. */
static void step_optional(const char *cmd, uint32_t timeout_ms, link_state_t on_next)
{
    if (!cmd_active) {
        at_submit(cmd, "OK", "ERROR", timeout_ms);
        cmd_active = true;
        return;
    }
    at_result_t r = at_poll();
    if (r == AT_BUSY) {
        return;
    }
    if (r != AT_OK) {
        printf("\r\n[BG95] optional cmd not accepted, continuing\r\n");
    }
    cmd_active = false;
    state = on_next;
}

static void begin_send(void)
{
    (void)sprintf(cmd_buf, "AT+QISEND=0,%u", (unsigned)tx_len);
    send_start_ms = millis();
    at_submit(cmd_buf, ">", NULL, 5000);
    ready_sub = RS_SEND_PROMPT;
}

/* Finish the current send transaction and release the staging buffer. The
 * datagram is never retried: repetition is handled upstream by putting each fix
 * in several consecutive datagrams, which beats an immediate resend anyway --
 * back-to-back copies die to the same radio fade, and resending into a module
 * that has just reported a full buffer is the wrong response to backpressure. */
static void end_send(void)
{
    tx_ready  = false;
    ready_sub = RS_IDLE;
}

static void note_send_ok(void)
{
    uint32_t rt = millis() - send_start_ms;
    if (rt > 0xFFFFUL) {
        rt = 0xFFFFUL;
    }

    tx_stats.sent++;
    if (tx_stats.sent == 0) {
        /* uint16 wrap, ~3.6 h at the nominal send rate. Restart the averaging
         * window rather than divide by zero below. */
        tx_stats.sent  = 1;
        tx_rt_total_ms = 0;
    }
    tx_stats.rt_last_ms = (uint16_t)rt;
    if (tx_stats.rt_min_ms == 0 || rt < tx_stats.rt_min_ms) {
        tx_stats.rt_min_ms = (uint16_t)rt;
    }
    if (rt > tx_stats.rt_max_ms) {
        tx_stats.rt_max_ms = (uint16_t)rt;
    }
    tx_rt_total_ms += rt;
    tx_stats.rt_avg_ms = (uint16_t)(tx_rt_total_ms / tx_stats.sent);

    consec_send_fail = 0;
    end_send();
}

/* A send did not complete. Individually this is unremarkable -- SEND FAIL is the
 * module reporting backpressure, and it fires exactly when coverage is already
 * poor -- so the socket is kept and the packet simply skipped. Only a sustained
 * run means the link itself is wedged and worth the several seconds a teardown
 * and reopen costs; reacting sooner would destroy a working socket and rebuild
 * it under the very conditions where QIOPEN is slowest, which can loop. */
static void note_send_failed(void)
{
    end_send();
    if (++consec_send_fail >= BG95_SEND_FAIL_LIMIT) {
        consec_send_fail = 0;
        printf("\r\n[BG95] %u consecutive send failures; reopening socket\r\n",
               (unsigned)BG95_SEND_FAIL_LIMIT);
        enter_backoff(ST_QIOPEN);
    }
}

/* Decide the next READY activity when idle: downlink read, then send, then a
 * periodic signal poll. */
static void ready_service(void)
{
    if (ready_sub != RS_IDLE) {
        return;
    }

    /* Read downlink when the module signals it (recv URC) OR on a periodic
     * poll. The "recv" URC is edge-triggered (buffer access mode reports it
     * only on an empty->non-empty transition), so a datagram that arrives while
     * another AT transaction is in flight -- or any byte left un-drained -- can
     * silence the URC permanently. Polling AT+QIRD guarantees buffered downlink
     * is always picked up regardless of the URC. */
    if (pending_recv || (millis() - last_qird_ms) >= BG95_QIRD_POLL_MS) {
        pending_recv = false;
        last_qird_ms = millis();
        at_submit("AT+QIRD=0", "OK", "ERROR", 3000);
        ready_sub = RS_QIRD_WAIT;
        return;
    }

    if (tx_ready) {
        begin_send();
        return;
    }

    if ((millis() - last_qcsq_ms) >= BG95_QCSQ_INTERVAL_MS) {
        last_qcsq_ms = millis();
        at_submit("AT+QCSQ", "OK", "ERROR", 2000);
        ready_sub = RS_QCSQ_WAIT;
        return;
    }
}

static void ready_task(void)
{
    /* Handle a reconnect requested by a URC first. */
    if (link_drop == DROP_SOCKET) {
        link_drop = DROP_NONE;
        ready_sub = RS_IDLE;
        cmd_active = false;
        printf("\r\n[BG95] socket closed; reopening\r\n");
        enter_backoff(ST_QIOPEN);
        return;
    }
    if (link_drop == DROP_PDP) {
        link_drop = DROP_NONE;
        ready_sub = RS_IDLE;
        cmd_active = false;
        printf("\r\n[BG95] PDP deactivated; reactivating\r\n");
        enter_backoff(ST_QIACT);
        return;
    }

    switch (ready_sub) {
    case RS_IDLE:
        ready_service();
        break;

    case RS_SEND_PROMPT:
        switch (at_poll()) {
        case AT_OK:
            for (uint16_t i = 0; i < tx_len; i++) {
                UART3_Write((char)tx_buf[i]);
            }
            /* Three-way match. SEND FAIL shares no substring with either of the
             * others, so all three are unambiguous. Do not shortcut this by
             * matching the common prefix "SEND ": strstr() would fire the moment
             * those five bytes landed, before OK or FAIL had arrived. */
            at_wait("SEND OK", "ERROR", "SEND FAIL", BG95_SEND_TIMEOUT_MS);
            ready_sub = RS_SEND_WAIT;
            break;
        case AT_FAIL:
        case AT_TMO:
            at_flush_rx();
            tx_stats.timeouts++;
            note_send_failed();
            break;
        default:
            break;
        }
        break;

    case RS_SEND_WAIT:
        switch (at_poll()) {
        case AT_OK:
            note_send_ok();
            break;
        case AT_RETRY:
            /* SEND FAIL: the module's transmit buffer is full. Skip this
             * datagram and stay on the socket; the next packet 200 ms from now
             * already repeats most of the fixes it carried. */
            tx_stats.send_fail++;
            note_send_failed();
            break;
        case AT_FAIL:
            note_send_failed();
            break;
        case AT_TMO:
            /* The verdict never arrived, so it may still be in transit. Clear
             * the pipe before the next command so a late "SEND OK" cannot be
             * matched against it. */
            at_flush_rx();
            tx_stats.timeouts++;
            note_send_failed();
            break;
        default:
            break;
        }
        break;

    case RS_QIRD_WAIT:
        switch (at_poll()) {
        case AT_OK:
            /* If a datagram was delivered, keep reading until the buffer is
             * empty so nothing is left to stall the edge-triggered URC. */
            if (parse_qird(at_buf)) {
                pending_recv = true;
            }
            ready_sub = RS_IDLE;
            break;
        case AT_FAIL:
        case AT_TMO:
            ready_sub = RS_IDLE;
            break;
        default:
            break;
        }
        break;

    case RS_QCSQ_WAIT:
        switch (at_poll()) {
        case AT_OK:
            parse_qcsq(at_buf);
            ready_sub = RS_IDLE;
            break;
        case AT_FAIL:
        case AT_TMO:
            ready_sub = RS_IDLE;
            break;
        default:
            break;
        }
        break;
    }
}

/* ------------------------------------------------------------------------- */
/* Public API                                                                */
/* ------------------------------------------------------------------------- */

void BG95_Init(BG95_DownlinkHandler on_downlink)
{
    downlink_cb = on_downlink;

    /* RC7 -> CELL_PWR_EN -> R49 -> U3 (TPS54560-Q1) EN on the 3V3_CELL buck.
     * HIGH enables the rail; the card auto-powers on when its rail comes up
     * (Mini PCIe HW Design V1.0 Fig. 1 - there is no PWRKEY). Drive LOW here so
     * the modem stays off until the PIC is ready; R48 (100k pull-down) holds EN
     * low while the PIC is in reset, so the card is off before firmware runs.
     * ST_PWR_HOLD drives it HIGH after BG95_PWR_HOLD_MS, and ST_PWR_WAIT then
     * waits BG95_RAIL_SETTLE_MS before UART3_EnableTx() drives the modem UART:
     * until the rail is up, RA1 stays high-Z so no current is injected into the
     * unpowered card. */
    ANSELCbits.ANSELC7 = 0;
    LATCbits.LATC7 = CELL_PWR_OFF;
    TRISCbits.TRISC7 = 0;
    pwr_hold_start = millis();

    at_state   = ATS_IDLE;
    cmd_active = false;
    ready_sub  = RS_IDLE;
    state      = ST_PWR_HOLD;
    tx_enabled = false;
    pending_recv = false;
    link_drop  = DROP_NONE;
    tx_ready   = false;
    tx_len     = 0;
    consec_send_fail = 0;
    tx_rt_total_ms = 0;
    memset(&tx_stats, 0, sizeof tx_stats);
    signal_snapshot.valid = false;
    last_qcsq_ms = millis();
    last_qird_ms = millis();
}

bool BG95_IsReady(void)
{
    return state == ST_READY;
}

uint8_t *BG95_ClaimTxBuffer(uint16_t *max_len)
{
    /* Only offered when the driver is idle, which is what lets a single buffer
     * be safe: nothing can be reading it while the caller writes. */
    if (state != ST_READY || ready_sub != RS_IDLE || tx_ready) {
        return NULL;
    }
    if (max_len != NULL) {
        *max_len = BG95_MSG_MAX;
    }
    return tx_buf;
}

void BG95_CommitTxBuffer(uint16_t len)
{
    if (len == 0 || len > BG95_MSG_MAX) {
        return;
    }
    tx_len   = len;
    tx_ready = true;
}

BG95_Signal BG95_GetSignal(void)
{
    return signal_snapshot;
}

void BG95_GetTxStats(BG95_TxStats *out)
{
    if (out != NULL) {
        *out = tx_stats;
    }
}

const char *BG95_GetImei(void)
{
    return imei;
}

bool BG95_ImeiValid(void)
{
    return imei_valid;
}

void BG95_Task(void)
{
    bg95_pump();

    switch (state) {
    case ST_PWR_HOLD:
        /* Keep the module off until the PIC has been up for BG95_PWR_HOLD_MS,
         * then drive CELL_PWR_EN HIGH to bring up 3V3_CELL (the card
         * auto-powers on with its rail) and begin the AT bring-up. */
        if ((millis() - pwr_hold_start) >= BG95_PWR_HOLD_MS) {
            LATCbits.LATC7 = CELL_PWR_ON;   /* enable the cell rail */
            rail_up_ms = millis();
            state = ST_PWR_WAIT;
        }
        break;

    case ST_PWR_WAIT:
        /* The card's rail is ramping. Leave the modem UART high-impedance until
         * it has settled, then take over TX before talking to the module. */
        if (!tx_enabled) {
            if ((millis() - rail_up_ms) < BG95_RAIL_SETTLE_MS) {
                break;
            }
            UART3_EnableTx();
            tx_enabled = true;
        }

        /* Retry AT in place until the module answers (no backoff). */
        if (!cmd_active) {
            at_submit("AT", "OK", NULL, 1000);
            cmd_active = true;
        } else {
            at_result_t r = at_poll();
            if (r == AT_OK) {
                cmd_active = false;
                state = ST_ATE0;
            } else if (r != AT_BUSY) {
                cmd_active = false;     /* timeout: try AT again */
            }
        }
        break;

    case ST_ATE0:
        step("ATE0", "OK", "ERROR", 2000, ST_GSN, ST_ATE0);
        break;

    case ST_GSN: {
        /* AT+GSN returns the bare IMEI followed by OK (AT Commands Manual V2.0
         * sec 2.8). Read once here and cached: the value never changes, so
         * querying per packet would add an AT round-trip to every send.
         *
         * Best-effort. A failure leaves the header field zeroed for the server
         * to flag, which is a far better outcome than wedging bring-up -- the
         * uplink still works without it. */
        if (!cmd_active) {
            at_submit("AT+GSN", "OK", "ERROR", 2000);
            cmd_active = true;
            break;
        }
        at_result_t r = at_poll();
        if (r == AT_BUSY) {
            break;
        }
        if (r == AT_OK) {
            parse_gsn(at_buf);
        }
        cmd_active = false;
        printf("\r\n[BG95] IMEI %s%s\r\n", imei, imei_valid ? "" : " (not read)");
        state = ST_CFG_SIMDET;
        break;
    }

    case ST_CFG_SIMDET:
        /* Hot-plug detection is DISABLED by default (Mini PCIe HW Design
         * 3.3). Insert level 0 = pin low when the card is inserted, matching
         * the board: the holder's normally-open switch grounds SIM_DET
         * against its 51k/51k divider bias when the card is seated. The
         * setting saves to NV and only takes effect after a reboot, so this
         * is one-time provisioning that a replacement modem card picks up
         * automatically; on an already-provisioned module it is a no-op.
         * Runs before CPIN so a module with no card at boot still gets
         * provisioned. Best-effort: a rejection must not wedge bring-up. */
        step_optional("AT+QSIMDET=1,0", 2000, ST_CFG_SIMSTAT);
        break;
    case ST_CFG_SIMSTAT:
        /* Report insertion/removal as "+QSIMSTAT:" URCs (also NV-saved). */
        step_optional("AT+QSIMSTAT=1", 2000, ST_CPIN);
        break;

    case ST_CPIN:
        step("AT+CPIN?", "READY", "ERROR", 5000, ST_CFG_SCANMODE, ST_CPIN);
        break;

    case ST_CFG_SCANMODE:
        /* nwscanmode 3 = LTE only. VERIFY against the AT Commands Manual. */
        step_optional("AT+QCFG=\"nwscanmode\",3,1", 2000, ST_CFG_IOTOPMODE);
        break;
    case ST_CFG_IOTOPMODE:
        /* iotopmode 0 = Cat-M1 (LTE-M) only. VERIFY against the AT Commands Manual. */
        step_optional("AT+QCFG=\"iotopmode\",0,1", 2000, ST_CFG_PSM);
        break;
    case ST_CFG_PSM:
        step_optional("AT+CPSMS=0", 2000, ST_CFG_EDRX);
        break;
    case ST_CFG_EDRX:
        step_optional("AT+CEDRXS=0", 2000, ST_CFUN);
        break;

    case ST_CFUN:
        step("AT+CFUN=1", "OK", "ERROR", 15000, ST_CGATT, ST_CFUN);
        break;
    case ST_CGATT:
        /* Poll for PS attach; a "+CGATT: 0" reply matches neither token and
         * times out, which routes back here to retry. */
        step("AT+CGATT?", "+CGATT: 1", NULL, 2000, ST_CFG_QISDE, ST_CGATT);
        break;

    case ST_CFG_QISDE:
        /* Turn off the echo of data written after the QISEND "> " prompt
         * (TCP/IP App Note V1.2 sec 2.3.16). With an ASCII payload the echo was
         * merely wasteful; with a binary one it breaks the driver outright. The
         * echo of a 512-byte payload would overrun UART3's 256-byte receive
         * ring, whose ISR discards silently, so the SEND OK that followed would
         * simply never arrive and every send would time out.
         *
         * Set explicitly rather than trusted to a default: the app note records
         * that this setting is not saved across power cycles, and the local
         * documentation does not state what the power-on value is. */
        step_optional("AT+QISDE=0", 2000, ST_QICSGP);
        break;

    case ST_QICSGP:
        if (!cmd_active) {
            (void)sprintf(cmd_buf, "AT+QICSGP=1,1,\"%s\",\"\",\"\",1", BG95_APN);
        }
        step(cmd_buf, "OK", "ERROR", 5000, ST_QIACT, ST_QICSGP);
        break;
    case ST_QIACT:
        /* QIACT max response time is 150 s per the manual. */
        step("AT+QIACT=1", "OK", "ERROR", 150000, ST_QICLOSE, ST_QICSGP);
        break;
    case ST_QICLOSE:
        /* A warm PIC reset leaves the BG95 powered, so socket 0 from the prior
         * session may still be open. Re-opening it then fails with
         * "+QIOPEN: 0,563" (socket identity has been used, TCP/IP App Note V1.2
         * Table 20). Close it first, best-effort: if no socket is open the
         * module answers ERROR, which step_optional() ignores and advances. */
        step_optional("AT+QICLOSE=0", 10000, ST_QIOPEN);
        break;
    case ST_QIOPEN:
        if (!cmd_active) {
            (void)sprintf(cmd_buf, "AT+QIOPEN=1,0,\"UDP\",\"%s\",%u,0,0",
                          BG95_SERVER_HOST, (unsigned)BG95_SERVER_PORT);
        }
        /* "OK" comes first, then the "+QIOPEN: 0,0" URC signals success. */
        step(cmd_buf, "+QIOPEN: 0,0", "ERROR", 150000, ST_READY, ST_QIACT);
        if (state == ST_READY) {
            ready_sub        = RS_IDLE;
            tx_ready         = false;   /* whatever was staged pre-drop is stale */
            consec_send_fail = 0;
            printf("\r\n[BG95] UDP socket open; link ready\r\n");
        }
        break;

    case ST_READY:
        ready_task();
        break;

    case ST_BACKOFF:
        if ((millis() - backoff_until) < 0x80000000UL) {
            /* backoff_until has passed (unsigned wrap-safe compare). */
            state = backoff_next;
        }
        break;
    }
}
