import smbus2
import time

class ADS1115:
    ADDRESS = 0x48

    # Registers
    REG_CONVERSION = 0x00
    REG_CONFIG     = 0x01

    # Config bits
    OS_SINGLE      = 0x8000  # Start single conversion
    MUX_AIN0_GND   = 0x4000  # A0 vs GND (single-ended)
    PGA_4096       = 0x0200  # ±4.096V range
    MODE_SINGLE    = 0x0100  # Single-shot mode
    DR_860SPS      = 0x00E0  # 860 samples/sec (fastest)
    COMP_DISABLE   = 0x0003  # Disable comparator

    def __init__(self, bus_number=1):
        self.bus = smbus2.SMBus(bus_number)

    def _read_voltage(self):
        config = (
            self.OS_SINGLE    |
            self.MUX_AIN0_GND |
            self.PGA_4096     |
            self.MODE_SINGLE  |
            self.DR_860SPS    |
            self.COMP_DISABLE
        )
        # Write config
        config_bytes = [(config >> 8) & 0xFF, config & 0xFF]
        self.bus.write_i2c_block_data(self.ADDRESS, self.REG_CONFIG, config_bytes)

        # Wait for conversion
        time.sleep(0.002)

        # Read result
        data = self.bus.read_i2c_block_data(self.ADDRESS, self.REG_CONVERSION, 2)
        raw = (data[0] << 8) | data[1]

        # Convert to signed 16-bit
        if raw > 32767:
            raw -= 65536

        # Convert to voltage (PGA ±4.096V, 16-bit)
        voltage = raw * 4.096 / 32767.0
        return voltage

    def read_ecg_raw(self):
        """Returns raw voltage from A0 (AD8232 output)."""
        return self._read_voltage()

    def close(self):
        self.bus.close()