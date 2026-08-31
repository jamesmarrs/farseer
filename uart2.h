/**
 * @file uart2.h
 * @author james
 * @brief UART2 driver for the NEO-M9N GNSS receiver.
 *
 * UART2 is routed to RD0 (TX) / RD1 (RX): GNSS_RX -> U4 RXD, GNSS_TX <- U4 TXD.
 * Fixed at 38400 8N1, the NEO-M9N power-on default (data sheet UBX-19014285
 * sec 5.5). RMC + GGA at the configured 10 Hz is ~1.6 kB/s, about 43% of that
 * link, so the baud is never changed at runtime.
 * See board_pins.h.
 */
#ifndef UART2_H
#define UART2_H

#include <stdbool.h>
#include <stdint.h>

/* U2BRG value for BRGS = 0 at Fosc = 64 MHz: Baud = Fosc / (16 * (BRG + 1)). */
#define UART2_BRG_38400   103   /* 64 MHz / (16 * 104) = 38462 */

/** Initialize UART2 on RD0/RD1 at 38400 baud, 8N1. Call after the clock is set.
 *  Enables the UART2 receive interrupt; the caller must also enable global
 *  interrupts (INTCON0bits.GIE = 1). */
void UART2_Init(void);

/**
 * Non-blocking read of one received byte from the interrupt-fed RX ring buffer.
 * Returns true and stores the byte in @p out if one was available, false if the
 * buffer is empty.
 */
bool UART2_TryReadByte(char *out);

/** Blocking write of one byte to the GNSS (used to send UBX configuration). */
void UART2_Write(char data);

/**
 * Bytes discarded because the RX ring was full, cumulative since UART2_Init().
 *
 * The ring holds roughly 67 ms of NMEA at 38400 baud, and the foreground stalls
 * for a comparable time whenever it writes a large payload to the modem, so
 * report this: a non-zero value means the GNSS stream has gaps, and the payload
 * write needs breaking up across loop iterations.
 */
uint16_t UART2_RxDropped(void);

#endif /* UART2_H */
