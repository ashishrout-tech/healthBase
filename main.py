import time
from sensors.ads1115  import ADS1115
from sensors.ad8232   import AD8232
from sensors.max30102 import MAX30102

# ── Initialize ────────────────────────────────────────────
print("Initializing sensors...\n")

adc   = None
ecg   = None
pulse = None

try:
    adc = ADS1115(bus_number=1)
    print("  ADS1115  — OK")
except Exception as e:
    print(f"  ADS1115  — FAILED: {e}")

if adc:
    try:
        ecg = AD8232(adc, lo_plus_pin=17, lo_minus_pin=27)
        print("  AD8232   — OK")
    except Exception as e:
        print(f"  AD8232   — FAILED: {e}")
else:
    print("  AD8232   — SKIPPED (requires ADS1115)")

try:
    pulse = MAX30102(bus_number=1)
    print("  MAX30102 — OK")
except Exception as e:
    print(f"  MAX30102 — FAILED: {e}")

# ── Availability summary ─────────────────────────────────
available = []
if ecg:
    available.append("ECG")
if pulse:
    available.append("HR/SpO2")

if not available:
    print("\nNo sensors available — nothing to collect. Exiting.")
    exit(1)

print(f"\nSensor system ready.  Active: {', '.join(available)}\n")

# ── Data loop ─────────────────────────────────────────────
if ecg:
    print("Attach electrodes to your body, then press Enter...")
    input()

print(f"{'Status':<22} {'ECG voltage (V)':<20} {'HR':<10} {'SpO2'}")
print("-" * 65)

sample = 0
try:
    while True:
        ecg_str = "N/A"
        status  = "  Sensors OK"

        # ── ECG ───────────────────────────────────────────
        if ecg:
            if not ecg.leads_attached():
                print("  LEAD OFF — check electrode connections")
                time.sleep(0.5)
                continue
            voltage = ecg.read_voltage()
            ecg_str = f"{voltage:>+8.4f} V"

        sample += 1

        # ── MAX30102 ──────────────────────────────────────
        hr_str = spo2_str = "---"
        if pulse:
            ready = pulse.collect_samples()
            if ready and pulse.finger_detected():
                hr   = pulse.get_heart_rate()
                spo2 = pulse.get_spo2()
                hr_str   = f"{hr} BPM" if hr   else "..."
                spo2_str = f"{spo2}%"  if spo2 else "..."

        if not ecg:
            status = "  No ECG   "
        if not pulse:
            hr_str = spo2_str = "N/A"

        print(f"{status}  [{sample:>5}]     {ecg_str:<20} {hr_str:<10} {spo2_str}")

        time.sleep(0.005)

except KeyboardInterrupt:
    print("\nStopped.")
    if ecg:
        ecg.cleanup()
    if pulse:
        pulse.close()
    if adc:
        adc.close()