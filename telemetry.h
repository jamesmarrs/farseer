/**
 * @file telemetry.h
 * @author james
 * @brief Fix ring buffer and binary uplink packet builder.
 *
 * Sits between the GNSS parser and the cellular driver. Every locked fix the
 * NEO-M9N produces (10 Hz) is encoded straight into its 18-byte wire form and
 * pushed into a ring; the uplink then draws overlapping windows out of that ring
 * at 5 Hz. Decoupling the two rates means the on-air packet rate no longer
 * limits the data rate: no fix is discarded, every fix is transmitted in several
 * consecutive datagrams for redundancy, and a modem stall costs latency rather
 * than data (the ring keeps filling, and the next window is wider).
 *
 * The ring stores finished wire records rather than parsed structures, so
 * building a packet is a copy and a fix has exactly one representation.
 *
 * ---------------------------------------------------------------------------
 * Wire format v1. All multi-byte fields are little-endian and are written with
 * explicit shifts. A C struct is never memcpy'd onto the wire: XC8 is free to
 * insert padding, so a struct dump would be a silent portability trap.
 *
 * Packet header - TLM_HDR_LEN (23) bytes, once per datagram:
 *    +0  uint8   ver       = TLM_WIRE_VERSION
 *    +1  uint8   n_fixes   0 for a no-lock status packet
 *    +2  char    imei[15]  raw ASCII digits, cached at modem bring-up
 *   +17  int16   rssi_dbm  0 until the first AT+QCSQ has been parsed
 *   +19  uint8   flags     TLM_FLAG_*
 *   +20  uint8   reserved  0
 *   +21  uint16  drops     fixes lost to ring overflow since the link came up
 *
 * Fix record - TLM_FIX_REC_LEN (18) bytes, repeated n_fixes times, ordered
 * oldest to newest:
 *    +0  uint16  seq            per-fix counter, from GPS_Fix.seq
 *    +2  uint32  time_cs        centiseconds since UTC midnight
 *    +6  int32   lat_1e7        signed degrees x 1e7
 *   +10  int32   lng_1e7        signed degrees x 1e7
 *   +14  uint16  speed_kn_x100  raw NMEA knots x 100 (server converts)
 *   +16  uint16  course_x10     degrees x 10
 *
 * The version byte lets the server reject stray traffic on an open UDP port and
 * lets the format evolve. The sequence counter is not needed for ordering (the
 * timestamp does that) but distinguishes a packet lost in the network from a
 * GNSS dropout, which otherwise both look like absent timestamps.
 */
#ifndef TELEMETRY_H
#define TELEMETRY_H

#include <stdbool.h>
#include <stdint.h>
#include "gps.h"

/* --- Wire format ---------------------------------------------------------- */

#define TLM_WIRE_VERSION   1
#define TLM_HDR_LEN        23
#define TLM_FIX_REC_LEN    18
#define TLM_IMEI_LEN       15

/* Header flag bits. */
#define TLM_FLAG_GPS_LOCK  0x01   /* a locked RMC fix has been parsed */
#define TLM_FLAG_CFG_ACKED 0x02   /* the NEO-M9N ACKed our UBX config */
#define TLM_FLAG_RSSI_OK   0x04   /* rssi_dbm holds a real reading */
#define TLM_FLAG_IMEI_OK   0x08   /* imei holds a real reading */

/* --- Sizing ---------------------------------------------------------------- */

/* Ring depth in fixes. At the 10 Hz capture rate 32 slots is 3.2 s of history,
 * chosen to match the server's 2-3 s livestream delay: a modem stall shorter
 * than that window is absorbed here and never reaches the viewer. Costs
 * 32 x 18 = 576 bytes against the PIC18F57Q84's 8 KB of SRAM. */
#define TLM_RING_SLOTS     32

/* Previously-sent fixes repeated in each packet on top of the new ones. At the
 * steady state of 2 new fixes per 200 ms send, a window of 2 + 6 = 8 puts every
 * fix in four consecutive datagrams spanning 600 ms, so three consecutive
 * packet losses are survivable. Repetition is spread over time deliberately;
 * back-to-back duplicates would die to the same radio fade. */
#define TLM_OVERLAP_FIXES  6

/* Hard cap on fixes per datagram. This is the catch-up rate, and it must exceed
 * the fill rate or the ring can never recover: at 24 fixes x 5 packets/s the
 * drain ceiling is 120 fixes/s against a 10 fixes/s fill. A cap at the
 * steady-state window of 8 would sit at equilibrium instead, leaving every fix
 * permanently stale after the first stall. */
#define TLM_MAX_FIXES_PER_PKT 24

/* Hard cap on datagram size. AT+QISEND accepts up to 1460 bytes (TCP/IP App
 * Note V1.2 sec 2.3.7), but the binding limit is path MTU: an oversized UDP
 * datagram is IP-fragmented, and on cellular one lost fragment destroys the
 * whole thing. 512 bytes stays clear of that and holds the 24-fix cap
 * (23 + 24 x 18 = 455). It also bounds how long the payload write blocks the
 * main loop, which matters because nothing drains UART2 meanwhile. */
#define TLM_MAX_PAYLOAD    512

/* Cadence of the header-only status datagram sent while there is no GPS lock,
 * so the server can tell "car present, no fix" from "car offline". */
#define TLM_STATUS_INTERVAL_MS 5000

/* --- API ------------------------------------------------------------------- */

/** Reset the ring and counters. Call once before use. */
void Telemetry_Init(void);

/**
 * Note that the cellular link has reached the ready state. Zeroes the overflow
 * counter, so the drops reported to the server exclude the fixes that
 * necessarily pile up during the seconds the modem spends attaching at boot.
 */
void Telemetry_LinkReady(void);

/**
 * Encode @p fix into the ring. Call once per locked fix at the full nav rate.
 * When the ring is full the oldest entry is overwritten and the overflow
 * counter incremented: a fix older than the server's delay window is already
 * useless, so the freshest data is what survives.
 */
void Telemetry_PushFix(const GPS_Fix *fix);

/**
 * Build the next outbound datagram into @p out, which must have room for
 * @p max_len bytes. Returns the packet length, or 0 if there is nothing to send
 * right now.
 *
 * Emits a batch whenever at least one fix has arrived since the previous
 * packet, sized to cover every new fix plus TLM_OVERLAP_FIXES already-sent ones
 * and clamped by TLM_MAX_FIXES_PER_PKT and @p max_len. With no new fixes it
 * falls back to a header-only status packet on the TLM_STATUS_INTERVAL_MS
 * cadence, and otherwise returns 0.
 */
uint16_t Telemetry_BuildPacket(uint8_t *out, uint16_t max_len);

/** Fixes currently held in the ring, for the health beacon. */
uint8_t Telemetry_RingDepth(void);

/** Fixes lost to ring overflow since the link came up, for the health beacon. */
uint16_t Telemetry_DropCount(void);

#endif /* TELEMETRY_H */
