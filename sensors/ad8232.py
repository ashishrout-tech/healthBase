import RPi.GPIO as GPIO

class AD8232:
    """
    AD8232 ECG front-end.
    Reads analog signal via ADS1115.
    Uses LO+ / LO- pins to detect if electrodes are attached.
    """

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

    def leads_attached(self):
        """Returns True if all electrodes are properly connected."""
        lo_plus_off  = GPIO.input(self.lo_plus)  == GPIO.HIGH
        lo_minus_off = GPIO.input(self.lo_minus) == GPIO.HIGH
        # LO pins go HIGH when a lead falls off
        return not (lo_plus_off or lo_minus_off)

    def read_voltage(self):
        """Raw ECG voltage from ADS1115 A0."""
        return self.adc.read_ecg_raw()

    def cleanup(self):
        GPIO.cleanup()