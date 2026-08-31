/**
 * @file timer.h
 * @author james
 * @brief Timer0-based millisecond tick.
 *
 * Provides a free-running millisecond counter used for AT-command response
 * timeouts and the periodic UDP send interval. Timer0 is clocked from FOSC/4
 * (16 MHz at the 64 MHz system clock) with a 1:64 prescaler and an 8-bit period
 * of 250, producing a 1 kHz interrupt.
 */
#ifndef TIMER_H
#define TIMER_H

#include <stdint.h>

/** Configure and start the Timer0 1 ms tick. Enables the Timer0 interrupt;
 *  the caller must also enable global interrupts (INTCON0bits.GIE = 1). */
void Timer0_Init(void);

/** Milliseconds elapsed since Timer0_Init(). Wraps after ~49 days. */
uint32_t millis(void);

#endif /* TIMER_H */
