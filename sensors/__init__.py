from sensors.ads1115  import ADS1115
from sensors.ad8232   import AD8232
from sensors.max30102 import MAX30102


def init_sensors(bus_number=1, lo_plus_pin=17, lo_minus_pin=27):
    """Initialize all sensors with graceful fallback.
    Returns (adc, ecg, pulse) - any may be None if init failed."""
    print("Initializing sensors...\n")

    adc = ecg = pulse = None

    try:
        adc = ADS1115(bus_number=bus_number)
        print("  ADS1115  - OK")
    except Exception as e:
        print(f"  ADS1115  - FAILED: {e}")

    if adc:
        try:
            ecg = AD8232(adc, lo_plus_pin=lo_plus_pin, lo_minus_pin=lo_minus_pin)
            print("  AD8232   - OK")
        except Exception as e:
            print(f"  AD8232   - FAILED: {e}")
    else:
        print("  AD8232   - SKIPPED (requires ADS1115)")

    try:
        pulse = MAX30102(bus_number=bus_number)
        print("  MAX30102 - OK")
    except Exception as e:
        print(f"  MAX30102 - FAILED: {e}")

    available = []
    if ecg:
        available.append("ECG")
    if pulse:
        available.append("HR/SpO2")

    if not available:
        print("\nNo sensors available - nothing to collect. Exiting.")
        exit(1)

    print(f"\nSensor system ready.  Active: {', '.join(available)}\n")
    return adc, ecg, pulse
