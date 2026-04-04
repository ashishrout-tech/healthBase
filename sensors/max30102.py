import smbus2
import time
from collections import deque

class MAX30102:
    ADDRESS = 0x57

    REG_INTR_ENABLE_1 = 0x02
    REG_INTR_ENABLE_2 = 0x03
    REG_FIFO_WR_PTR   = 0x04
    REG_OVF_COUNTER   = 0x05
    REG_FIFO_RD_PTR   = 0x06
    REG_FIFO_DATA     = 0x07
    REG_FIFO_CONFIG   = 0x08
    REG_MODE_CONFIG   = 0x09
    REG_SPO2_CONFIG   = 0x0A
    REG_LED1_PA       = 0x0C
    REG_LED2_PA       = 0x0D
    REG_PILOT_PA      = 0x10
    REG_TEMP_INTR     = 0x1F
    REG_TEMP_FRAC     = 0x20
    REG_TEMP_CONFIG   = 0x21
    REG_PART_ID       = 0xFF

    # Signal processing config
    BUFFER_SIZE    = 100   # samples collected before calculating HR/SpO2
    MIN_IR_VALUE   = 50000 # below this = no finger on sensor

    def __init__(self, bus_number=1):
        self.bus = smbus2.SMBus(bus_number)
        self._ir_buffer  = deque(maxlen=self.BUFFER_SIZE)
        self._red_buffer = deque(maxlen=self.BUFFER_SIZE)
        self._setup()

    # ── Low-level I/O ────────────────────────────────────

    def _write(self, reg, value):
        self.bus.write_byte_data(self.ADDRESS, reg, value)

    def _read(self, reg):
        return self.bus.read_byte_data(self.ADDRESS, reg)

    def _reset(self):
        self._write(self.REG_MODE_CONFIG, 0x40)
        time.sleep(0.1)

    # ── Sensor setup ─────────────────────────────────────

    def _setup(self):
        self._reset()

        part_id = self._read(self.REG_PART_ID)
        if part_id != 0x15:
            raise RuntimeError(
                f"MAX30102 not found. Got Part ID: 0x{part_id:02X}. "
                "Run i2cdetect -y 1 and check wiring."
            )

        self._write(self.REG_INTR_ENABLE_1, 0xC0)
        self._write(self.REG_INTR_ENABLE_2, 0x00)
        self._write(self.REG_FIFO_WR_PTR,   0x00)
        self._write(self.REG_OVF_COUNTER,   0x00)
        self._write(self.REG_FIFO_RD_PTR,   0x00)
        self._write(self.REG_FIFO_CONFIG,   0x0F)  # no averaging, rollover on
        self._write(self.REG_MODE_CONFIG,   0x03)  # SpO2 mode (Red + IR)
        self._write(self.REG_SPO2_CONFIG,   0x27)  # SR=100Hz, pulse=411us
        self._write(self.REG_LED1_PA,       0x24)  # Red LED ~7mA
        self._write(self.REG_LED2_PA,       0x24)  # IR LED ~7mA
        self._write(self.REG_PILOT_PA,      0x7F)

    # ── Raw FIFO read ────────────────────────────────────

    def _data_available(self):
        """Check if new sample exists in FIFO."""
        wr = self._read(self.REG_FIFO_WR_PTR)
        rd = self._read(self.REG_FIFO_RD_PTR)
        return wr != rd

    def _read_fifo(self):
        """Read one Red + IR sample from FIFO."""
        d = self.bus.read_i2c_block_data(self.ADDRESS, self.REG_FIFO_DATA, 6)
        red = (d[0] << 16 | d[1] << 8 | d[2]) & 0x3FFFF
        ir  = (d[3] << 16 | d[4] << 8 | d[5]) & 0x3FFFF
        return red, ir

    # ── Signal processing ────────────────────────────────

    def _detect_peaks(self, data, min_distance=10, threshold=0):
        """Find local maxima above threshold in the IR signal."""
        peaks = []
        for i in range(1, len(data) - 1):
            if (data[i] > threshold
                    and data[i] > data[i - 1]
                    and data[i] > data[i + 1]):
                if not peaks or (i - peaks[-1]) >= min_distance:
                    peaks.append(i)
        return peaks

    def _calculate_hr(self, ir_data, sample_rate=100):
        """
        Calculate heart rate from IR signal.
        Returns BPM or None if not enough peaks found.
        """
        mean_ir = sum(ir_data) / len(ir_data)

        # Remove DC offset — work on AC component only
        ac_data = [v - mean_ir for v in ir_data]

        # Amplitude threshold — ignore noise below 40% of max AC
        max_ac = max(ac_data)
        if max_ac <= 0:
            return None
        threshold = max_ac * 0.4

        # min_distance = 0.5s → caps at 120 BPM (covers exercise)
        peaks = self._detect_peaks(
            ac_data,
            min_distance=int(sample_rate * 0.5),
            threshold=threshold,
        )

        if len(peaks) < 2:
            return None

        # Average interval between peaks → BPM
        intervals = [peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
        avg_interval = sum(intervals) / len(intervals)
        bpm = (sample_rate / avg_interval) * 60

        # Sanity check — valid HR range
        if 40 <= bpm <= 120:
            return round(bpm, 1)
        return None

    def _calculate_spo2(self, red_data, ir_data):
        """
        Calculate SpO2 using AC/DC ratio of Red and IR signals.
        Standard formula: R = (AC_red/DC_red) / (AC_ir/DC_ir)
        SpO2 ≈ 104 - 17 * R  (empirical calibration curve)
        Returns SpO2 percentage or None if signal is invalid.
        """
        dc_red = sum(red_data) / len(red_data)
        dc_ir  = sum(ir_data)  / len(ir_data)

        if dc_red == 0 or dc_ir == 0:
            return None

        ac_red = max(red_data) - min(red_data)
        ac_ir  = max(ir_data)  - min(ir_data)

        if ac_ir == 0:
            return None

        R = (ac_red / dc_red) / (ac_ir / dc_ir)

        # Empirical formula (standard approximation)
        spo2 = 104.0 - 17.0 * R

        # Sanity check — valid SpO2 range
        if 80 <= spo2 <= 100:
            return round(spo2, 1)
        return None

    # ── Public API ───────────────────────────────────────

    def collect_samples(self, count=None):
        """
        Collect raw samples into internal buffer.
        Call this in a loop. Returns True when buffer is full
        and HR/SpO2 can be calculated.
        """
        target = count or self.BUFFER_SIZE

        # Only read when sensor has new data — avoids duplicates
        if not self._data_available():
            return len(self._ir_buffer) >= target

        red, ir = self._read_fifo()

        self._ir_buffer.append(ir)
        self._red_buffer.append(red)

        return len(self._ir_buffer) >= target

    def finger_detected(self):
        """Returns True if IR value indicates a finger is on the sensor."""
        if not self._ir_buffer:
            return False
        if self._ir_buffer[-1] > self.MIN_IR_VALUE:
            return True
        # Finger removed — clear stale data
        self._ir_buffer.clear()
        self._red_buffer.clear()
        return False

    def get_heart_rate(self):
        """Returns calculated BPM or None if not enough data / no finger."""
        if not self.finger_detected() or len(self._ir_buffer) < self.BUFFER_SIZE:
            return None
        return self._calculate_hr(self._ir_buffer)

    def get_spo2(self):
        """Returns SpO2 percentage or None if not enough data / no finger."""
        if not self.finger_detected() or len(self._ir_buffer) < self.BUFFER_SIZE:
            return None
        return self._calculate_spo2(self._red_buffer, self._ir_buffer)

    def get_temperature(self):
        """Returns sensor die temperature in Celsius."""
        self._write(self.REG_TEMP_CONFIG, 0x01)
        time.sleep(0.02)
        temp_int  = self._read(self.REG_TEMP_INTR)
        temp_frac = self._read(self.REG_TEMP_FRAC)
        return round(temp_int + (temp_frac * 0.0625), 2)

    def get_signal_quality(self):
        """Returns a string describing current signal quality."""
        if not self._ir_buffer:
            return "No data"
        ir = self._ir_buffer[-1]
        if ir < self.MIN_IR_VALUE:
            return "No finger"
        elif ir < 100000:
            return "Weak — press finger firmly"
        elif ir < 150000:
            return "Good"
        return "Excellent"

    def close(self):
        self.bus.close()