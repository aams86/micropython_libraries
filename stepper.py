from machine import Pin
from time import ticks_us, ticks_diff, sleep_us

class Stepper:
    # Stepper motor sequence for 28BYJ-48 (half-stepping)
    SEQUENCE = [
        [1, 0, 0, 0],
        [1, 1, 0, 0],
        [0, 1, 0, 0],
        [0, 1, 1, 0],
        [0, 0, 1, 0],
        [0, 0, 1, 1],
        [0, 0, 0, 1],
        [1, 0, 0, 1]
    ]

    def __init__(self, pins, steps_per_rev=4096, rpm=8):
        self.pins = [Pin(p, Pin.OUT) for p in pins]
        self.steps_per_rev = steps_per_rev
        self.rpm = rpm
        self.last_step_time = ticks_us()
        self._update_min_delay()
        self.current_index = 0

    def _update_min_delay(self):
        # Time for one step in microseconds
        steps_per_min = self.steps_per_rev * self.rpm
        self.min_delay_us = int(60_000_000 / steps_per_min)

    def set_rpm(self, rpm):
        self.rpm = rpm
        self._update_min_delay()

    def set_pins(self, pattern):
        for pin, value in zip(self.pins, pattern):
            pin.value(value)

    def step_blocking(self, direction):
        now = ticks_us()
        elapsed = ticks_diff(now, self.last_step_time)
        if elapsed < self.min_delay_us:
            sleep_us(self.min_delay_us - elapsed)
        self._advance_sequence(direction)
        self.last_step_time = ticks_us()

    def step_nonblocking(self, direction):
        now = ticks_us()
        elapsed = ticks_diff(now, self.last_step_time)
        if elapsed >= self.min_delay_us:
            self._advance_sequence(direction)
            self.last_step_time = now
            return True
        return False

    def _advance_sequence(self, direction):
        if direction > 0:
            self.current_index = (self.current_index + 1) % len(Stepper.SEQUENCE)
        else:
            self.current_index = (self.current_index - 1) % len(Stepper.SEQUENCE)
        self.set_pins(Stepper.SEQUENCE[self.current_index])

    def disable(self):
        for pin in self.pins:
            pin.value(0)
