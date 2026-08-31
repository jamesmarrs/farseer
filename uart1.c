/**
 * @file uart1.c
 * @author james
 * @brief UART1 terminal driver implementation.
 *
 * Register values verified against the PIC18F57Q84 data sheet (DS40002213F),
 * 48-pin package:
 *   - PPS output code U1TX = 0x20 (Table 21-2); RF0 valid on 48-pin (ports B/C/F).
 *   - U1RXPPS encoding = (PORT << 3) | PIN; RF1 = (5 << 3) | 1 = 0x29 (Table 21-1).
 *   - Baud (BRGS = 0): Baud = Fosc / (16 * (U1BRG + 1)).
 *     64 MHz / (16 * 35) = 114286 -> U1BRG = 34 for 115200 (Table 35-2).
 */
#include <xc.h>
#include <stdio.h>
#include "uart1.h"

void UART1_Init(void)
{
    /* RF0 = TX (output), RF1 = RX (input). */
    TRISFbits.TRISF0 = 0;
    TRISFbits.TRISF1 = 1;

    /* Ensure RF0/RF1 are digital. */
    ANSELFbits.ANSELF0 = 0;
    ANSELFbits.ANSELF1 = 0;

    /* Peripheral Pin Select routing. */
    RF0PPS = 0x20;   /* U1TX -> RF0 */
    U1RXPPS = 0x29;  /* U1RX <- RF1 */

    /* Baud must be written while the module is off. */
    U1CON1bits.ON = 0;
    U1BRG = 34;                 /* 115200 @ 64 MHz, BRGS = 0 */

    U1CON0bits.BRGS = 0;        /* normal speed (16 clocks/bit) */
    U1CON0bits.MODE = 0b0000;   /* 8-bit asynchronous UART */
    U1CON0bits.TXEN = 1;        /* enable transmitter */
    U1CON0bits.RXEN = 1;        /* enable receiver */

    U1CON1bits.ON = 1;          /* enable UART1 */
}

void UART1_Write(char data)
{
    while (U1FIFObits.TXBF) {   /* wait while TX FIFO is full */
        ;
    }
    U1TXB = (uint8_t)data;
}

/* stdio hook: routes printf()/putchar() to UART1. */
void putch(char data)
{
    UART1_Write(data);
}
