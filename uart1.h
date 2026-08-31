/**
 * @file uart1.h
 * @author james
 * @brief UART1 console driver (USB-C via CP2102N).
 *
 * UART1 is routed to RF0 (TX) / RF1 (RX): USB_RXD -> U7 RXD, USB_TXD <- U7 TXD.
 * Configured for 115200 8N1. Overriding putch() here lets stdio printf() write
 * to this port. See board_pins.h.
 */
#ifndef UART1_H
#define UART1_H

/** Initialize UART1 on RF0/RF1 at 115200 baud, 8N1. Call after the clock is set. */
void UART1_Init(void);

/** Blocking single-byte transmit. */
void UART1_Write(char data);

#endif /* UART1_H */
