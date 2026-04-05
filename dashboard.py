import time
import threading
import json
from collections import deque
from urllib.request import Request, urlopen
from urllib.error import URLError
from flask import Flask, render_template, jsonify, request as flask_request

from sensors import init_sensors

# ── Configuration ─────────────────────────────────────────
HEALTHIFY_URL   = "https://healthify-one-beige.vercel.app"   # Change to your Vercel URL for prod
ECG_WINDOW      = 1200                       # 6 seconds of data at 200 Hz
SEND_INTERVAL   = 1.0                        # seconds between POSTs to Healthify
TEMP_INTERVAL   = 5.0                        # temperature reads (slow sensor)

# ── Shared state (thread-safe) ────────────────────────────
ecg_graph_data  = deque(maxlen=ECG_WINDOW)
# Batch buffer: collects voltage samples between sends
ecg_send_buffer = deque(maxlen=ECG_WINDOW)
latest_metrics  = {
    "ecg_hr": None, "ppg_hr": None, "spo2": None,
    "hrv": None, "temperature": None,
    "quality": "---", "leads": True,
}
cloud_status    = {"ok": False, "last_error": "Not started"}
selected_patient = {"id": None, "name": None}
lock = threading.Lock()

# ── Sensor initialization ─────────────────────────────────
adc, ecg, pulse, temp_sensor = init_sensors()

# ── Sensor loop (background thread) ──────────────────────
def sensor_loop():
    SAMPLE_INTERVAL = 0.005     # 200 Hz
    CALC_INTERVAL   = 2.0
    last_calc       = time.time()
    last_temp       = 0.0

    while True:
        # ── ECG ──────────────────────────────────────────
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
                        ecg_send_buffer.append(round(v, 5))
            except OSError:
                with lock:
                    latest_metrics["leads"] = False
                    latest_metrics["quality"] = "I2C error"

        # ── MAX30102 ─────────────────────────────────────
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

        # ── Temperature (slow) ───────────────────────────
        now = time.time()
        if temp_sensor and now - last_temp >= TEMP_INTERVAL:
            try:
                with lock:
                    latest_metrics["temperature"] = temp_sensor.get_body_temperature()
            except Exception:
                pass
            last_temp = now

        # ── Periodic metric calculation ──────────────────
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

# ── Cloud sender (background thread) ─────────────────────
def cloud_sender():
    """Every SEND_INTERVAL seconds, POST batched data to Healthify."""
    while True:
        time.sleep(SEND_INTERVAL)

        with lock:
            pid = selected_patient["id"]
        if not pid:
            continue

        # Drain the send buffer
        with lock:
            samples = list(ecg_send_buffer)
            ecg_send_buffer.clear()
            m = dict(latest_metrics)

        payload = json.dumps({
            "patient_id":       pid,
            "ecg_samples":      samples,
            "ecg_sampling_rate": 200,
            "heart_rate":       m.get("ecg_hr"),
            "spo2":             m.get("spo2"),
            "temperature":      m.get("temperature"),
            "leads_attached":   m.get("leads", False),
            "signal_quality":   m.get("quality", "---"),
        }).encode("utf-8")

        try:
            req = Request(
                f"{HEALTHIFY_URL}/api/live/ingest",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urlopen(req, timeout=5)
            resp.read()
            with lock:
                cloud_status["ok"] = True
                cloud_status["last_error"] = ""
        except Exception as e:
            with lock:
                cloud_status["ok"] = False
                cloud_status["last_error"] = str(e)

# ── Flask app ─────────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/ecg")
def api_ecg():
    with lock:
        data = list(ecg_graph_data)
    return jsonify(data)

@app.route("/api/metrics")
def api_metrics():
    with lock:
        m = dict(latest_metrics)
        m["cloud"] = dict(cloud_status)
        m["patient"] = dict(selected_patient)
    return jsonify(m)

@app.route("/api/patients")
def api_patients():
    """Proxy patient list from Healthify so the dashboard can show a selector."""
    try:
        req = Request(f"{HEALTHIFY_URL}/api/patients", method="GET")
        resp = urlopen(req, timeout=5)
        data = json.loads(resp.read().decode("utf-8"))
        return jsonify(data)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 502

@app.route("/api/select-patient", methods=["POST"])
def api_select_patient():
    body = flask_request.get_json(force=True)
    pid  = body.get("id")
    name = body.get("name", "")
    with lock:
        selected_patient["id"]   = pid
        selected_patient["name"] = name
        # Clear old buffers when switching patient
        ecg_send_buffer.clear()
    return jsonify({"success": True, "patient_id": pid})

# ── Start ─────────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=sensor_loop,  daemon=True).start()
    threading.Thread(target=cloud_sender, daemon=True).start()
    print("\n  Dashboard → http://<your-pi-ip>:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
