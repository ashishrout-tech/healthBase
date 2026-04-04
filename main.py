import time
from sensors.ads1115  import ADS1115
from sensors.ad8232   import AD8232
from sensors.max30102 import MAX30102

# ── Initialize ────────────────────────────────────────────
print("Initializing sensors...\n")

try:
    adc    = ADS1115(bus_number=1)
    ecg    = AD8232(adc, lo_plus_pin=17, lo_minus_pin=27)
    print("  ADS1115  — OK")
    print("  AD8232   — OK")
except Exception as e:
    print(f"  ECG setup FAILED: {e}")
    exit(1)

try:
    pulse  = MAX30102(bus_number=1)
    print("  MAX30102 — OK")
except RuntimeError as e:
    print(f"  MAX30102 — FAILED: {e}")
    pulse = None

print("\nSensor system ready.\n")

# ── ECG loop ──────────────────────────────────────────────
print("Attach electrodes to your body, then press Enter...")
input()

print(f"{'Status':<22} {'ECG voltage (V)':<20} {'HR':<10} {'SpO2'}")
print("-" * 65)

sample = 0
try:
    while True:
        # ECG
        if not ecg.leads_attached():
            print("  LEAD OFF — check electrode connections")
            time.sleep(0.5)
            continue

        voltage = ecg.read_voltage()
        sample += 1

        # MAX30102
        hr_str = spo2_str = "---"
        if pulse:
            ready = pulse.collect_samples()
            if ready and pulse.finger_detected():
                hr   = pulse.get_heart_rate()
                spo2 = pulse.get_spo2()
                hr_str   = f"{hr} BPM" if hr   else "..."
                spo2_str = f"{spo2}%"  if spo2 else "..."

        print(f"  Leads OK  [{sample:>5}]     {voltage:>+8.4f} V           {hr_str:<10} {spo2_str}")

        time.sleep(0.005)  # ~200 samples/sec for ECG

except KeyboardInterrupt:
    print("\nStopped.")
    ecg.cleanup()
    if pulse:
        pulse.close()
    adc.close()