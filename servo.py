import machine
import sys

class Servo:
    def __init__(self, pin, freq=50, min_us=500, max_us=2500, degrees=180):
        """
        MicroPython Servo driver.

        :param pin: GPIO pin number for PWM output.
        :param freq: PWM frequency (default: 50 Hz for servos).
        :param min_us: Minimum pulse width in microseconds (default: 500 µs).
        :param max_us: Maximum pulse width in microseconds (default: 2500 µs).
        :param degrees: Maximum angle range (default: 180°).
        """
        self.pin = pin
        self.freq = freq
        self.min_us = min_us
        self.max_us = max_us
        self.degrees = degrees
        
        # Detect platform
        self.platform = sys.platform
        
        # Initialize PWM
        if self.platform in ('esp8266', 'esp32'):
            self.pwm = machine.PWM(machine.Pin(pin), freq=freq)
        elif self.platform == 'rp2':  # Raspberry Pi Pico
            self.pwm = machine.PWM(machine.Pin(pin))
            self.pwm.freq(freq)
        else:
            raise RuntimeError("Unsupported platform")

    def _angle_to_duty(self, angle):
        """Convert angle (0 to max degrees) into duty cycle."""
        pulse_width = self.min_us + (angle / self.degrees) * (self.max_us - self.min_us)
        
        if self.platform in ('esp8266', 'esp32'):
            return int(pulse_width * 1023 / 20000)  # ESP32/ESP8266 uses 10-bit (0-1023)
        elif self.platform == 'rp2':  # Raspberry Pi Pico
            return int(pulse_width * 65535 / 20000)  # Pico uses 16-bit (0-65535)
        else:
            return 0  # Unsupported platform

    def set(self, angle):
        """Move the servo to the specified angle (0 to max degrees)."""
        angle = max(0, min(self.degrees, angle))  # Clamp angle to valid range
        duty = self._angle_to_duty(angle)

        if self.platform in ('esp8266', 'esp32'):
            self.pwm.duty(duty)
        elif self.platform == 'rp2':  # Raspberry Pi Pico
            self.pwm.duty_u16(duty)

    def stop(self):
        """Stop the servo (set PWM duty cycle to 0)."""
        if self.platform in ('esp8266', 'esp32'):
            self.pwm.duty(0)
        elif self.platform == 'rp2':  # Raspberry Pi Pico
            self.pwm.duty_u16(0)

    def off(self):
        """Turn off the servo completely (disable PWM)."""
        self.pwm.deinit()

