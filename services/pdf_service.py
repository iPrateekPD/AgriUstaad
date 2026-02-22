"""
AgriCopilot - PDF Service
Generates the Farm Health Passport for financial inclusion.
"""

from fpdf import FPDF
from datetime import datetime

def generate_farm_health_passport(record_dict: dict) -> bytes:
    """
    Creates a PDF report from a scan record.
    """
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(26, 122, 66) # AgriCopilot Green
    pdf.cell(200, 10, txt="AgriCopilot: Farm Health Passport", ln=True, align='C')
    
    pdf.set_font("Arial", 'I', 10)
    pdf.set_text_color(100, 100, 100)
    date_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    pdf.cell(200, 10, txt=f"Generated on: {date_str}", ln=True, align='C')
    pdf.ln(10)
    
    # Scan Details
    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(200, 10, txt="1. Scan & Location Details", ln=True)
    pdf.set_font("Arial", '', 11)
    pdf.cell(200, 8, txt=f"Scan ID: {record_dict.get('id', 'N/A')}", ln=True)
    lat = record_dict.get('latitude')
    lon = record_dict.get('longitude')
    pdf.cell(200, 8, txt=f"Coordinates: {lat}, {lon}", ln=True)
    pdf.ln(5)
    
    # Diagnosis
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="2. AI Diagnosis", ln=True)
    pdf.set_font("Arial", '', 11)
    pdf.cell(200, 8, txt=f"Condition: {record_dict.get('disease_name', 'Unknown')}", ln=True)
    pdf.cell(200, 8, txt=f"Severity Score: {record_dict.get('severity_score', '0')}/100", ln=True)
    pdf.ln(5)
    
    # Symptoms
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="3. Identified Symptoms", ln=True)
    pdf.set_font("Arial", '', 11)
    symptoms = record_dict.get('symptoms', [])
    for symptom in symptoms:
        pdf.cell(200, 8, txt=f"- {symptom}", ln=True)
    pdf.ln(5)
    
    # Execution Plan & Treatment
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="4. Treatment & Execution Plan", ln=True)
    pdf.set_font("Arial", '', 10)
    # Using encode/decode to handle special characters in FPDF
    plan_text = str(record_dict.get('execution_plan', '')).encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 8, txt=plan_text)
    pdf.ln(5)
    
    # Financial/Bank Note
    pdf.set_font("Arial", 'I', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 6, txt="Note for Financial Institutions: This document verifies proactive crop management and risk mitigation strategies implemented by the farmer.")
    
    return pdf.output(dest='S').encode('latin1')
