/**
 * @file uart3.c
 * @author james
 * @brief UART3 (Quectel BG95-M3) driver implementation.
 *
 * Register values verified against the PIC18F57Q84 data sheet (DS40002213F),
 * 48-pin package:
 *   - PPS output code U3TX = 0x26 (Table 21-2); RA1 is valid on the 48-pin part.
 *   - U3RXPPS encoding = (PORT << 3) | PIN (port A/F only); RA0 = 0x00.
 *   - Baud (BRGS = 0): Baud = Fosc / (16 * (U3BRG + 1)).
 *     64 MHz / (16 * 35) = 114286 -> U3BRG = 34 for 115200 (Table 35-2).
 *
 * Both TX and RX are used: the AT-command driver transmits commands and reads
 * the module's responses.
 *
 * RX is interrupt-driven into a ring buffer so unsolicited result codes (URCs,
 * e.g. +QIURC) that arrive between commands are never lost and the foreground is
 * never blocked spinning on the module. The U3RX vector and the U3RXIE/U3RXIF
 * bits (PIE9/PIR9 bit 0) are per the data sheet interrupt register map
 * (DS40002213F sec 14).
 */
#include <xc.h>
#include <stdint.h>
#include "uart3.h"

/* Power-of-two size so the uint8_t indices wrap naturally at the boundary. */
#define U3_RX_BUF_SIZE 256

static volatile uint8_t rx_buf[U3_RX_BUF_SIZE];
static volatile uint8_t rx_head;   /* next write slot; owned by the ISR */
static volatile uint8_t rx_tail;   /* next read slot; owned by the foreground */

void UART3_Init(void)
{
    /* RA1 = TX, RA0 = RX (input). TX is left high-impedance here: the 3V3_CELL
     * rail is still off at this point, and driving RA1 high (UART idle) would
     * push current through R57 into the unpowered card's input clamp.
     * UART3_EnableTx() takes the pin over once the rail is up. */
    TRISAbits.TRISA1 = 1;
    TRISAbits.TRISA0 = 1;

    /* Ensure RA0/RA1 are digital. */
    ANSELAbits.ANSELA0 = 0;
    ANSELAbits.ANSELA1 = 0;

    /* Peripheral Pin Select routing. */
    RA1PPS = 0x26;   /* U3TX -> RA1 */
    U3RXPPS = 0x00;  /* U3RX <- RA0 */

    /* Baud must be written while the module is off. */
    U3CON1bits.ON = 0;
    U3BRG = 34;                 /* 115200 @ 64 MHz, BRGS = 0 */

    U3CON0bits.BRGS = 0;        /* normal speed (16 clocks/bit) */
    U3CON0bits.MODE = 0b0000;   /* 8-bit asynchronous UART */
    U3CON0bits.TXEN = 1;        /* enable transmitter */
    U3CON0bits.RXEN = 1;        /* enable receiver */

    rx_head = 0;
    rx_tail = 0;
    PIE9bits.U3RXIE = 1;        /* enable UART3 receive interrupt (PIE9 bit 0) */

    U3CON1bits.ON = 1;          /* enable UART3 */
}

void UART3_EnableTx(void)
{
    TRISAbits.TRISA1 = 0;       /* hand RA1 to the U3TX output driver */
}

bool UART3_TryReadByte(char *out)
{
    /* Each side writes only its own index and single-byte accesses are atomic on
     * this 8-bit core, so no interrupt masking is needed here. */
    if (rx_head == rx_tail) {
        return false;           /* buffer empty */
    }
    *out = (char)rx_buf[rx_tail];
    rx_tail = (uint8_t)(rx_tail + 1);
    return true;
}

void __interrupt(irq(U3RX)) UART3_RX_ISR(void)
{
    if (U3ERRIRbits.RXFOIF) {
        U3ERRIRbits.RXFOIF = 0; /* clear receive FIFO overflow */
    }
    if (U3ERRIRbits.FERIF) {
        (void)U3RXB;            /* discard framing-error byte (also clears FERIF) */
        return;
    }

    uint8_t b = U3RXB;          /* reading clears U3RXIF */
    uint8_t next = (uint8_t)(rx_head + 1);
    if (next != rx_tail) {      /* drop the byte if the buffer is full */
        rx_buf[rx_head] = b;
        rx_head = next;
    }
}

void UART3_Write(char data)
{
    while (U3FIFObits.TXBF) {   /* wait while TX FIFO is full */
        ;
    }
    U3TXB = (uint8_t)data;
}

void UART3_WriteStr(const char *s)
{
    while (*s != '\0') {
        UART3_Write(*s++);
    }
}
