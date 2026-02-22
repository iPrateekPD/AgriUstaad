"""
AgriCopilot - Main Flask Application
Agriculture Decision Support System with AI-powered crop disease detection.
"""

import os
import json
import logging
import traceback
import urllib.request
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template,
    send_file, abort, make_response
)
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# ── Load Environment ──────────────────────────────────────────────────────────
load_dotenv()

# ── Services ──────────────────────────────────────────────────────────────────
from services.ai_service import analyze_crop_image, get_demo_diagnosis, initialize_gemini, chat_with_agronomist
from services.weather_service import fetch_weather_forecast
from services.pdf_service import generate_farm_health_passport

# ── Auth Blueprint ─────────────────────────────────────────────────────────────
from auth import auth_bp

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agricopilot")

# ── Flask App Factory ─────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///agricopilot.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

# ── Database ──────────────────────────────────────────────────────────────────
from models import db, ScanRecord
db.init_app(app)

# ── Register Blueprints ────────────────────────────────────────────────────────
app.register_blueprint(auth_bp)

# Initialize Gemini
_gemini_available = False
try:
    initialize_gemini()
    _gemini_available = True
    logger.info("✅ Gemini AI ready.")
except ValueError as e:
    logger.warning(f"⚠️  Gemini not available: {e}. Using demo mode.")

# ── Helper Decorators ─────────────────────────────────────────────────────────
def handle_errors(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            return jsonify({"error": str(e), "type": "validation_error"}), 400
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify({"error": "Server error.", "type": "server_error"}), 500
    return wrapper


def enrich_weather_from_openmeteo(lat: float, lon: float, weather: dict) -> dict:
    """
    If the weather_service didn't return temp/humidity/rainfall/wind fields,
    fetch them directly from the free Open-Meteo API (no key required) and
    merge them into the weather dict.

    Also normalises spray_status to lowercase so the frontend badge works.
    """
    needs_enrichment = not any([
        weather.get("temp_max"),
        weather.get("temperature"),
        weather.get("temp"),
    ])

    if needs_enrichment:
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&daily=temperature_2m_max,temperature_2m_min,"
                f"precipitation_sum,windspeed_10m_max"
                f"&hourly=relativehumidity_2m"
                f"&timezone=auto&forecast_days=1"
            )
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())

            daily = data.get("daily", {})
            hourly = data.get("hourly", {})

            temp_max  = daily.get("temperature_2m_max", [None])[0]
            temp_min  = daily.get("temperature_2m_min", [None])[0]
            rainfall  = daily.get("precipitation_sum",  [None])[0]
            wind      = daily.get("windspeed_10m_max",  [None])[0]
            hum_list  = hourly.get("relativehumidity_2m", [])
            humidity  = round(sum(hum_list[:12]) / len(hum_list[:12])) if hum_list else None

            weather.update({
                "temp_max":   round(temp_max,  1) if temp_max  is not None else None,
                "temp_min":   round(temp_min,  1) if temp_min  is not None else None,
                "humidity":   humidity,
                "rainfall":   round(rainfall,  1) if rainfall  is not None else None,
                "wind_speed": round(wind,       1) if wind      is not None else None,
            })

            # If spray_status wasn't set by weather_service, derive it from wind + rain
            if not weather.get("spray_status") or weather["spray_status"].lower() == "unknown":
                w = wind or 0
                r = rainfall or 0
                if w < 15 and r < 5:
                    weather["spray_status"] = "green"
                    weather["status_reason"] = f"Good conditions — Wind: {w} km/h, Rain: {r} mm"
                elif w < 25 and r < 15:
                    weather["spray_status"] = "yellow"
                    weather["status_reason"] = f"Caution — Wind: {w} km/h, Rain: {r} mm"
                else:
                    weather["spray_status"] = "red"
                    weather["status_reason"] = f"DO NOT SPRAY — Wind too high: {w} km/h"

            logger.info("✅ Weather enriched from Open-Meteo.")
        except Exception as e:
            logger.warning(f"⚠️  Open-Meteo enrichment failed: {e}")

    # ── Normalise spray_status to lowercase so the frontend badge works ──
    # (weather_service returns "GREEN"/"YELLOW"/"RED", frontend checks "green"/"yellow"/"red")
    if weather.get("spray_status"):
        weather["spray_status"] = weather["spray_status"].lower()

    return weather


def build_execution_plan(diagnosis: dict, weather: dict) -> str:
    """Merge AI diagnosis with weather context into a farmer-friendly execution plan."""
    disease      = diagnosis.get("disease_name", "Unknown")
    severity     = diagnosis.get("severity_score", 0)
    spray_status = weather.get("spray_status", "unknown").lower()
    reason       = weather.get("status_reason", "")
    treatment    = diagnosis.get("treatment_advice", "")

    if disease == "Yield Estimation":
        return (f"YIELD REPORT: {diagnosis.get('yield_estimate', 'N/A')}. "
                f"HARVEST ADVICE: {diagnosis.get('market_advice', 'Check market prices.')}")

    if disease == "Soil Analysis":
        return (f"SOIL REPORT: Type: {diagnosis.get('soil_type', 'N/A')}, "
                f"Moisture: {diagnosis.get('moisture_level', 'N/A')}. "
                f"RECOMMENDATION: {diagnosis.get('treatment_advice', '')}")

    if spray_status == "green":
        timing = "CONDITIONS IDEAL. Spray immediately."
    elif spray_status == "yellow":
        timing = "CAUTION. High wind/rain risk."
    else:
        timing = "DO NOT SPRAY. Rain expected."

    return (f"DIAGNOSIS: {disease} (Severity: {severity}%). "
            f"WEATHER: {reason}. ADVISORY: {timing} TREATMENT: {treatment}")

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", gemini_available=_gemini_available)

@app.route("/history")
def history():
    scan_count = db.session.query(ScanRecord).count()
    return render_template("history.html", scan_count=scan_count)

@app.route("/analyze", methods=["POST"])
@handle_errors
def analyze():
    if "image" not in request.files:
        raise ValueError("No image file provided.")

    image_file  = request.files["image"]
    image_bytes = image_file.read()
    lat         = request.form.get("lat")
    lon         = request.form.get("lon")
    scan_mode   = request.form.get("mode", "field")

    lat_f = float(lat) if lat else None
    lon_f = float(lon) if lon else None

    # ── AI Analysis ───────────────────────────────────────────────────────────
    used_demo = False
    diagnosis = {}

    if _gemini_available:
        try:
            diagnosis = analyze_crop_image(
                image_bytes, image_file.mimetype or "image/jpeg", mode=scan_mode
            )
            # ai_service raises RuntimeError if all models fail or returns error payload
            # but double-check here anyway
            _bad = ("analysis error", "api key", "check your internet", "quota", "unknown")
            _txt = str(diagnosis.get("disease_name", "")).lower()
            if _txt in _bad or not diagnosis.get("disease_name"):
                raise RuntimeError("Gemini returned empty/error diagnosis")
        except Exception as ai_err:
            logger.warning(f"⚠️  AI analysis failed ({ai_err}), using demo diagnosis.")
            diagnosis = get_demo_diagnosis()
            used_demo = True
    else:
        diagnosis = get_demo_diagnosis()
        used_demo = True

    # ── Weather Analysis ──────────────────────────────────────────────────────
    weather = {}
    if lat_f and lon_f:
        try:
            weather = fetch_weather_forecast(lat_f, lon_f)
        except Exception:
            weather = {"spray_status": "unknown", "status_reason": "Weather unavailable"}

        # Enrich with Open-Meteo if fields are missing + normalise casing
        weather = enrich_weather_from_openmeteo(lat_f, lon_f, weather)
    else:
        weather = {"spray_status": "unknown", "status_reason": "No GPS location provided"}

    execution_plan = build_execution_plan(diagnosis, weather)

    # ── Save to DB ────────────────────────────────────────────────────────────
    record = ScanRecord(
        timestamp      = datetime.now(timezone.utc),
        latitude       = lat_f,
        longitude      = lon_f,
        disease_name   = diagnosis.get("disease_name", "Unknown"),
        severity_score = diagnosis.get("severity_score", 0),
        symptoms       = json.dumps(diagnosis.get("symptoms", [])),
        treatment_advice = diagnosis.get("treatment_advice", ""),
        weather_summary  = json.dumps(weather),
        spray_status     = weather.get("spray_status", "unknown"),
        execution_plan   = execution_plan,
        image_filename   = image_file.filename,
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({
        "success":        True,
        "scan_id":        record.id,
        "diagnosis":      diagnosis,
        "weather":        weather,   # now always includes temp_max/humidity/rainfall/wind_speed
        "execution_plan": execution_plan,
        "demo_mode":      used_demo,
    }), 200


@app.route("/api/chat", methods=["POST"])
def chat_api():
    data  = request.json or {}
    reply = ""
    if _gemini_available:
        try:
            reply = chat_with_agronomist(data.get("message", ""))
        except Exception as e:
            logger.warning(f"⚠️  Chat failed: {e}")
    if not reply:
        reply = ("AgriUstaad AI is in demo mode. Describe your crop problem and "
                 "I'll give you general farming advice!")
    return jsonify({"reply": reply})


@app.route("/api/scans", methods=["GET"])
def api_scans():
    records = (db.session.query(ScanRecord)
               .order_by(ScanRecord.timestamp.desc())
               .limit(500).all())
    return jsonify({"count": len(records), "scans": [r.to_dict() for r in records]})


@app.route("/report/<int:scan_id>", methods=["GET"])
def download_report(scan_id):
    record = db.session.get(ScanRecord, scan_id)
    if not record:
        abort(404)
    pdf_bytes = generate_farm_health_passport(record.to_dict())
    filename  = f"FarmHealthPassport_{scan_id}.pdf"
    response  = make_response(pdf_bytes)
    response.headers["Content-Type"]        = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


@app.route("/manifest.json")
def manifest():
    return app.send_static_file("uploads/manifest.json")


@app.route("/sw.js")
def service_worker():
    response = make_response(app.send_static_file("uploads/sw.js"))
    response.headers["Content-Type"]          = "application/javascript"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.route("/api/test-gemini", methods=["GET"])
def test_gemini():
    """Debug endpoint — visit /api/test-gemini in browser to check AI status."""
    if not _gemini_available:
        return jsonify({"status": "error", "message": "GEMINI_API_KEY missing from .env"}), 500
    try:
        from services.ai_service import _generate_with_fallback
        reply = _generate_with_fallback("Say exactly: GEMINI_OK")
        return jsonify({"status": "ok", "reply": reply})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Database Init ─────────────────────────────────────────────────────────────
def create_tables():
    with app.app_context():
        # Import auth models so SQLAlchemy registers them before create_all
        from auth import User, FarmerProfile  # noqa: F401
        db.create_all()

if __name__ == "__main__":
    create_tables()
    app.run(host="0.0.0.0", port=5000, debug=True)
