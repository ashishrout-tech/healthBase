import time
import threading
from collections import deque
from flask import Flask, render_template, jsonify

from sensors import init_sensors

# ── Shared state (thread-safe via deque) ──────────────────
ECG_WINDOW      = 1200          # 6 seconds of data at 200 Hz
ecg_graph_data  = deque(maxlen=ECG_WINDOW)
latest_metrics  = {
    "ecg_hr": None, "ppg_hr": None, "spo2": None,
    "hrv": None, "quality": "---", "leads": True,
}
lock = threading.Lock()

# ── Sensor initialization ─────────────────────────────────
adc, ecg, pulse = init_sensors()

# ── Sensor loop (runs in background thread) ───────────────
def sensor_loop():
    SAMPLE_INTERVAL = 0.005     # 200 Hz
    CALC_INTERVAL   = 2.0       # recalculate metrics every 2 s
    last_calc       = time.time()

    while True:
        # ── ECG ───────────────────────────────────────────
        if ecg:
            try:
                if not ecg.leads_attached():
                    with lock:
                        latest_metrics["leads"]   = False
                        latest_metrics["ecg_hr"]  = None
                        latest_metrics["hrv"]     = None
                        latest_metrics["quality"] = "Leads off"
                else:
                    v = ecg.record_sample()
                    t = time.time()
                    with lock:
                        latest_metrics["leads"] = True
                        ecg_graph_data.append({"t": round(t * 1000), "v": round(v, 5)})
            except OSError:
                with lock:
                    latest_metrics["leads"] = False
                    latest_metrics["quality"] = "I2C error"

        # ── MAX30102 ──────────────────────────────────────
        if pulse:
            try:
                ready = pulse.collect_samples()
                if ready and pulse.finger_detected():
                    with lock:
                        latest_metrics["ppg_hr"] = pulse.get_heart_rate()
                        latest_metrics["spo2"]   = pulse.get_spo2()
                else:
                    with lock:
                        latest_metrics["ppg_hr"] = None
                        latest_metrics["spo2"]   = None
            except OSError:
                pass

        # ── Periodic metric calculation ───────────────────
        now = time.time()
        with lock:
            leads_on = latest_metrics["leads"]
        if now - last_calc >= CALC_INTERVAL and ecg and leads_on:
            m = ecg.get_all_metrics()
            with lock:
                latest_metrics["ecg_hr"]  = m["heart_rate"]
                latest_metrics["hrv"]     = m["hrv"]
                latest_metrics["quality"] = m["quality"]
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
