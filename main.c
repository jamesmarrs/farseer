/**
 * @file main.c
 * @author james
 * @date 2026-07-03
 * @brief Farseer prototype: non-blocking superloop tying the NEO-M9N GNSS and the
 *        BG95-M3 cellular link together.
 *
 * The loop never blocks: UART RX is interrupt-fed into ring buffers, GPS bytes
 * are drained and parsed, and BG95_Task() cooperatively brings up an LTE-M link,
 * transmits datagrams, monitors signal quality, and delivers downlink data. A
 * cellular stall therefore can no longer starve GPS ingest.
 *
 * Capture and transmit run at different rates on purpose. Every fix the NEO-M9N
 * produces (10 Hz) goes into the telemetry ring; the uplink drains overlapping
 * windows out of it at 5 Hz, so each fix rides in several consecutive datagrams.
 * Nothing is discarded for being un-sendable at the moment it was measured, and a
 * modem stall shows up as latency the server's livestream delay absorbs rather
 * than as a hole in the data.
 *
 * Data flow:  NEO-M9N TX --(38400)--> RD1/UART2 (ISR) --> GPS_Process --> UART1 terminal
 *             (module runs at its 38400 power-on default; RMC+GGA at 10 Hz is
 *              ~1.6 kB/s, about 43% of that link, so no baud change is needed)
 *             GPS_GetFix --> telemetry ring --> binary batch --> UART3 --> BG95 --> UDP server
 *
 * Pin assignments: see board_pins.h.
 */

// CONFIG1 (see DS40002213F sec 8.5.1)
#pragma config FEXTOSC = OFF            // External oscillator not enabled
#pragma config RSTOSC = HFINTOSC_64MHZ  // Power-up with HFINTOSC @ 64 MHz, CDIV 1:1

// CONFIG3 (sec 8.5.3)
#pragma config MCLRE = EXTMCLR          // MCLR pin enabled (RE3)

// CONFIG4 (sec 8.5.4)
#pragma config LVP = ON                 // Low-voltage programming (ICSP / PICkit)

// CONFIG5 (sec 8.5.5)
#pragma config WDTE = OFF               // Watchdog timer disabled

#include <xc.h>
#include <stdio.h>
#include "board_pins.h"
#include "uart1.h"
#include "uart2.h"
#include "uart3.h"
#include "timer.h"
#include "gps.h"
#include "bg95.h"
#include "telemetry.h"

/* 5 Hz uplink. Fast enough that the server's 2-3 s livestream delay hides the
 * packetisation entirely, and slow enough that each datagram carries several
 * fixes, which is what pays for the redundancy: the per-packet overhead (IP,
 * UDP and LTE headers, plus an AT round-trip) is amortised over 8 fixes instead
 * of being paid per fix. */
#define UDP_SEND_INTERVAL_MS 200

/* How often to print the link/telemetry health beacon, in ms. */
#define HEALTH_INTERVAL_MS 5000

/**
 * @brief Downlink handler: called when a UDP datagram arrives from the server.
 *
 * The downlink is a very low volume control channel (as little as a single
 * byte), so for now the payload is echoed to the debug terminal. Hook real
 * command handling in here.
 */
static void on_downlink(const uint8_t *data, uint16_t len)
{
    printf("[BG95] downlink payload: ");
    for (uint16_t i = 0; i < len; i++) {
        printf("%02X ", data[i]);
    }
    printf(" | \"");
    for (uint16_t i = 0; i < len; i++) {
        uint8_t c = data[i];
        /* printable ASCII stays as-is; everything else shown as '.' */
        printf("%c", (c >= 0x20 && c <= 0x7E) ? (char)c : '.');
    }
    printf("\"\r\n");
}

/**
 * @brief Select HFINTOSC at 64 MHz as the system clock.
 *
 * RSTOSC already sets this at reset, but set it explicitly so the clock source
 * is unambiguous, then wait for the HFINTOSC to report ready.
 */
static void Clock_Init(void)
{
    OSCFRQbits.HFFRQ = 0b1000; // HFINTOSC = 64 MHz
    OSCCON1bits.NOSC = 0b110;  // New oscillator source = HFINTOSC
    OSCCON1bits.NDIV = 0b0000; // Clock divider = 1:1

    while (OSCCON3bits.ORDY == 0) {  // wait for clock switch to complete
        ;
    }
    while (OSCSTATbits.HFOR == 0) {  // wait for HFINTOSC to stabilize
        ;
    }
}

int main(void)
{
    Clock_Init();
    UART1_Init();
    UART2_Init();
    UART3_Init();
    Timer0_Init();
    INTCON0bits.GIE = 1;    // enable interrupts for the Timer0 millisecond tick

    printf("\r\nFarseer boot: NEO-M9N + BG95 UDP (non-blocking)\r\n");

    /* Kick off GPS config; it is re-sent below until the module ACKs, so a
     * still-booting NEO-M9N that misses the first frame is retried. */
    GPS_Configure();
    uint32_t last_gps_cfg = millis();
    printf("[GPS] link @38400; configuring for 10 Hz (RMC+GGA); awaiting ACK\r\n");

    BG95_Init(on_downlink);
    printf("[BG95] bring-up started; loop is non-blocking\r\n");

    Telemetry_Init();

    uint32_t last_send = millis();
    uint32_t last_health = millis();
    uint16_t last_fix_seq = 0;      /* seq of the last fix pushed to the ring */
    bool     link_was_ready = false;
    for (;;) {
        /* Drain GPS bytes so the NEO-M9N is never starved, regardless of what
         * the cellular link is doing. */
        char c;
        while (UART2_TryReadByte(&c)) {
            GPS_Process(c);
        }

        /* Re-send the GPS config once per second until the module ACKs it, in
         * case the NEO-M9N was still booting when the first frame was sent. */
        if (!GPS_ConfigAcked() && (millis() - last_gps_cfg) >= 1000) {
            last_gps_cfg = millis();
            GPS_Configure();
        }

        /* Advance the cellular link/send/receive state machine. */
        BG95_Task();

        /* Capture every locked fix at the full nav rate. GPS_Fix.seq advances
         * once per locked epoch, so comparing it is how a fresh fix is told from
         * a repeat read of the previous one. This is polled rather than driven
         * from the parser so the ring is filled from the foreground, where a
         * long BG95 transaction cannot preempt it mid-update. */
        GPS_Fix fix;
        GPS_GetFix(&fix);
        if (fix.valid && fix.seq != last_fix_seq) {
            last_fix_seq = fix.seq;
            Telemetry_PushFix(&fix);
        }

        /* Fixes pile up during the seconds the modem spends attaching at boot.
         * Zero the overflow counter the moment the link comes up so the server
         * is not told a healthy boot lost data. */
        if (BG95_IsReady() != link_was_ready) {
            link_was_ready = BG95_IsReady();
            if (link_was_ready) {
                Telemetry_LinkReady();
            }
        }

        /* Build and hand over the next datagram. The buffer is only offered when
         * the driver is idle, so the packet is always assembled from the newest
         * ring contents rather than having gone stale waiting in a queue.
         *
         * last_send only advances on a successful claim: if the modem is busy
         * the deadline stays passed and the send happens the moment it frees up,
         * so a stall is followed by catch-up rather than by skipped slots. */
        if ((millis() - last_send) >= UDP_SEND_INTERVAL_MS) {
            uint16_t max_len;
            uint8_t *buf = BG95_ClaimTxBuffer(&max_len);
            if (buf != NULL) {
                last_send = millis();
                uint16_t n = Telemetry_BuildPacket(buf, max_len);
                if (n > 0) {
                    BG95_CommitTxBuffer(n);
                }
            }
        }

        /* Health beacon. Between them these numbers localise a fault without a
         * debugger: gps rx=0 means nothing is arriving on UART2 (wiring, power
         * or baud), rx>0 with valid=0 means the bytes are garbage (baud
         * mismatch), and valid>0 with depth=0 means the link is fine and the
         * receiver simply has no lock yet.
         *
         * Once running, watch three things. u2drop must stay at 0; if it moves,
         * the payload write is blocking long enough to lose NMEA and needs
         * chunking across loop iterations. depth should hover near the batch
         * size and return to it after a stall -- pinned near TLM_RING_SLOTS
         * means the uplink is not keeping up and fixes are being lost. And the
         * QISEND round-trip is what sets the real ceiling on send rate, so the
         * max is the number to size any future interval change against. */
        if ((millis() - last_health) >= HEALTH_INTERVAL_MS) {
            last_health = millis();

            uint32_t gps_bytes, gps_sentences;
            GPS_RxStats(&gps_bytes, &gps_sentences);
            printf("\r\n[GPS] health: rx=%lu bytes, valid=%lu sentences, "
                   "cfg_acked=%d, u2drop=%u\r\n",
                   (unsigned long)gps_bytes, (unsigned long)gps_sentences,
                   (int)GPS_ConfigAcked(), (unsigned)UART2_RxDropped());

            BG95_TxStats tx;
            BG95_GetTxStats(&tx);
            printf("[TLM] ring depth=%u/%u drops=%u | sent=%u sendfail=%u tmo=%u"
                   " | qisend ms last=%u min=%u avg=%u max=%u\r\n",
                   (unsigned)Telemetry_RingDepth(), (unsigned)TLM_RING_SLOTS,
                   (unsigned)Telemetry_DropCount(),
                   (unsigned)tx.sent, (unsigned)tx.send_fail,
                   (unsigned)tx.timeouts, (unsigned)tx.rt_last_ms,
                   (unsigned)tx.rt_min_ms, (unsigned)tx.rt_avg_ms,
                   (unsigned)tx.rt_max_ms);
        }
    }

    return 0;
}
