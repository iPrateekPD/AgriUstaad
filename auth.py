"""
AgriUstaad - Authentication & Farmer Profile Blueprint
Handles user registration, login, logout, and farmer profile CRUD.
Integrates with existing Flask app without disturbing existing routes.
"""

import os
import json
import logging
from functools import wraps
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

from models import db

logger = logging.getLogger("agricopilot.auth")

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ── Inline Models (added to existing db instance) ────────────────────────────
class User(db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(180), unique=True, nullable=False, index=True)
    phone         = db.Column(db.String(20),  unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20),  default="farmer")   # farmer | admin
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    profile       = db.relationship("FarmerProfile", backref="user",
                                    uselist=False, cascade="all, delete-orphan",
                                    lazy="joined")

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def to_dict(self):
        return {
            "id":    self.id,
            "email": self.email,
            "phone": self.phone,
            "role":  self.role,
        }


class FarmerProfile(db.Model):
    __tablename__ = "farmer_profiles"
    id                = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    full_name         = db.Column(db.String(120))
    age               = db.Column(db.Integer)
    location          = db.Column(db.String(200))
    field_size_acres  = db.Column(db.Float)
    soil_type         = db.Column(db.String(80))       # Sandy / Clay / Loamy / Silty / etc.
    soil_ph           = db.Column(db.Float)
    soil_quality_notes= db.Column(db.Text)
    budget_inr        = db.Column(db.Integer)          # investment capacity in ₹
    previous_crops    = db.Column(db.Text)             # JSON list
    planned_crops     = db.Column(db.Text)             # JSON list
    irrigation        = db.Column(db.String(80))       # Drip / Flood / Rain-fed / None
    other_notes       = db.Column(db.Text)
    updated_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        def _j(v):
            try:    return json.loads(v) if v else []
            except: return []
        return {
            "full_name":         self.full_name,
            "age":               self.age,
            "location":          self.location,
            "field_size_acres":  self.field_size_acres,
            "soil_type":         self.soil_type,
            "soil_ph":           self.soil_ph,
            "soil_quality_notes":self.soil_quality_notes,
            "budget_inr":        self.budget_inr,
            "previous_crops":    _j(self.previous_crops),
            "planned_crops":     _j(self.planned_crops),
            "irrigation":        self.irrigation,
            "other_notes":       self.other_notes,
        }


# ── Session helper ────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required."}), 401
        return f(*args, **kwargs)
    return wrapper


def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
def register():
    data     = request.json or {}
    email    = (data.get("email") or "").strip().lower()
    phone    = (data.get("phone") or "").strip() or None
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists."}), 409

    user = User(email=email, phone=phone, role="farmer")
    user.set_password(password)

    # Empty profile created immediately so frontend can populate it
    profile = FarmerProfile(user=user)
    db.session.add(user)
    db.session.add(profile)
    db.session.commit()

    session["user_id"] = user.id
    session.permanent  = True
    logger.info(f"New user registered: {email}")
    return jsonify({"success": True, "user": user.to_dict()}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data     = request.json or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password."}), 401

    session["user_id"] = user.id
    session.permanent  = True
    logger.info(f"User logged in: {email}")
    return jsonify({"success": True, "user": user.to_dict()}), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"success": True}), 200


@auth_bp.route("/me", methods=["GET"])
def me():
    user = current_user()
    if not user:
        return jsonify({"logged_in": False}), 200
    return jsonify({
        "logged_in": True,
        "user":      user.to_dict(),
        "profile":   user.profile.to_dict() if user.profile else {},
    }), 200


@auth_bp.route("/profile", methods=["PUT"])
@login_required
def update_profile():
    user = current_user()
    data = request.json or {}

    p = user.profile or FarmerProfile(user_id=user.id)

    def _s(v): return str(v).strip() if v else None
    def _i(v):
        try:    return int(v)
        except: return None
    def _f(v):
        try:    return float(v)
        except: return None

    p.full_name          = _s(data.get("full_name"))
    p.age                = _i(data.get("age"))
    p.location           = _s(data.get("location"))
    p.field_size_acres   = _f(data.get("field_size_acres"))
    p.soil_type          = _s(data.get("soil_type"))
    p.soil_ph            = _f(data.get("soil_ph"))
    p.soil_quality_notes = _s(data.get("soil_quality_notes"))
    p.budget_inr         = _i(data.get("budget_inr"))
    p.previous_crops     = json.dumps(data.get("previous_crops", []))
    p.planned_crops      = json.dumps(data.get("planned_crops", []))
    p.irrigation         = _s(data.get("irrigation"))
    p.other_notes        = _s(data.get("other_notes"))
    p.updated_at         = datetime.now(timezone.utc)

    if not user.profile:
        db.session.add(p)
    db.session.commit()
    return jsonify({"success": True, "profile": p.to_dict()}), 200


@auth_bp.route("/recommend", methods=["POST"])
@login_required
def recommend():
    """
    AI-powered crop recommendation based on farmer profile.
    Uses a structured prompt sent to Gemini; falls back to demo data.
    """
    user = current_user()
    if not user or not user.profile:
        return jsonify({"error": "Profile not found."}), 404

    p    = user.profile
    data = request.json or {}

    # ── Build context ─────────────────────────────────────────────────────────
    profile_ctx = {
        "location":       p.location or data.get("location", "Unknown"),
        "soil_type":      p.soil_type or "Loamy",
        "soil_ph":        p.soil_ph or 6.5,
        "field_size":     p.field_size_acres or 2,
        "budget_inr":     p.budget_inr or 10000,
        "irrigation":     p.irrigation or "Rain-fed",
        "planned_crops":  json.loads(p.planned_crops) if p.planned_crops else [],
        "previous_crops": json.loads(p.previous_crops) if p.previous_crops else [],
    }

    # ── Try Gemini ────────────────────────────────────────────────────────────
    try:
        from services.ai_service import _generate_with_fallback
        import re

        prompt = f"""
You are an expert agricultural advisor for Indian farmers. Based on the farmer profile below,
provide crop recommendations as ONLY valid JSON with NO extra text.

Farmer Profile:
- Location: {profile_ctx['location']}
- Soil Type: {profile_ctx['soil_type']} (pH: {profile_ctx['soil_ph']})
- Field Size: {profile_ctx['field_size']} acres
- Budget: ₹{profile_ctx['budget_inr']}
- Irrigation: {profile_ctx['irrigation']}
- Planned Crops: {', '.join(profile_ctx['planned_crops']) or 'Not specified'}
- Previous Crops: {', '.join(profile_ctx['previous_crops']) or 'Not specified'}

Return ONLY a JSON object:
{{
  "top_crops": [
    {{
      "name": "Crop Name",
      "suitability_score": 85,
      "reason": "One line why it suits this farm",
      "expected_return_inr": 25000,
      "investment_inr": 8000,
      "duration_days": 90,
      "risk_level": "Low/Medium/High",
      "market_demand": "High/Medium/Low",
      "market_price_qtl": "₹2500/qtl"
    }}
  ],
  "oversupply_warnings": [
    {{
      "crop": "Crop Name",
      "warning": "Warning message about market saturation"
    }}
  ],
  "govt_schemes": [
    {{
      "name": "Scheme Name",
      "benefit": "Short description",
      "url": "https://..."
    }}
  ],
  "equipment_rental": [
    {{
      "tool": "Tool name",
      "rental_cost": "₹X/day",
      "where": "Local source"
    }}
  ],
  "sustainability_tip": "One actionable eco-tip"
}}
"""
        raw  = _generate_with_fallback(prompt)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(match.group(0)) if match else _demo_recommendation(profile_ctx)
        return jsonify({"success": True, "recommendation": result, "demo": False}), 200

    except Exception as e:
        logger.warning(f"AI recommendation failed: {e}. Using demo.")
        return jsonify({
            "success": True,
            "recommendation": _demo_recommendation(profile_ctx),
            "demo": True
        }), 200


def _demo_recommendation(ctx):
    """Demo recommendation when AI is unavailable."""
    return {
        "top_crops": [
            {
                "name": "Paddy (Short Duration)",
                "suitability_score": 88,
                "reason": f"Excellent for {ctx.get('soil_type','Loamy')} soil with {ctx.get('irrigation','Rain-fed')} irrigation",
                "expected_return_inr": 28000,
                "investment_inr": 8500,
                "duration_days": 110,
                "risk_level": "Low",
                "market_demand": "High",
                "market_price_qtl": "₹2,369/qtl"
            },
            {
                "name": "Green Gram (Moong)",
                "suitability_score": 82,
                "reason": "High protein crop, soil nitrogen fixation benefit, fast 60-day cycle",
                "expected_return_inr": 22000,
                "investment_inr": 5000,
                "duration_days": 65,
                "risk_level": "Low",
                "market_demand": "High",
                "market_price_qtl": "₹8,550/qtl"
            },
            {
                "name": "Onion",
                "suitability_score": 74,
                "reason": "High market value, good demand in Odisha mandis",
                "expected_return_inr": 35000,
                "investment_inr": 12000,
                "duration_days": 130,
                "risk_level": "Medium",
                "market_demand": "High",
                "market_price_qtl": "₹2,500/qtl"
            }
        ],
        "oversupply_warnings": [
            {
                "crop": "Tomato",
                "warning": "Tomato is widely cultivated in your region this season. Market saturation may reduce profit margins by 30-40%. Consider Green Gram for better demand-supply balance."
            }
        ],
        "govt_schemes": [
            {
                "name": "PM-KISAN",
                "benefit": "₹6,000/year direct income support for small & marginal farmers",
                "url": "https://pmkisan.gov.in/"
            },
            {
                "name": "NFSM — National Food Security Mission",
                "benefit": "Seeds, fertilisers, irrigation tools subsidised for rice/wheat/pulses",
                "url": "https://nfsm.gov.in/"
            },
            {
                "name": "Soil Health Card Scheme",
                "benefit": "Free soil testing & nutrient recommendations every 2 years",
                "url": "https://soilhealth.dac.gov.in/"
            }
        ],
        "equipment_rental": [
            {
                "tool": "Tractor + Cultivator",
                "rental_cost": "₹800/day",
                "where": "Custom Hiring Centre (CHC) — nearest district HQ"
            },
            {
                "tool": "Sprayer (Knapsack)",
                "rental_cost": "₹150/day",
                "where": "Local agri input dealer or Krishi Vigyan Kendra"
            }
        ],
        "sustainability_tip": "Practice crop rotation between paddy and legumes to restore soil nitrogen naturally, reducing fertiliser costs by up to 20% next season."
    }