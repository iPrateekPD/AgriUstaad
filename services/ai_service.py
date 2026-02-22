"""
AgriUstad - AI Service
Handles multimodal vision and reasoning using Gemini via the google-genai SDK.
"""

import os
import json
import logging
import re
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Global client
client = None

# ── Model fallback chain ───────────────────────────────────────────────────────
# gemini-2.5-flash is preview and restricted to some API tiers.
# If it fails, we automatically try the next model in the list.
MODELS_TO_TRY = [
    "gemini-2.0-flash",       # stable, widely available ← primary
    "gemini-2.5-flash",       # preview, try if 2.0 unavailable
    "gemini-1.5-flash",       # legacy fallback
]


def initialize_gemini():
    """Initialize the Gemini API client."""
    global client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing.")
    client = genai.Client(api_key=api_key)
    logger.info("✅ Gemini client initialized.")


def _generate_with_fallback(contents) -> str:
    """
    Try each model in MODELS_TO_TRY until one succeeds.
    Returns the raw response text.
    Raises RuntimeError if all models fail.
    """
    global client
    if not client:
        initialize_gemini()

    last_error = None
    for model_name in MODELS_TO_TRY:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
            )
            logger.info(f"✅ Used model: {model_name}")
            return response.text.strip()
        except Exception as e:
            logger.warning(f"⚠️  Model {model_name} failed: {e}")
            last_error = e

    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")


def chat_with_agronomist(user_message: str) -> str:
    """Gemini-powered interactive Q&A for preventative farming advice."""
    try:
        prompt = (
            "You are an expert, empathetic agronomist advising a smallholder farmer in India. "
            "Keep your advice highly practical, simple, and concise (under 3-4 sentences).\n"
            f'Farmer says: "{user_message}"'
        )
        return _generate_with_fallback(prompt)
    except Exception as e:
        logger.error(f"Chatbot error: {e}")
        return (
            "I'm having trouble connecting right now. "
            "Please try asking again, or describe your crop problem in more detail."
        )


def analyze_crop_image(image_bytes: bytes, mime_type: str, mode: str = "field") -> dict:
    """
    Handles Field Diagnosis, Crate Checks, Yield Estimation, and Soil Analysis.
    Always returns a valid dict — never returns an error payload.
    Raises an exception on failure so app.py can fall back to demo mode.
    """
    # ── Build prompt based on mode ─────────────────────────────────────────────
    if mode == "yield":
        prompt = """
        Analyze this image of a crop/tree. Count the visible fruits/pods/vegetables.
        Return ONLY valid JSON with these keys:
        {
            "disease_name": "Yield Estimation",
            "severity_score": 0,
            "yield_estimate": "e.g., Approx 45 visible tomatoes",
            "harvest_readiness": "e.g., 80% ready",
            "market_advice": "e.g., Harvest in 3 days for peak price",
            "treatment_advice": "Prepare storage crates."
        }
        """

    elif mode == "soil":
        prompt = """
        Analyze this soil image (texture, color, cracking).
        Return ONLY valid JSON with these keys:
        {
            "disease_name": "Soil Analysis",
            "severity_score": 0,
            "soil_type": "e.g., Clay Loam or Sandy",
            "moisture_level": "Low/Medium/High",
            "organic_matter": "Estimated Low/High",
            "treatment_advice": "e.g., Add gypsum and organic compost to improve water retention."
        }
        """

    elif mode == "crate":
        prompt = """
        You are an AI post-harvest quality inspector. Analyze this crate of harvested crops for rot, damage, or spoilage.
        Return ONLY a valid JSON object:
        - "disease_name": The specific type of rot or damage (or "Healthy" if none).
        - "severity_score": An integer 0-100 estimating the percentage of the crate affected.
        - "confidence_level": "High", "Medium", or "Low".
        - "affected_crop_part": "Harvested Produce".
        - "symptoms": A list of visual signs of rot/damage.
        - "treatment_advice": Actionable sorting/storage advice.
        """

    else:  # field (default)
        prompt = """
        You are an expert agronomist AI. Analyze this crop image for pests, diseases, or nutrient deficiencies.
        Crucially, distinguish between biological infections and mineral deficiencies (soil hunger).

        Return ONLY a valid JSON object with the following keys:
        - "disease_name": The name of the disease, pest, or nutrient deficiency.
        - "severity_score": An integer from 0 to 100.
        - "confidence_level": "High", "Medium", or "Low".
        - "affected_crop_part": E.g., "Leaves", "Stem", "Fruit".
        - "symptoms": A list of 2-4 strings describing visual symptoms.
        - "treatment_advice": Actionable treatment advice with rough budget.
        - "expected_cause": One sentence on the likely biological/environmental cause.
        - "prevention_tips": A list of 3-5 prevention steps.
        - "govt_subsidy": Name of a relevant Indian gov scheme (e.g. PM-KISAN, NFSM).
        - "govt_scheme_url": The official gov.in website URL for this specific scheme.
        - "roi_calculation": A string like "Spend ₹500 to save ₹4000 crop value".
        - "sustainability_score": 0-10 (10=Organic/Eco-friendly, 0=Heavy Chemical).
        """

    # ── Call Gemini with model fallback ────────────────────────────────────────
    image_part    = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    response_text = _generate_with_fallback([prompt, image_part])

    # ── Bulletproof JSON extraction ────────────────────────────────────────────
    # Find outermost { ... } block, ignoring any conversational text Gemini adds
    match = re.search(r'\{.*\}', response_text, re.DOTALL)
    clean_json = match.group(0) if match else response_text
    result = json.loads(clean_json)

    # ── Sanity check: if Gemini returned an error payload, raise so app.py
    #    can fall back to demo instead of showing "Analysis Error" to the user
    _error_signals = ("analysis error", "api key", "check your internet", "quota")
    _result_text   = " ".join([
        str(result.get("disease_name",     "")),
        str(result.get("treatment_advice", "")),
    ]).lower()
    if any(sig in _result_text for sig in _error_signals):
        raise RuntimeError(f"Gemini returned an error payload: {result.get('disease_name')}")

    return result


def get_demo_diagnosis() -> dict:
    """Fallback demo data when AI is unavailable."""
    return {
        "disease_name":       "Nitrogen Deficiency (Demo)",
        "severity_score":     65,
        "confidence_level":   "High",
        "affected_crop_part": "Lower Leaves",
        "symptoms":           ["Yellowing of lower leaves", "Pale green upper canopy", "Stunted growth"],
        "treatment_advice":   "Apply Urea at 50 kg/acre. Cost: ₹800/acre. Re-check in 10 days.",
        "expected_cause":     "Insufficient nitrogen in soil due to leaching or poor organic matter.",
        "prevention_tips": [
            "Test soil before every season.",
            "Use slow-release fertilisers to reduce leaching.",
            "Incorporate green manure crops in rotation.",
            "Maintain optimal irrigation to prevent nutrient runoff.",
        ],
        "govt_subsidy":       "NFSM Soil Health Card",
        "govt_scheme_url":    "https://www.soilhealth.dac.gov.in/",
        "roi_calculation":    "Spend ₹800 on Urea → save 20% of ₹12,000 yield = ₹2,400 gain",
        "sustainability_score": 6,
    }
