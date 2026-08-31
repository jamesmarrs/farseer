/**
 * @file timer.c
 * @author james
 * @brief Timer0 millisecond tick implementation.
 *
 * Register values verified against the PIC18F57Q84 data sheet (DS40002213F):
 *   - T0CON1 (sec 24.5.2): CS = 0b010 (FOSC/4), ASYNC = 0, CKPS = 0b0110 (1:64).
 *   - T0CON0 (sec 24.5.1): MD16 = 0 (8-bit), OUTPS = 1:1, EN set last.
 *   - 8-bit mode compares TMR0L against the TMR0H period register (sec 24.2).
 *   - TMR0IE/TMR0IF live in PIE3/PIR3 bit 7 (Interrupt register map, sec 14).
 *
 * Tick math: 64 MHz / 4 = 16 MHz FOSC/4; / 64 prescaler = 250 kHz; period of
 * (249 + 1) = 250 -> 1000 Hz -> 1 ms per interrupt.
 *
 * The counter crosses the ISR boundary, so it is declared volatile per the
 * project coding-standards rule.
 */
#include <xc.h>
#include "timer.h"

static volatile uint32_t g_millis;

void Timer0_Init(void)
{
    T0CON0bits.EN = 0;          /* configure while disabled */

    T0CON1bits.CS = 0b010;      /* clock = FOSC/4 (16 MHz) */
    T0CON1bits.ASYNC = 0;       /* synchronize to FOSC/4 */
    T0CON1bits.CKPS = 0b0110;   /* prescaler 1:64 -> 250 kHz */

    T0CON0bits.MD16 = 0;        /* 8-bit timer with period register */
    T0CON0bits.OUTPS = 0b0000;  /* postscaler 1:1 */

    TMR0H = 249;                /* period: rollover every 250 counts = 1 ms */
    TMR0L = 0;

    PIR3bits.TMR0IF = 0;        /* clear stale flag */
    PIE3bits.TMR0IE = 1;        /* enable Timer0 interrupt */

    T0CON0bits.EN = 1;          /* start the timer */
}

uint32_t millis(void)
{
    /* 32-bit read is non-atomic on this 8-bit core; guard against a tick
     * landing mid-read by briefly masking interrupts. */
    uint8_t gie = INTCON0bits.GIE;
    INTCON0bits.GIE = 0;
    uint32_t now = g_millis;
    INTCON0bits.GIE = gie;
    return now;
}

void __interrupt(irq(TMR0)) Timer0_ISR(void)
{
    PIR3bits.TMR0IF = 0;
    g_millis++;
}
