import RPi.GPIO as GPIO
import time
from collections import deque

class AD8232:
    """
    AD8232 ECG front-end.
    Reads analog signal via ADS1115.
    Uses LO+ / LO- pins to detect if electrodes are attached.
    Includes R-peak detection for heart-rate calculation.
    """

    SAMPLE_RATE    = 200     # expected sampling rate in Hz
    BUFFER_SIZE    = 600     # 3 seconds of data at 200 Hz
    R_PEAK_THRESH  = 0.6     # fraction of max amplitude to qualify as R-peak
    MIN_RR_SEC     = 0.3     # minimum R-R interval (200 BPM ceiling)
    MAX_RR_SEC     = 1.5     # maximum R-R interval (40 BPM floor)

    def __init__(self, adc, lo_plus_pin=17, lo_minus_pin=27):
        """
        adc          : ADS1115 instance
        lo_plus_pin  : BCM GPIO pin connected to AD8232 LO+
        lo_minus_pin : BCM GPIO pin connected to AD8232 LO-
        """
        self.adc = adc
        self.lo_plus  = lo_plus_pin
        self.lo_minus = lo_minus_pin

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.lo_plus,  GPIO.IN)
        GPIO.setup(self.lo_minus, GPIO.IN)

        # Signal buffer: deque of (timestamp, voltage)
        self._buffer = deque(maxlen=self.BUFFER_SIZE)

    def leads_attached(self):
        """Returns True if all electrodes are properly connected."""
        lo_plus_off  = GPIO.input(self.lo_plus)  == GPIO.HIGH
        lo_minus_off = GPIO.input(self.lo_minus) == GPIO.HIGH
        # LO pins go HIGH when a lead falls off
        return not (lo_plus_off or lo_minus_off)

    def read_voltage(self):
        """Raw ECG voltage from ADS1115 A0."""
        return self.adc.read_ecg_raw()

    # ── Buffered sampling ─────────────────────────────────

    def record_sample(self):
        """Read one sample and add it to the internal buffer.
        Returns the voltage value."""
        v = self.read_voltage()
        self._buffer.append((time.monotonic(), v))
        return v

    def get_latest_voltage(self):
        """Return the most recent voltage reading, or None."""
        if not self._buffer:
            return None
        return self._buffer[-1][1]

    def buffer_seconds(self):
        """How many seconds of data are in the buffer."""
        if len(self._buffer) < 2:
            return 0.0
        return self._buffer[-1][0] - self._buffer[0][0]

    # ── R-peak detection ──────────────────────────────────

    def _detect_r_peaks(self):
        """Find R-peak timestamps using a simple threshold method.
        Works on the AC component of the buffered signal."""
        if len(self._buffer) < self.SAMPLE_RATE:
            return []

        voltages = [v for _, v in self._buffer]
        times    = [t for t, _ in self._buffer]

        # Remove DC offset
        mean_v = sum(voltages) / len(voltages)
        ac = [v - mean_v for v in voltages]

        # Dynamic threshold based on signal amplitude
        max_ac = max(ac)
        if max_ac <= 0:
            return []
        threshold = max_ac * self.R_PEAK_THRESH

        min_samples = int(self.MIN_RR_SEC * self.SAMPLE_RATE)

        peaks = []
        for i in range(1, len(ac) - 1):
            if ac[i] > threshold and ac[i] > ac[i - 1] and ac[i] > ac[i + 1]:
                if not peaks or (i - peaks[-1]) >= min_samples:
                    peaks.append(i)

        return [(times[i], voltages[i]) for i in peaks]

    # ── Derived metrics ───────────────────────────────────

    def get_heart_rate(self):
        """Calculate BPM from R-R intervals.  Returns float or None."""
        peaks = self._detect_r_peaks()
        if len(peaks) < 2:
            return None

        rr_intervals = [
            peaks[i + 1][0] - peaks[i][0]
            for i in range(len(peaks) - 1)
        ]

        # Filter physiologically plausible intervals
        valid = [rr for rr in rr_intervals
                 if self.MIN_RR_SEC <= rr <= self.MAX_RR_SEC]
        if not valid:
            return None

        avg_rr = sum(valid) / len(valid)
        bpm = 60.0 / avg_rr
        return round(bpm, 1)

    def get_rr_intervals(self):
        """Return list of R-R intervals in milliseconds, or empty list."""
        peaks = self._detect_r_peaks()
        if len(peaks) < 2:
            return []
        return [
            round((peaks[i + 1][0] - peaks[i][0]) * 1000, 1)
            for i in range(len(peaks) - 1)
        ]

    def get_hrv(self):
        """Heart-rate variability (SDNN) in ms.  Returns float or None."""
        rr = self.get_rr_intervals()
        if len(rr) < 2:
            return None
        mean_rr = sum(rr) / len(rr)
        variance = sum((r - mean_rr) ** 2 for r in rr) / len(rr)
        return round(variance ** 0.5, 1)

    def get_signal_quality(self):
        """Rough signal-quality label based on peak consistency."""
        rr = self.get_rr_intervals()
        if len(rr) < 2:
            return "Insufficient data"
        hrv = self.get_hrv()
        if hrv is not None and hrv > 200:
            return "Noisy — keep still"
        if len(rr) >= 3:
            return "Good"
        return "Weak — keep electrodes firm"

    def get_all_metrics(self):
        """Return all ECG metrics in one call (single peak detection pass)."""
        result = {
            "heart_rate": None, "hrv": None,
            "rr_intervals": [], "quality": "Insufficient data",
        }
        peaks = self._detect_r_peaks()
        if len(peaks) < 2:
            return result

        rr_sec = [peaks[i+1][0] - peaks[i][0] for i in range(len(peaks)-1)]
        rr_ms  = [round(r * 1000, 1) for r in rr_sec]
        result["rr_intervals"] = rr_ms

        valid = [r for r in rr_sec if self.MIN_RR_SEC <= r <= self.MAX_RR_SEC]
        if valid:
            result["heart_rate"] = round(60.0 / (sum(valid) / len(valid)), 1)

        if len(rr_ms) >= 2:
            mean = sum(rr_ms) / len(rr_ms)
            result["hrv"] = round((sum((r - mean)**2 for r in rr_ms) / len(rr_ms)) ** 0.5, 1)

        if result["hrv"] is not None and result["hrv"] > 200:
            result["quality"] = "Noisy — keep still"
        elif len(rr_ms) >= 3:
            result["quality"] = "Good"
        else:
            result["quality"] = "Weak — keep electrodes firm"

        return result

    def cleanup(self):
        GPIO.cleanup()