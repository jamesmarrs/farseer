/**
 * @file uart3.h
 * @author james
 * @brief UART3 driver for the Quectel BG95-M3 Mini PCIe card.
 *
 * UART3 is routed to RA1 (TX) / RA0 (RX): CELL_RX -> J5 pin 11 UART_RX,
 * CELL_TX <- J5 pin 13 UART_TX. Both ends are 3.3 V on this board (Mini PCIe
 * HW Design V1.0 Table 8). Configured for 115200 8N1 to match the BG95 default
 * baud. See board_pins.h.
 */
#ifndef UART3_H
#define UART3_H

#include <stdbool.h>

/** Initialize UART3 on RA1/RA0 at 115200 baud, 8N1. Call after the clock is set.
 *  Enables the UART3 receive interrupt; the caller must also enable global
 *  interrupts (INTCON0bits.GIE = 1).
 *
 *  RX is live immediately, but TX is left high-impedance: see UART3_EnableTx(). */
void UART3_Init(void);

/**
 * Hand RA1 over to the U3TX output driver. Must not be called until the
 * 3V3_CELL rail is up: until then the card is unpowered and a driven TX line
 * would inject current into its input clamp through R57.
 */
void UART3_EnableTx(void);

/**
 * Non-blocking read of one received byte from the interrupt-fed RX ring buffer.
 * Returns true and stores the byte in @p out if one was available, false if the
 * buffer is empty.
 */
bool UART3_TryReadByte(char *out);

/** Blocking single-byte transmit. */
void UART3_Write(char data);

/** Blocking transmit of a NUL-terminated string (e.g. an AT command body). */
void UART3_WriteStr(const char *s);

#endif /* UART3_H */
