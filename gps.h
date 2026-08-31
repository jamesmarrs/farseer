/**
 * @file gps.h
 * @author james
 * @brief NMEA 0183 line assembler + parser for the NEO-M9N.
 *
 * Feed raw UART bytes to GPS_Process() one at a time. When a complete,
 * checksum-valid NMEA sentence is assembled it is parsed and the relevant
 * fields (position, speed, course, time, fix, satellites, altitude) are
 * printed to stdout (UART1 terminal) in a labeled, human-readable form.
 */
#ifndef GPS_H
#define GPS_H

#include <stdbool.h>
#include <stdint.h>

/**
 * Most recent GPS fix, updated from each locked RMC sentence. @c valid is false
 * until the first RMC with an active ("A") status has been parsed.
 *
 * Every field is a scaled integer; the struct holds no floating-point values
 * and the parser calls no floating-point routines. That is partly precision and
 * partly cost. On precision: XC8 builds this project with -fno-short-double, so
 * `double` is 32-bit IEEE-754 single, and because float precision is relative to
 * magnitude, running the raw NMEA "ddmm.mmmmm" field (~12213 for a longitude)
 * through atof() alone quantised position to roughly 1.8 m. Integer 1e-7 degrees
 * resolves to ~1.1 cm, far below the receiver's own 2.0 m CEP. On cost: the
 * PIC18 has no FPU, so every float operation is a software library call, and
 * keeping them out of the build reclaims several kilobytes of flash.
 *
 * Speed is carried in the receiver's own units (knots) rather than converted to
 * mph here. The conversion is a floating-point multiply that the server can do
 * for free, so it does not belong in firmware.
 */
typedef struct {
    bool     valid;          /* true once a locked RMC fix has been parsed */
    uint16_t seq;            /* increments once per locked fix; 0 before the first */
    uint32_t time_cs;        /* centiseconds since UTC midnight (0..8639999) */
    int32_t  lat_1e7;        /* signed latitude, degrees x 1e7 */
    int32_t  lng_1e7;        /* signed longitude, degrees x 1e7 */
    uint16_t speed_kn_x100;  /* RMC speed over ground, knots x 100 */
    uint16_t course_x10;     /* RMC course over ground, degrees x 10 */
} GPS_Fix;

/**
 * Copy the most recent GPS fix into @p out. Check @c out->valid before use.
 *
 * @c seq changes on every locked epoch, so a caller that remembers the last
 * value it saw can tell a fresh fix from a repeat of the previous one without
 * any separate notification.
 */
void GPS_GetFix(GPS_Fix *out);

/**
 * Send RAM-layer UBX configuration to the NEO-M9N: automotive dynamic model,
 * 10 Hz measurement rate, and an RMC + GGA only NMEA output set
 * (GLL/GSA/GSV/VTG disabled). That stream is ~1.6 kB/s, comfortably inside the
 * module's 38400 power-on default, so the link baud is never changed. Requires
 * the PIC TX -> GNSS RX wire. Must be re-sent each boot because the config is
 * written to the RAM layer only, never persisted to flash.
 */
void GPS_Configure(void);

/** True once the module has ACKed the UBX-CFG-VALSET from GPS_Configure(). */
bool GPS_ConfigAcked(void);

/**
 * Bench diagnostics: report cumulative counts since boot. @p bytes receives the
 * total raw bytes fed to GPS_Process(); @p sentences receives the total
 * checksum-valid NMEA sentences parsed. Either pointer may be NULL. Use to tell
 * "no bytes" (wiring/power/baud) from "bytes but no valid frames" (baud
 * mismatch) from "valid frames but no fix".
 */
void GPS_RxStats(uint32_t *bytes, uint32_t *sentences);

/** Feed one received byte from the GPS UART. */
void GPS_Process(char c);

#endif /* GPS_H */
