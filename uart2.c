/**
 * @file uart2.c
 * @author james
 * @brief UART2 (NEO-M9N GNSS) driver implementation.
 *
 * Register values verified against the PIC18F57Q84 data sheet (DS40002213F),
 * 48-pin package:
 *   - PPS output code U2TX = 0x23 (Table 21-2); RD0 valid on 48-pin (ports B/D).
 *   - U2RXPPS encoding = (PORT << 3) | PIN (ports A-D only); RD1 = (3 << 3) | 1 = 0x19.
 *   - Baud (BRGS = 0): Baud = Fosc / (16 * (U2BRG + 1)).
 *     64 MHz / (16 * 104) = 38462 -> U2BRG = 103 for 38400 (Table 35-2).
 *
 * Only the RX path is required to read NMEA. The TX pin is configured so the
 * host can send configuration to the module later if needed.
 *
 * RX is interrupt-driven into a ring buffer so the NEO-M9N (streaming at 38400
 * continuously) is never starved while the foreground services the BG95 link.
 * The U2RX vector and the U2RXIE/U2RXIF bits (PIE8/PIR8 bit 0) are per the data
 * sheet interrupt register map (DS40002213F sec 14).
 */
#include <xc.h>
#include <stdint.h>
#include "uart2.h"

/* Power-of-two size so the uint8_t indices wrap naturally at the boundary. */
#define U2_RX_BUF_SIZE 256

static volatile uint8_t rx_buf[U2_RX_BUF_SIZE];
static volatile uint8_t rx_head;   /* next write slot; owned by the ISR */
static volatile uint8_t rx_tail;   /* next read slot; owned by the foreground */

/* Bytes the ISR had to discard because the ring was full. At 38400 baud this
 * buffer holds about 67 ms of NMEA, and the foreground can block for longer than
 * that while writing a large payload to the modem, so overflow is a real
 * possibility rather than a theoretical one. Counting it makes the resulting
 * gaps in the GNSS stream visible instead of silent. */
static volatile uint16_t rx_dropped;

void UART2_Init(void)
{
    /* RD0 = TX (output), RD1 = RX (input). */
    TRISDbits.TRISD0 = 0;
    TRISDbits.TRISD1 = 1;

    /* Ensure RD0/RD1 are digital. */
    ANSELDbits.ANSELD0 = 0;
    ANSELDbits.ANSELD1 = 0;

    /* Peripheral Pin Select routing. */
    RD0PPS = 0x23;   /* U2TX -> RD0 */
    U2RXPPS = 0x19;  /* U2RX <- RD1 */

    /* Baud must be written while the module is off. The NEO-M9N power-on
     * default is 38400 and the firmware never changes it. */
    U2CON1bits.ON = 0;
    U2BRG = UART2_BRG_38400;    /* 38400 @ 64 MHz, BRGS = 0 */

    U2CON0bits.BRGS = 0;        /* normal speed (16 clocks/bit) */
    U2CON0bits.MODE = 0b0000;   /* 8-bit asynchronous UART */
    U2CON0bits.TXEN = 1;        /* enable transmitter (for optional config TX) */
    U2CON0bits.RXEN = 1;        /* enable receiver */

    rx_head = 0;
    rx_tail = 0;
    rx_dropped = 0;
    PIE8bits.U2RXIE = 1;        /* enable UART2 receive interrupt (PIE8 bit 0) */

    U2CON1bits.ON = 1;          /* enable UART2 */
}

void UART2_Write(char data)
{
    while (U2FIFObits.TXBF) {   /* wait while TX FIFO is full */
        ;
    }
    U2TXB = (uint8_t)data;
}

bool UART2_TryReadByte(char *out)
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

uint16_t UART2_RxDropped(void)
{
    /* A 16-bit read is not atomic on this 8-bit core, so mask the sole writer
     * for the copy. The UART's hardware FIFO covers the handful of instructions
     * this takes, so no byte is lost to the mask itself. */
    bool was_enabled = PIE8bits.U2RXIE;
    PIE8bits.U2RXIE = 0;
    uint16_t v = rx_dropped;
    PIE8bits.U2RXIE = was_enabled;
    return v;
}

void __interrupt(irq(U2RX)) UART2_RX_ISR(void)
{
    if (U2ERRIRbits.RXFOIF) {
        U2ERRIRbits.RXFOIF = 0; /* clear receive FIFO overflow */
    }
    if (U2ERRIRbits.FERIF) {
        (void)U2RXB;            /* discard framing-error byte (also clears FERIF) */
        return;
    }

    uint8_t b = U2RXB;          /* reading clears U2RXIF */
    uint8_t next = (uint8_t)(rx_head + 1);
    if (next != rx_tail) {
        rx_buf[rx_head] = b;
        rx_head = next;
    } else {
        rx_dropped++;           /* ring full: the byte is gone, but not silently */
    }
}
