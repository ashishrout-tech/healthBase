import time
from sensors import init_sensors

# ── Initialize ────────────────────────────────────────────
adc, ecg, pulse, temp_sensor = init_sensors()

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
        status    = "  Sensors OK"
        leads_off = False

        # ── ECG sampling ──────────────────────────────────
        if ecg:
            try:
                if not ecg.leads_attached():
                    leads_off = True
                else:
                    ecg.record_sample()
            except OSError:
                leads_off = True

        sample += 1

        # ── MAX30102 sampling ─────────────────────────────
        ppg_hr_str = spo2_str = "---"
        if pulse:
            try:
                ready = pulse.collect_samples()
                if ready and pulse.finger_detected():
                    hr   = pulse.get_heart_rate()
                    spo2 = pulse.get_spo2()
                    ppg_hr_str = f"{hr} BPM" if hr   else "..."
                    spo2_str   = f"{spo2}%"  if spo2 else "..."
            except OSError:
                pass

        # ── Display (throttled) ───────────────────────────
        now = time.time()
        if now - last_display >= DISPLAY_INTERVAL:

            # ECG derived data
            if not ecg:
                status = "  No ECG   "
                volt_str = ecg_hr_str = hrv_str = quality_str = "N/A"
            elif leads_off:
                status      = "  LEAD OFF "
                volt_str    = "---"
                ecg_hr_str  = "---"
                hrv_str     = "---"
                quality_str = "Check electrodes"
            elif ecg.buffer_seconds() >= 1.0:
                last_v = ecg.get_latest_voltage()
                volt_str = f"{last_v:>+8.4f} V" if last_v is not None else "---"

                m = ecg.get_all_metrics()
                ecg_hr_str  = f"{m['heart_rate']} BPM" if m["heart_rate"] else "..."
                hrv_str     = f"{m['hrv']}" if m["hrv"] else "..."
                quality_str = m["quality"]
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