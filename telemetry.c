/**
 * @file telemetry.c
 * @author james
 * @brief Fix ring buffer and binary uplink packet builder implementation.
 *
 * See telemetry.h for the wire format and the sizing rationale.
 */
#include <string.h>
#include "telemetry.h"
#include "gps.h"
#include "bg95.h"
#include "timer.h"

#if TLM_IMEI_LEN != BG95_IMEI_LEN
#error "packet header IMEI width must match the width the driver reads back"
#endif

/* Ring of finished wire records. Storing the encoded form rather than a parsed
 * structure means a fix has exactly one representation and building a packet is
 * a copy. */
static uint8_t  ring[TLM_RING_SLOTS][TLM_FIX_REC_LEN];
static uint8_t  head;          /* next slot to write */
static uint8_t  depth;         /* records held, saturates at TLM_RING_SLOTS */
static uint16_t newest_seq;    /* seq of the most recently pushed fix */
static uint16_t drops;         /* fixes lost to overflow since the link came up */
static bool     had_lock;      /* a locked fix has been parsed at least once */

/* seq of the newest fix in the previous packet. The difference against
 * newest_seq is how many fixes are new, which sizes the next window. */
static uint16_t last_sent_seq;

static uint32_t last_status_ms;

/* --- Little-endian field writers ------------------------------------------ */
/* Explicit shifts rather than a struct memcpy: XC8 is free to insert padding
 * between members, so a struct laid over the wire is a silent portability trap.
 * These also make the byte offsets in telemetry.h directly checkable. */

static void put_u16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)(v & 0xFFu);
    p[1] = (uint8_t)((v >> 8) & 0xFFu);
}

static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v & 0xFFu);
    p[1] = (uint8_t)((v >> 8) & 0xFFu);
    p[2] = (uint8_t)((v >> 16) & 0xFFu);
    p[3] = (uint8_t)((v >> 24) & 0xFFu);
}

/* --- Header --------------------------------------------------------------- */

/* Write the TLM_HDR_LEN-byte packet header. Gathers the modem-side fields at
 * send time so every datagram, including a no-lock status packet, carries the
 * current identity and signal picture. */
static void write_header(uint8_t *out, uint8_t n_fixes)
{
    BG95_Signal sig = BG95_GetSignal();
    const char *imei = BG95_GetImei();

    uint8_t flags = 0;
    if (had_lock)           flags |= TLM_FLAG_GPS_LOCK;
    if (GPS_ConfigAcked())  flags |= TLM_FLAG_CFG_ACKED;
    if (sig.valid)          flags |= TLM_FLAG_RSSI_OK;
    if (BG95_ImeiValid())   flags |= TLM_FLAG_IMEI_OK;

    out[0] = TLM_WIRE_VERSION;
    out[1] = n_fixes;
    memcpy(&out[2], imei, TLM_IMEI_LEN);
    /* RSSI is negative dBm; the two's-complement bit pattern is what the server
     * reads back as an int16, so the reinterpretation here is deliberate. */
    put_u16(&out[17], (uint16_t)sig.rssi);
    out[19] = flags;
    out[20] = 0;                        /* reserved */
    put_u16(&out[21], drops);
}

/* --- Public API ----------------------------------------------------------- */

void Telemetry_Init(void)
{
    head           = 0;
    depth          = 0;
    newest_seq     = 0;
    drops          = 0;
    had_lock       = false;
    last_sent_seq  = 0;
    last_status_ms = millis();
}

void Telemetry_LinkReady(void)
{
    /* Fixes necessarily pile up during the seconds the modem spends attaching,
     * and reporting those as drops would make a healthy boot look broken. */
    drops = 0;
}

void Telemetry_PushFix(const GPS_Fix *fix)
{
    if (fix == NULL || !fix->valid) {
        return;
    }

    uint8_t *rec = ring[head];
    put_u16(&rec[0],  fix->seq);
    put_u32(&rec[2],  fix->time_cs);
    put_u32(&rec[6],  (uint32_t)fix->lat_1e7);
    put_u32(&rec[10], (uint32_t)fix->lng_1e7);
    put_u16(&rec[14], fix->speed_kn_x100);
    put_u16(&rec[16], fix->course_x10);

    head = (uint8_t)((head + 1u) % TLM_RING_SLOTS);
    if (depth < TLM_RING_SLOTS) {
        depth++;
    } else {
        /* Full: head has just overwritten the oldest record. Keeping the newest
         * is deliberate -- a fix older than the server's delay window can no
         * longer be shown live, so it is the one worth losing. */
        drops++;
    }
    newest_seq = fix->seq;
    had_lock   = true;
}

uint16_t Telemetry_BuildPacket(uint8_t *out, uint16_t max_len)
{
    if (out == NULL || max_len < TLM_HDR_LEN) {
        return 0;
    }

    /* How many fixes have arrived since the previous packet. Unsigned
     * subtraction so a seq wrap is handled without a special case. */
    uint16_t delta = (uint16_t)(newest_seq - last_sent_seq);
    uint8_t  n_new = (delta > depth) ? depth : (uint8_t)delta;

    if (n_new == 0) {
        /* Nothing new to say. Emit a header-only status packet on a slow
         * cadence so the server can distinguish a car sitting without a GPS
         * lock (or with a stalled receiver) from one that is off the air. */
        if ((millis() - last_status_ms) < TLM_STATUS_INTERVAL_MS) {
            return 0;
        }
        last_status_ms = millis();
        write_header(out, 0);
        return TLM_HDR_LEN;
    }

    /* The window starts at the oldest fix not yet sent, backed up by
     * TLM_OVERLAP_FIXES already-sent ones for redundancy, and runs forward. In
     * the steady state that is 6 + 2 = 8, putting each fix in four consecutive
     * datagrams.
     *
     * Starting from the oldest rather than the newest is what makes a stall
     * recoverable. After one the backlog can exceed a single packet, and the
     * window walks forward through it a packetful at a time: at 24 fixes five
     * times a second the drain ceiling is 120 fixes/s against a 10 fixes/s
     * fill, so the backlog is gone within a couple of packets and nothing is
     * skipped. Taking the newest instead would silently abandon everything
     * beyond the cap, which is the whole reason the ring exists. */
    uint16_t oldest_seq = (uint16_t)(newest_seq - depth + 1u);
    uint16_t want_start = (uint16_t)(last_sent_seq + 1u - TLM_OVERLAP_FIXES);

    /* Distance from the oldest record still held. An underflow here means the
     * requested start has already aged out of the ring, so begin at its oldest
     * entry; the unsigned difference is enormous in that case, hence the test
     * against depth rather than against zero. */
    uint16_t start_off = (uint16_t)(want_start - oldest_seq);
    if (start_off >= depth) {
        start_off = 0;
    }

    uint16_t n = (uint16_t)(depth - start_off);
    if (n > TLM_MAX_FIXES_PER_PKT) {
        n = TLM_MAX_FIXES_PER_PKT;
    }

    uint16_t fit = (uint16_t)((max_len - TLM_HDR_LEN) / TLM_FIX_REC_LEN);
    if (n > fit) {
        n = fit;
    }
    if (n == 0) {
        return 0;
    }

    write_header(out, (uint8_t)n);

    /* Emit oldest to newest so the server sees ascending seq. The oldest record
     * sits `depth` slots back from head. */
    uint8_t idx = (uint8_t)((head + TLM_RING_SLOTS - depth + start_off) % TLM_RING_SLOTS);
    uint8_t *p  = &out[TLM_HDR_LEN];
    for (uint16_t i = 0; i < n; i++) {
        memcpy(p, ring[idx], TLM_FIX_REC_LEN);
        p += TLM_FIX_REC_LEN;
        idx = (uint8_t)((idx + 1u) % TLM_RING_SLOTS);
    }

    /* Only the fixes actually carried count as sent, so a capped packet leaves
     * the rest of the backlog to the next one. */
    last_sent_seq  = (uint16_t)(oldest_seq + start_off + n - 1u);
    last_status_ms = millis();   /* a batch counts as proof of life */

    return (uint16_t)(TLM_HDR_LEN + n * TLM_FIX_REC_LEN);
}

uint8_t Telemetry_RingDepth(void)
{
    return depth;
}

uint16_t Telemetry_DropCount(void)
{
    return drops;
}
