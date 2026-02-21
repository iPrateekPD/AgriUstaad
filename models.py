"""
AgriCopilot - Database Models
Defines the SQLAlchemy ORM models for spatio-temporal scan history.
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()


class ScanRecord(db.Model):
    """
    Stores every crop disease scan with GPS coordinates,
    AI diagnosis, weather context, and execution plan.
    Enables full spatio-temporal replay and map visualization.
    """
    __tablename__ = "scan_records"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Temporal metadata
    timestamp = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True
    )

    # Geospatial fields (WGS84 decimal degrees)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    # AI Diagnosis (from Gemini)
    disease_name = db.Column(db.String(256), nullable=False)
    severity_score = db.Column(db.Integer, nullable=False)  # 0-100
    symptoms = db.Column(db.Text, nullable=True)            # JSON array stored as text
    treatment_advice = db.Column(db.Text, nullable=True)

    # Weather context at time of scan
    weather_summary = db.Column(db.Text, nullable=True)     # JSON blob
    spray_status = db.Column(db.String(16), nullable=True)  # Green / Yellow / Red

    # Combined execution plan (AI + weather-aware recommendation)
    execution_plan = db.Column(db.Text, nullable=True)

    # Original image filename (stored for reference)
    image_filename = db.Column(db.String(512), nullable=True)

    def to_dict(self):
        """Serialize record to a JSON-safe dictionary."""
        symptoms_parsed = []
        if self.symptoms:
            try:
                symptoms_parsed = json.loads(self.symptoms)
            except (json.JSONDecodeError, TypeError):
                symptoms_parsed = [self.symptoms]

        weather_parsed = {}
        if self.weather_summary:
            try:
                weather_parsed = json.loads(self.weather_summary)
            except (json.JSONDecodeError, TypeError):
                weather_parsed = {}

        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() + "Z",
            "latitude": self.latitude,
            "longitude": self.longitude,
            "disease_name": self.disease_name,
            "severity_score": self.severity_score,
            "symptoms": symptoms_parsed,
            "treatment_advice": self.treatment_advice,
            "weather_summary": weather_parsed,
            "spray_status": self.spray_status,
            "execution_plan": self.execution_plan,
            "image_filename": self.image_filename,
        }

    def __repr__(self):
        return (
            f"<ScanRecord id={self.id} disease='{self.disease_name}' "
            f"severity={self.severity_score} ts={self.timestamp.isoformat()}>"
        )