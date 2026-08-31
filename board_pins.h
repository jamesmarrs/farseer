/**
 * @file board_pins.h
 * @brief Farseer custom-board PIC18F57Q84 pin map (48-pin TQFP).
 *
 * Matches the KiCad schematic (farseer.kicad_sch + child sheets). Net names are
 * peripheral-relative (CELL_RX = card UART_RX, USB_RXD = bridge RXD, etc.).
 * Do not reassign reserved pins below to other functions.
 */
#ifndef BOARD_PINS_H
#define BOARD_PINS_H

/* --- In use by firmware -------------------------------------------------- */
/* RC7  CELL_PWR_EN   out  GPIO     -> U3 (TPS54560-Q1) EN; HIGH = 3V3_CELL on */
/* RF0  USB_RXD       out  U1TX     -> U7 CP2102N RXD (console) */
/* RF1  USB_TXD       in   U1RX     <- U7 CP2102N TXD */
/* RA1  CELL_RX       out  U3TX     -> J5 pin 11 UART_RX (via R57) */
/* RA0  CELL_TX       in   U3RX     <- J5 pin 13 UART_TX (via R58) */
/* RD0  GNSS_RX       out  U2TX     -> U4 NEO-M9N pin 21 RXD */
/* RD1  GNSS_TX       in   U2RX     <- U4 NEO-M9N pin 20 TXD */
/* RB6  ICSPCLK       —    ICSP     -> J1 PGC */
/* RB7  ICSPDAT       —    ICSP     -> J1 PGD */
/* RE3  MCLR          in   reset    -> J1 MCLR / R1 pull-up */

/* --- Wired on PCB, not driven/read by firmware yet — do not reuse -------- */
/* RB4  CELL_PERST    out  GPIO     -> J5 pin 22 PERST# (active-low reset) */
/* RB5  CELL_RI       in   INT2     <- J5 pin 17 RI (wake / URC) */
/* RD2  GNSS_RESET    out  GPIO     -> U4 pin 8 RESET_N (active-low) */
/* RC2  GNSS_1PPS     in   CCP1     <- U4 pin 3 TIMEPULSE */
/* RA2  CELL_CTS      in   U3CTS    <- J5 pin 25 UART_RTS (HW flow control) */
/* RA3  CELL_RTS      out  U3RTS    -> J5 pin 23 UART_CTS (HW flow control) */

/* --- Reserved on schematic, not wired yet -------------------------------- */
/* RB1  (spare)       —    —        reserved for W_DISABLE# if needed later */

#endif /* BOARD_PINS_H */
