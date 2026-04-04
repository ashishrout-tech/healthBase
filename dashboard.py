import time
import threading
from collections import deque
from flask import Flask, render_template, jsonify

from sensors.ads1115  import ADS1115
from sensors.ad8232   import AD8232
from sensors.max30102 import MAX30102

# ── Shared state (thread-safe via deque) ──────────────────
ECG_WINDOW      = 1200          # 6 seconds of data at 200 Hz
ecg_graph_data  = deque(maxlen=ECG_WINDOW)
latest_metrics  = {
    "ecg_hr": None, "ppg_hr": None, "spo2": None,
    "hrv": None, "quality": "---", "leads": True,
}
lock = threading.Lock()

# ── Sensor initialization ─────────────────────────────────
adc = ecg = pulse = None

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

if not ecg and not pulse:
    print("No sensors available — exiting.")
    exit(1)

# ── Sensor loop (runs in background thread) ───────────────
def sensor_loop():
    SAMPLE_INTERVAL = 0.005     # 200 Hz
    CALC_INTERVAL   = 2.0       # recalculate metrics every 2 s
    last_calc       = time.time()

    while True:
        # ── ECG ───────────────────────────────────────────
        if ecg:
            if not ecg.leads_attached():
                with lock:
                    latest_metrics["leads"] = False
                time.sleep(0.5)
                continue

            v = ecg.record_sample()
            t = time.time()
            with lock:
                latest_metrics["leads"] = True
                ecg_graph_data.append({"t": round(t * 1000), "v": round(v, 5)})

        # ── MAX30102 ──────────────────────────────────────
        if pulse:
            ready = pulse.collect_samples()
            if ready and pulse.finger_detected():
                with lock:
                    hr   = pulse.get_heart_rate()
                    spo2 = pulse.get_spo2()
                    latest_metrics["ppg_hr"] = hr
                    latest_metrics["spo2"]   = spo2

        # ── Periodic metric calculation ───────────────────
        now = time.time()
        if now - last_calc >= CALC_INTERVAL and ecg:
            with lock:
                latest_metrics["ecg_hr"]  = ecg.get_heart_rate()
                latest_metrics["hrv"]     = ecg.get_hrv()
                latest_metrics["quality"] = ecg.get_signal_quality()
            last_calc = now

        time.sleep(SAMPLE_INTERVAL)

# ── Flask app ─────────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/ecg")
def api_ecg():
    """Return latest ECG samples for the graph."""
    with lock:
        data = list(ecg_graph_data)
    return jsonify(data)

@app.route("/api/metrics")
def api_metrics():
    """Return latest computed metrics."""
    with lock:
        m = dict(latest_metrics)
    return jsonify(m)

# ── Start ─────────────────────────────────────────────────
if __name__ == "__main__":
    t = threading.Thread(target=sensor_loop, daemon=True)
    t.start()
    print("\n  Dashboard → http://<your-pi-ip>:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
