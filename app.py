"""
AgriCopilot - Main Flask Application
Agriculture Decision Support System with AI-powered crop disease detection.
"""

import os
import json
import logging
import traceback
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template,
    send_file, abort, make_response
)
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv

# ── Load Environment ──────────────────────────────────────────────────────────
load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agricopilot")

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///agricopilot.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

# ── CORS — allow Netlify frontend + local dev ─────────────────────────────────
CORS(app, origins=[
    "https://*.netlify.app",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:3000",
])

# ── Database ──────────────────────────────────────────────────────────────────
from models import db, ScanRecord
db.init_app(app)

# ── Services ──────────────────────────────────────────────────────────────────
from services.ai_service import analyze_crop_image, get_demo_diagnosis, initialize_gemini, chat_with_agronomist
from services.weather_service import fetch_weather_forecast
from services.pdf_service import generate_farm_health_passport

# ── Initialize Gemini ─────────────────────────────────────────────────────────
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

def build_execution_plan(diagnosis: dict, weather: dict) -> str:
    """Merge AI diagnosis with weather context into a farmer-friendly execution plan."""
    disease      = diagnosis.get("disease_name", "Unknown")
    severity     = diagnosis.get("severity_score", 0)
    spray_status = weather.get("spray_status", "Unknown")
    reason       = weather.get("status_reason", "")
    treatment    = diagnosis.get("treatment_advice", "")

    if disease == "Yield Estimation":
        return f"YIELD REPORT: {diagnosis.get('yield_estimate', 'N/A')}. HARVEST ADVICE: {diagnosis.get('market_advice', 'Check market prices.')}"

    if disease == "Soil Analysis":
        return f"SOIL REPORT: Type: {diagnosis.get('soil_type', 'N/A')}, Moisture: {diagnosis.get('moisture_level', 'N/A')}. RECOMMENDATION: {diagnosis.get('treatment_advice', '')}"

    if spray_status == "GREEN":
        timing = "CONDITIONS IDEAL. Spray immediately."
    elif spray_status == "YELLOW":
        timing = "CAUTION. High wind/rain risk."
    else:
        timing = "DO NOT SPRAY. Rain expected."

    return f"DIAGNOSIS: {disease} (Severity: {severity}%). WEATHER: {reason}. ADVISORY: {timing} TREATMENT: {treatment}"

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

    # AI Analysis
    if _gemini_available:
        diagnosis = analyze_crop_image(image_bytes, image_file.mimetype or "image/jpeg", mode=scan_mode)
    else:
        diagnosis = get_demo_diagnosis()

    # Weather Analysis
    if lat_f and lon_f:
        try:
            weather = fetch_weather_forecast(lat_f, lon_f)
        except Exception:
            weather = {"spray_status": "Unknown", "status_reason": "Weather unavailable"}
    else:
        weather = {"spray_status": "Unknown", "status_reason": "No GPS provided"}

    execution_plan = build_execution_plan(diagnosis, weather)

    # Save to DB
    record = ScanRecord(
        timestamp      = datetime.now(timezone.utc),
        latitude       = lat_f,
        longitude      = lon_f,
        disease_name   = diagnosis.get("disease_name", "Unknown"),
        severity_score = diagnosis.get("severity_score", 0),
        symptoms       = json.dumps(diagnosis.get("symptoms", [])),
        treatment_advice = diagnosis.get("treatment_advice", ""),
        weather_summary  = json.dumps(weather),
        spray_status     = weather.get("spray_status", "Unknown"),
        execution_plan   = execution_plan,
        image_filename   = image_file.filename,
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({
        "success":       True,
        "scan_id":       record.id,
        "diagnosis":     diagnosis,
        "weather":       weather,
        "execution_plan": execution_plan,
        "demo_mode":     not _gemini_available,
    }), 200


@app.route("/api/chat", methods=["POST"])
def chat_api():
    data = request.json or {}
    if _gemini_available:
        reply = chat_with_agronomist(
            data.get("message", ""),
            system_note=data.get("system_note", "")
        )
    else:
        reply = "Demo mode: please set GEMINI_API_KEY to enable chat."
    return jsonify({"reply": reply})


@app.route("/api/scans", methods=["GET"])
def api_scans():
    records = (
        db.session.query(ScanRecord)
        .order_by(ScanRecord.timestamp.desc())
        .limit(500)
        .all()
    )
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


# ── Database Init ─────────────────────────────────────────────────────────────
def create_tables():
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    create_tables()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_ENV") != "production")
