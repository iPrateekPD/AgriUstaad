"""
AgriUstad - AI Service
Handles multimodal vision and reasoning using Gemini 2.5 Flash via the new google-genai SDK.
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

def initialize_gemini():
    """Initialize the new Gemini API client."""
    global client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing.")
    # The new SDK uses a Client object
    client = genai.Client(api_key=api_key)

def chat_with_agronomist(user_message: str) -> str:
    """Gemini-powered interactive Q&A for preventative farming advice."""
    global client
    if not client:
        initialize_gemini()
        
    try:
        prompt = f"""
        You are an expert, empathetic agronomist advising a smallholder farmer in India.
        Keep your advice highly practical, simple, and concise (under 3-4 sentences). 
        Farmer says: "{user_message}"
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Chatbot error: {e}")
        return "I'm having trouble connecting right now. Please try asking again later."

def analyze_crop_image(image_bytes: bytes, mime_type: str, mode: str = "field") -> dict:
    """
    Handles Field Diagnosis, Crate Checks, Yield Estimation, and Soil Analysis.
    """
    global client
    if not client:
        initialize_gemini()

    try:
        # ─── FEATURE: AI YIELD ESTIMATOR ───
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

        # ─── FEATURE: AI SOIL ANALYSIS ───
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

        # ─── FEATURE: CRATE CHECK ───
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

        # ─── MAIN FIELD SCAN (Updated with dynamic URL support) ───
        else:
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
            
            - "govt_subsidy": Name of a relevant Indian gov scheme (e.g. PM-KISAN, NFSM).
            - "govt_scheme_url": The official gov.in website URL for this specific scheme.
            - "roi_calculation": A string like "Spend ₹500 to save ₹4000 crop value".
            - "sustainability_score": 0-10 (10=Organic/Eco-friendly, 0=Heavy Chemical).
            """
            
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=mime_type
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, image_part]
        )
        
        response_text = response.text.strip()
        
        # ─── BULLETPROOF JSON EXTRACTION ───
        # This regex finds everything from the first '{' to the last '}'
        # ignoring any conversational text Gemini might have added.
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        
        if match:
            clean_json = match.group(0)
        else:
            clean_json = response_text
            
        return json.loads(clean_json)
        
    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        return {
            "disease_name": "Analysis Error",
            "severity_score": 0,
            "symptoms": ["Could not connect to AI"],
            "treatment_advice": "Please check your internet connection or API key."
        }

def get_demo_diagnosis() -> dict:
    """Fallback demo data."""
    return {
        "disease_name": "Nitrogen Deficiency (Demo)",
        "severity_score": 65,
        "confidence_level": "High",
        "affected_crop_part": "Lower Leaves",
        "symptoms": ["Yellowing leaves", "Stunted growth"],
        "treatment_advice": "Apply Urea. Cost: ₹800/acre.",
        "govt_subsidy": "NFSM Soil Health Card",
        "govt_scheme_url": "https://www.soilhealth.dac.gov.in/",
        "roi_calculation": "High ROI: Save 20% yield",
        "sustainability_score": 8
    }