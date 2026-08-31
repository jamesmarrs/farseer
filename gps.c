/**
 * @file gps.c
 * @author james
 * @brief NMEA 0183 line assembler + parser implementation.
 *
 * Parses the NEO-M9N default sentences that carry position data (RMC and GGA)
 * and prints their fields with labels. Lat/lon are converted from the NMEA
 * ddmm.mmmm format to signed decimal degrees.
 *
 * Deliberately free of floating point, including in the log formatting. The
 * PIC18 has no FPU, so atof() and printf("%f") are software library calls that
 * cost several kilobytes of flash; NMEA fields are fixed-point decimals to begin
 * with, so they are parsed straight into scaled integers and printed by
 * splitting the integer and fractional parts.
 */
#include <xc.h>
#include <stdio.h>
#include <string.h>
#include "gps.h"
#include "uart2.h"
#include "timer.h"

#define NMEA_MAX_LEN   120   /* longest sentence we buffer (bytes) */
#define NMEA_MAX_FIELDS 24   /* comma-separated fields we index */

/* Throttle sentence logging so the terminal stays readable regardless of the
 * GNSS nav rate: each sentence type is printed at most once per this interval.
 * Fix extraction still runs on every sentence. */
#define GPS_LOG_INTERVAL_MS 10000

/* Buffer size for a signed decimal-degree string, e.g. "-122.2242797". */
#define DEG_STR_LEN 14

static char line[NMEA_MAX_LEN];
static uint8_t line_len;

/* Latest position/velocity fix, updated on each locked RMC sentence. */
static GPS_Fix last_fix;

/* Set true once the module ACKs our UBX-CFG-VALSET, so the boot-time retry in
 * main() can stop resending. Only latched after GPS_Configure() has actually
 * been sent (cfg_sent), so an ACK to the baud-probe VALSET does not prematurely
 * stop the config retry loop. */
static bool cfg_acked;
static bool cfg_sent;

/* Bench diagnostics: total raw bytes fed to GPS_Process() and total
 * checksum-valid NMEA sentences parsed. Lets main() distinguish "no bytes at
 * all" (wiring/power) from "bytes but no valid frames" (baud mismatch / junk)
 * from "valid frames but no fix". */
static uint32_t rx_bytes;
static uint32_t valid_sentences;

/* Parse a decimal ASCII field into an integer scaled by 10^decimals, e.g.
 * "12.345" with decimals=2 gives 1234. Extra precision is truncated, missing
 * digits are padded with zeros, and an empty or malformed field reads as 0.
 * Integer-only replacement for atof(). */
static uint32_t parse_fixed(const char *s, uint8_t decimals)
{
    uint32_t v = 0;
    uint8_t  i = 0;

    while (s[i] >= '0' && s[i] <= '9') {
        v = v * 10u + (uint32_t)(s[i] - '0');
        i++;
    }
    if (s[i] == '.') {
        i++;
        while (decimals > 0 && s[i] >= '0' && s[i] <= '9') {
            v = v * 10u + (uint32_t)(s[i] - '0');
            i++;
            decimals--;
        }
    }
    while (decimals > 0) {
        v *= 10u;
        decimals--;
    }
    return v;
}

/* parse_fixed() with a leading sign, for fields that can go negative (e.g. GGA
 * altitude below the geoid). */
static int32_t parse_fixed_signed(const char *s, uint8_t decimals)
{
    bool neg = (s[0] == '-');
    if (neg || s[0] == '+') {
        s++;
    }
    int32_t v = (int32_t)parse_fixed(s, decimals);
    return neg ? -v : v;
}

/* Convert an NMEA "hhmmss.ss" time field to centiseconds since UTC midnight.
 * Hundredths are what the receiver emits, giving 10 ms resolution -- ample to
 * place fixes 100 ms apart at the 10 Hz nav rate. Returns 0 if the field is too
 * short or non-numeric; a real 00:00:00.00 also reads as 0, which is harmless
 * because a fix is only stored when RMC reports a lock. */
static uint32_t time_to_cs(const char *t)
{
    for (uint8_t i = 0; i < 6; i++) {
        if (t[i] < '0' || t[i] > '9') {
            return 0;   /* also catches a field shorter than hhmmss */
        }
    }

    uint32_t hh = (uint32_t)(t[0] - '0') * 10u + (uint32_t)(t[1] - '0');
    uint32_t mm = (uint32_t)(t[2] - '0') * 10u + (uint32_t)(t[3] - '0');
    uint32_t ss = (uint32_t)(t[4] - '0') * 10u + (uint32_t)(t[5] - '0');

    /* t[6] is either '.' or the NUL terminator, so this is safe to read. */
    uint32_t cs = 0;
    if (t[6] == '.' && t[7] >= '0' && t[7] <= '9') {
        cs = (uint32_t)(t[7] - '0') * 10u;
        if (t[8] >= '0' && t[8] <= '9') {
            cs += (uint32_t)(t[8] - '0');
        }
    }

    /* Max 23:59:59.99 -> 8,639,999, well inside uint32. */
    return ((hh * 60u + mm) * 60u + ss) * 100u + cs;
}

/* Print a value scaled by 10^1 as "d.d" without pulling in float printf. */
static void print_x10(uint32_t v)
{
    printf("%lu.%lu", (unsigned long)(v / 10u), (unsigned long)(v % 10u));
}

/* Print a value scaled by 10^2 as "d.dd" without pulling in float printf. */
static void print_x100(uint32_t v)
{
    printf("%lu.%02lu", (unsigned long)(v / 100u), (unsigned long)(v % 100u));
}

/* Returns true at most once per GPS_LOG_INTERVAL_MS for the given per-type
 * timestamp, so each sentence type logs on its own 10 s cadence. Primed to fire
 * on the first call. */
static bool log_due(uint32_t *last)
{
    uint32_t now = millis();
    if (*last == 0 || (now - *last) >= GPS_LOG_INTERVAL_MS) {
        *last = now ? now : 1;   /* avoid 0 so the "first call" test stays valid */
        return true;
    }
    return false;
}

void GPS_GetFix(GPS_Fix *out)
{
    if (out != NULL) {
        *out = last_fix;
    }
}

bool GPS_ConfigAcked(void)
{
    return cfg_acked;
}

void GPS_RxStats(uint32_t *bytes, uint32_t *sentences)
{
    if (bytes != NULL) {
        *bytes = rx_bytes;
    }
    if (sentences != NULL) {
        *sentences = valid_sentences;
    }
}

/* Convert a hex character to its value, or -1 if not hex. */
static int8_t hex_val(char c)
{
    if (c >= '0' && c <= '9') return (int8_t)(c - '0');
    if (c >= 'A' && c <= 'F') return (int8_t)(c - 'A' + 10);
    if (c >= 'a' && c <= 'f') return (int8_t)(c - 'a' + 10);
    return -1;
}

/**
 * Validate the trailing "*HH" checksum against the XOR of the bytes between
 * '$' and '*'. Returns 1 if valid.
 */
static uint8_t checksum_ok(const char *s)
{
    if (s[0] != '$') {
        return 0;
    }

    uint8_t sum = 0;
    uint8_t i = 1;
    while (s[i] != '\0' && s[i] != '*') {
        sum ^= (uint8_t)s[i];
        i++;
    }
    if (s[i] != '*') {
        return 0;   /* no checksum delimiter */
    }

    int8_t hi = hex_val(s[i + 1]);
    int8_t lo = hex_val(s[i + 2]);
    if (hi < 0 || lo < 0) {
        return 0;
    }
    return (uint8_t)((hi << 4) | lo) == sum;
}

/**
 * Split the sentence in place on ',' and '*' into field pointers.
 * Returns the number of fields found.
 */
static uint8_t split_fields(char *s, char *fields[], uint8_t max_fields)
{
    uint8_t n = 0;
    fields[n++] = s;
    while (*s != '\0' && n < max_fields) {
        if (*s == ',' || *s == '*') {
            char delim = *s;
            *s = '\0';
            if (delim == '*') {
                break;      /* checksum follows; stop tokenizing */
            }
            fields[n++] = s + 1;
        }
        s++;
    }
    return n;
}

/* Convert an NMEA "ddmm.mmmmm" coordinate plus its hemisphere character to
 * signed degrees scaled by 1e7. Returns 0 for an empty or malformed field.
 *
 * Deliberately integer-only. atof() here would quantise the position before any
 * arithmetic ran: see the GPS_Fix comment in gps.h. All intermediates are sized
 * to stay inside 32 bits, so no 64-bit or floating-point support is pulled in.
 */
static int32_t to_deg_1e7(const char *coord, const char *hemi)
{
    /* Integer part: every digit but the last two is whole degrees, the last two
     * are whole minutes (dd|mm, or ddd|mm for a longitude). */
    uint32_t ipart = 0;
    uint8_t  i = 0;
    while (coord[i] >= '0' && coord[i] <= '9') {
        ipart = ipart * 10u + (uint32_t)(coord[i] - '0');
        i++;
    }
    if (i < 3) {
        return 0;               /* too short to carry even d|mm */
    }

    /* Fractional minutes, normalised to exactly five digits (1e-5 min): a
     * shorter field is padded with zeros, any extra precision is discarded. */
    uint32_t frac = 0;
    uint8_t  got = 0;
    if (coord[i] == '.') {
        i++;
        while (got < 5 && coord[i] >= '0' && coord[i] <= '9') {
            frac = frac * 10u + (uint32_t)(coord[i] - '0');
            i++;
            got++;
        }
    }
    while (got < 5) {
        frac *= 10u;
        got++;
    }

    uint32_t degrees  = ipart / 100u;                        /* max 180        */
    uint32_t minutes5 = (ipart % 100u) * 100000u + frac;     /* max 5,999,999  */

    /* 1 minute is 1/60 degree, so 1e-5 min -> 1e-7 deg scales by 100/60 = 5/3.
     * Largest intermediate is 3.0e7 and the largest total 1.8e9, both inside
     * uint32 and inside int32's 2,147,483,647. Truncation costs at most one
     * count, i.e. ~1.1 cm. */
    int32_t deg_1e7 = (int32_t)(degrees * 10000000UL + (minutes5 * 5UL) / 3UL);

    if (hemi[0] == 'S' || hemi[0] == 'W') {
        deg_1e7 = -deg_1e7;
    }
    return deg_1e7;
}

/* Render degrees x 1e7 as a signed decimal-degree string for the debug log.
 * Integer-only (%lu), so it does not drag in float printf. Only the terminal
 * output uses this: the uplink carries the raw int32. */
static void format_deg(char *out, int32_t deg_1e7)
{
    uint32_t v;
    const char *sign;

    if (deg_1e7 < 0) {
        sign = "-";
        v = (uint32_t)(-deg_1e7);
    } else {
        sign = "";
        v = (uint32_t)deg_1e7;
    }

    /* %07lu keeps the leading zeros of the fraction: 45.0056700 must not print
     * as 45.56700. */
    (void)sprintf(out, "%s%lu.%07lu", sign,
                  (unsigned long)(v / 10000000UL),
                  (unsigned long)(v % 10000000UL));
}

static const char *fix_quality_str(const char *q)
{
    switch (q[0]) {
        case '0': return "no fix";
        case '1': return "GPS fix";
        case '2': return "DGPS fix";
        case '4': return "RTK fixed";
        case '5': return "RTK float";
        default:  return "unknown";
    }
}

/* Print "hhmmss.ss" as "HH:MM:SS" (fractional seconds dropped). */
static void print_time(const char *t)
{
    if (strlen(t) >= 6) {
        printf("%c%c:%c%c:%c%c", t[0], t[1], t[2], t[3], t[4], t[5]);
    } else {
        printf("--:--:--");
    }
}

/* Print "ddmmyy" as "DD/MM/20YY". */
static void print_date(const char *d)
{
    if (strlen(d) >= 6) {
        printf("%c%c/%c%c/20%c%c", d[0], d[1], d[2], d[3], d[4], d[5]);
    } else {
        printf("--/--/----");
    }
}

/* Nav-rate meter: RMC is emitted once per navigation epoch, so counting RMC
 * sentences over a 1 s window yields the actual nav rate (should read ~10 Hz).
 * Reported regardless of fix status so the rate is visible before lock. */
static void tick_nav_rate(void)
{
    static uint32_t window_start;
    static uint16_t count;

    count++;

    uint32_t now = millis();
    if (window_start == 0) {
        window_start = now ? now : 1;
        return;
    }
    if ((now - window_start) >= 1000) {
        printf("[GPS] nav rate: %u Hz\r\n", (unsigned)count);
        count = 0;
        window_start = now;
    }
}

static void parse_rmc(char *fields[], uint8_t n)
{
    if (n < 10) {
        return;
    }
    tick_nav_rate();
    const char *time   = fields[1];
    const char *status = fields[2];
    const char *lat    = fields[3];
    const char *ns     = fields[4];
    const char *lon    = fields[5];
    const char *ew     = fields[6];
    const char *speed  = fields[7];
    const char *course = fields[8];
    const char *date   = fields[9];

    static uint32_t last_log;

    if (status[0] != 'A') {
        if (log_due(&last_log)) {
            printf("[RMC] no valid fix (status=%s) time=", status[0] ? status : "?");
            print_time(time);
            printf("\r\n");
        }
        return;
    }

    /* Store the fix on every locked epoch (not gated by the log throttle) so
     * the uplink always sees the freshest position/velocity. seq advances once
     * per locked epoch, which is both the telemetry sequence number and how
     * callers detect that a new fix has landed. */
    last_fix.seq++;
    last_fix.time_cs       = time_to_cs(time);
    last_fix.lat_1e7       = to_deg_1e7(lat, ns);
    last_fix.lng_1e7       = to_deg_1e7(lon, ew);
    last_fix.speed_kn_x100 = (uint16_t)parse_fixed(speed, 2);
    last_fix.course_x10    = (uint16_t)parse_fixed(course, 1);
    last_fix.valid         = true;

    if (!log_due(&last_log)) {
        return;
    }

    char lat_str[DEG_STR_LEN], lng_str[DEG_STR_LEN];
    format_deg(lat_str, last_fix.lat_1e7);
    format_deg(lng_str, last_fix.lng_1e7);

    printf("[RMC] ");
    printf("Time="); print_time(time);
    printf(" Date="); print_date(date);
    printf(" Lat=%s Lng=%s", lat_str, lng_str);
    printf(" Speed="); print_x100(last_fix.speed_kn_x100); printf(" kn");
    printf(" Course="); print_x10(last_fix.course_x10); printf(" deg");
    printf("\r\n");
}

static void parse_gga(char *fields[], uint8_t n)
{
    if (n < 10) {
        return;
    }
    const char *time = fields[1];
    const char *lat  = fields[2];
    const char *ns   = fields[3];
    const char *lon  = fields[4];
    const char *ew   = fields[5];
    const char *qual = fields[6];
    const char *sats = fields[7];
    const char *hdop = fields[8];
    const char *alt  = fields[9];

    /* GGA is logged for diagnostics only. The stored fix comes solely from RMC
     * so that position, velocity and time in a telemetry record always belong to
     * the same navigation epoch. */
    static uint32_t last_log;
    if (!log_due(&last_log)) {
        return;
    }

    char lat_str[DEG_STR_LEN], lng_str[DEG_STR_LEN];
    format_deg(lat_str, to_deg_1e7(lat, ns));
    format_deg(lng_str, to_deg_1e7(lon, ew));

    int32_t alt_x10 = parse_fixed_signed(alt, 1);

    printf("[GGA] ");
    printf("Time="); print_time(time);
    printf(" Fix=%s Sats=%s", fix_quality_str(qual), sats[0] ? sats : "0");
    printf(" HDOP="); print_x10(parse_fixed(hdop, 1));
    printf(" Lat=%s Lng=%s", lat_str, lng_str);
    printf(" Alt=");
    if (alt_x10 < 0) {
        printf("-");
        alt_x10 = -alt_x10;
    }
    print_x10((uint32_t)alt_x10);
    printf(" m\r\n");
}

static void parse_line(void)
{
    if (line_len < 6 || line[0] != '$') {
        return;
    }
    if (!checksum_ok(line)) {
        return;     /* drop corrupted sentences silently */
    }

    valid_sentences++;

    /* The 3-char sentence type sits at line[3..5] after "$tt". */
    char type[4];
    type[0] = line[3];
    type[1] = line[4];
    type[2] = line[5];
    type[3] = '\0';

    char *fields[NMEA_MAX_FIELDS];
    uint8_t n = split_fields(line, fields, NMEA_MAX_FIELDS);

    if (strcmp(type, "RMC") == 0) {
        parse_rmc(fields, n);
    } else if (strcmp(type, "GGA") == 0) {
        parse_gga(fields, n);
    }
    /* Other sentence types (GLL, GSA, GSV, VTG, TXT) are ignored. */
}

/* Send a UBX frame (sync + class/id + little-endian length + payload + 8-bit
 * Fletcher checksum) to the GNSS over UART2. */
static void ubx_send(uint8_t cls, uint8_t id, const uint8_t *payload, uint16_t len)
{
    uint8_t hdr[6] = { 0xB5, 0x62, cls, id,
                       (uint8_t)(len & 0xFF), (uint8_t)(len >> 8) };
    uint8_t ck_a = 0, ck_b = 0;

    /* Checksum runs over class, id, length, and payload (hdr[2..5]). */
    for (uint8_t i = 2; i < 6; i++) {
        ck_a = (uint8_t)(ck_a + hdr[i]);
        ck_b = (uint8_t)(ck_b + ck_a);
    }
    for (uint16_t i = 0; i < len; i++) {
        ck_a = (uint8_t)(ck_a + payload[i]);
        ck_b = (uint8_t)(ck_b + ck_a);
    }

    for (uint8_t i = 0; i < 6; i++) {
        UART2_Write((char)hdr[i]);
    }
    for (uint16_t i = 0; i < len; i++) {
        UART2_Write((char)payload[i]);
    }
    UART2_Write((char)ck_a);
    UART2_Write((char)ck_b);
}

void GPS_Configure(void)
{
    /* One UBX-CFG-VALSET (0x06 0x8A), RAM layer, that:
     *   - selects the automotive dynamic platform model so the nav filter is
     *     tuned for vehicle motion (better heading/velocity stability, fewer
     *     jumps) rather than the default "portable" model,
     *   - sets the measurement rate to 100 ms (10 Hz nav), and
     *   - leaves only RMC + GGA enabled on UART1 (disables GLL/GSA/GSV/VTG).
     * RMC + GGA at 10 Hz is ~1.6 kB/s, about 43% of the 38400 power-on default,
     * so no baud change is needed. Keep GSV disabled: in a concurrent
     * multi-constellation fix it adds hundreds of bytes per epoch and would
     * overrun the link, at which point the module drops whole messages
     * (NEO-M9N Integration Manual sec 3.7.1).
     * Configuration key IDs are from the u-blox M9 Interface Description
     * (UBX-19035940); the module NAKs unknown keys, so a wrong key is harmless.
     * RAM layer only: this is re-sent by the firmware on every boot.
     *
     * TODO(verify): confirm CFG-NAVSPG-DYNMODEL key 0x20110021 and value 4
     * (automotive) against UBX-19035940 before relying on it; watch for an
     * ACK-ACK vs ACK-NAK on the bench. */
    static const uint8_t cfg[] = {
        0x00, 0x01, 0x00, 0x00,            /* version, layers=RAM, reserved */
        0x21, 0x00, 0x11, 0x20, 0x04,       /* CFG-NAVSPG-DYNMODEL = 4 (automotive) */
        0x01, 0x00, 0x21, 0x30, 0x64, 0x00, /* CFG-RATE-MEAS = 100 ms (10 Hz) */
        0x02, 0x00, 0x21, 0x30, 0x01, 0x00, /* CFG-RATE-NAV  = 1 cycle        */
        0xAC, 0x00, 0x91, 0x20, 0x01,       /* NMEA RMC on UART1 = 1          */
        0xBB, 0x00, 0x91, 0x20, 0x01,       /* NMEA GGA on UART1 = 1          */
        0xCA, 0x00, 0x91, 0x20, 0x00,       /* NMEA GLL on UART1 = 0          */
        0xC0, 0x00, 0x91, 0x20, 0x00,       /* NMEA GSA on UART1 = 0          */
        0xC5, 0x00, 0x91, 0x20, 0x00,       /* NMEA GSV on UART1 = 0          */
        0xB1, 0x00, 0x91, 0x20, 0x00,       /* NMEA VTG on UART1 = 0          */
    };
    cfg_sent = true;   /* from here on, a UBX-ACK-ACK means our config was taken */
    ubx_send(0x06, 0x8A, cfg, (uint16_t)sizeof cfg);
}

/* Minimal UBX receive parser: watches the GNSS byte stream for ACK-ACK (0x05
 * 0x01) / ACK-NAK (0x05 0x00) responses and reports whether our configuration
 * was accepted. Runs alongside the NMEA assembler; UBX bytes that leak into the
 * NMEA path just form junk lines that fail the checksum and are dropped. */
static void ubx_rx(uint8_t b)
{
    static uint8_t  st = 0;
    static uint8_t  cls, id, cka, ckb;
    static uint16_t len, idx;

    switch (st) {
    case 0: if (b == 0xB5) st = 1; break;
    case 1: st = (b == 0x62) ? 2 : 0; break;
    case 2: cls = b; cka = b; ckb = b; st = 3; break;
    case 3: id = b; cka = (uint8_t)(cka + b); ckb = (uint8_t)(ckb + cka); st = 4; break;
    case 4: len = b; cka = (uint8_t)(cka + b); ckb = (uint8_t)(ckb + cka); st = 5; break;
    case 5:
        len |= (uint16_t)b << 8;
        cka = (uint8_t)(cka + b);
        ckb = (uint8_t)(ckb + cka);
        idx = 0;
        st = (len == 0) ? 6 : 7;
        break;
    case 7:     /* consume payload (contents not needed for ACK/NAK) */
        cka = (uint8_t)(cka + b);
        ckb = (uint8_t)(ckb + cka);
        if (++idx >= len) st = 6;
        break;
    case 6: st = (b == cka) ? 8 : 0; break;   /* ck_a */
    case 8:                                    /* ck_b */
        if (b == ckb && cls == 0x05) {
            if (id == 0x01) {
                if (cfg_sent) {
                    cfg_acked = true;
                    printf("\r\n[GPS] UBX ACK: config accepted\r\n");
                }
            } else if (id == 0x00 && cfg_sent) {
                printf("\r\n[GPS] UBX NAK: config rejected\r\n");
            }
        }
        st = 0;
        break;
    }
}

void GPS_Process(char c)
{
    rx_bytes++;
    ubx_rx((uint8_t)c);

    if (c == '\n' || c == '\r') {
        if (line_len > 0) {
            line[line_len] = '\0';
            parse_line();
            line_len = 0;
        }
        return;
    }

    if (line_len < (NMEA_MAX_LEN - 1)) {
        line[line_len++] = c;
    } else {
        line_len = 0;   /* overflow: drop the malformed line */
    }
}
