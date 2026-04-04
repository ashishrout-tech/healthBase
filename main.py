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

SAMPLE_INTERVAL  = 0.005   # 200 Hz sampling (good for ECG)
DISPLAY_INTERVAL = 2.0     # print a summary line every 2 seconds

print(f"{'Status':<14} {'Samples':>7}   {'ECG (V)':>10} {'ECG HR':>10} {'HRV(ms)':>8} {'Quality':<16}  {'PPG HR':<10} {'SpO2'}")
print("-" * 105)

sample       = 0
last_display = time.time()

try:
    while True:
        status = "  Sensors OK"

        # ── ECG sampling ──────────────────────────────────
        if ecg:
            if not ecg.leads_attached():
                print("  LEAD OFF — check electrode connections")
                time.sleep(0.5)
                last_display = time.time()
                continue
            ecg.record_sample()

        sample += 1

        # ── MAX30102 sampling ─────────────────────────────
        ppg_hr_str = spo2_str = "---"
        if pulse:
            ready = pulse.collect_samples()
            if ready and pulse.finger_detected():
                hr   = pulse.get_heart_rate()
                spo2 = pulse.get_spo2()
                ppg_hr_str = f"{hr} BPM" if hr   else "..."
                spo2_str   = f"{spo2}%"  if spo2 else "..."

        # ── Display (throttled) ───────────────────────────
        now = time.time()
        if now - last_display >= DISPLAY_INTERVAL:

            # ECG derived data
            if not ecg:
                status = "  No ECG   "
                volt_str = ecg_hr_str = hrv_str = quality_str = "N/A"
            elif ecg.buffer_seconds() >= 1.0:
                last_v   = ecg._buffer[-1][1]
                volt_str = f"{last_v:>+8.4f} V"

                ecg_hr = ecg.get_heart_rate()
                ecg_hr_str = f"{ecg_hr} BPM" if ecg_hr else "..."

                hrv = ecg.get_hrv()
                hrv_str = f"{hrv}" if hrv else "..."

                quality_str = ecg.get_signal_quality()
            else:
                volt_str    = "buffering"
                ecg_hr_str  = "..."
                hrv_str     = "..."
                quality_str = f"{ecg.buffer_seconds():.1f}s collected"

            # MAX30102 data
            if not pulse:
                ppg_hr_str = spo2_str = "N/A"

            print(
                f"{status}  [{sample:>7}]"
                f"   {volt_str:>10} {ecg_hr_str:>10} {hrv_str:>8} {quality_str:<16}"
                f"  {ppg_hr_str:<10} {spo2_str}"
            )

            last_display = now

        time.sleep(SAMPLE_INTERVAL)

except KeyboardInterrupt:
    print("\nStopped.")
    if ecg:
        ecg.cleanup()
    if pulse:
        pulse.close()
    if adc:
        adc.close()