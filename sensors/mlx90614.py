import random
import time


class MLX90614:
    """
    Dummy MLX90614 infrared temperature sensor.
    Returns realistic random body temperatures for development.
    Replace the read methods with real I2C calls when hardware is available.
    """

    # Normal human body temperature range (°C)
    _BASE_TEMP = 36.6
    _VARIATION = 0.3       # ±0.3 °C random drift

    def __init__(self, bus_number=1, address=0x5A):
        self.address = address
        self._last_temp = self._BASE_TEMP
        print(f"  MLX90614 (dummy) at 0x{address:02X} — OK")

    def get_body_temperature(self):
        """Return a realistic body temperature in Celsius."""
        # Small random walk around the base so the reading looks natural
        drift = random.uniform(-0.05, 0.05)
        self._last_temp += drift
        # Clamp to realistic range
        self._last_temp = max(
            self._BASE_TEMP - self._VARIATION,
            min(self._BASE_TEMP + self._VARIATION, self._last_temp),
        )
        return round(self._last_temp, 1)

    def get_ambient_temperature(self):
        """Return a plausible ambient temperature in Celsius."""
        return round(random.uniform(24.0, 26.0), 1)

    def close(self):
        pass
