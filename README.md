# 🌿 AgriUstaad — AI-Powered Farm Intelligence Platform

> **Hacknovation 2.0 · Team AgriCore**  
> An AI-powered super app for Indian farmers — diagnose crop diseases, estimate yields, analyse soil health, and get real-time advisory in your own language. Built for the field, by people who care about it.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-agriustaad.onrender.com-brightgreen)](https://agriustaad.onrender.com)
[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey)](https://flask.palletsprojects.com)
[![Gemini AI](https://img.shields.io/badge/AI-Gemini%202.0%20Flash-orange)](https://ai.google.dev)

---

## 📋 Table of Contents

- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Setup & Installation](#-setup--installation)
- [Environment Variables](#-environment-variables)
- [API Reference](#-api-reference)
- [Database Schema](#-database-schema)
- [Deployment](#-deployment-render)
- [Team](#-team)

---

## ✨ Features

### 🦠 AI Crop Disease Scanner
- Upload a photo of your crop — Gemini AI diagnoses disease, pest, or nutrient deficiency in seconds
- Returns severity score (0–100), treatment advice, ROI calculation, and government subsidy links
- **4 scan modes:** Field Diagnosis · Yield Estimation · Soil Analysis · Crate/Post-Harvest Check
- AI auto-classifies the image mode so farmers don't need to select manually

### 🌦️ Hyperlocal Weather Advisory
- Real-time 7-day weather dashboard using Open-Meteo API (no key required)
- **Spray Safety Indicator:** Green / Yellow / Red based on wind speed and rain probability
- Auto-detects farmer's GPS location on page load — no manual input needed
- Falls back to IP-based geolocation if GPS permission is denied

### 🔔 Smart Notification System
- Bell icon in navbar with unread badge count
- Alerts for: nearby disease outbreaks, spray advisories, mandi price drops, sowing tips, government scheme reminders
- Read state persists across sessions via localStorage
- Dynamic notifications pushed on location detection and scan events

### 👤 Farmer Authentication & Profile
- Secure login / sign-up with bcrypt-hashed passwords (never plain text)
- Farmer profile stores: name, age, location, field size, soil type & pH, budget, irrigation method, previous/planned crops
- Server-side Flask sessions with persistent login

### 🌱 AI Crop Recommendation Engine
- Uses farmer's saved profile (soil, budget, irrigation, location) to recommend the best crops for next season
- Oversupply warnings: alerts when too many farmers in the region are growing the same crop
- Demo market price table with demand/trend indicators
- Linked government schemes (PM-KISAN, NFSM, Soil Health Card) and equipment rental suggestions

### 🤖 Personalised AI Agronomist Chat (AgriUstaad AI)
- Chat widget powered by Gemini — answers crop questions in real time
- **Fully personalised:** automatically injects farmer's profile (soil type, field size, budget, crops, GPS location) into every query
- Supports 5+ Indian languages with auto-translation fallback
- Shows `✦ Personalised` badge when profile context is active

### 📄 Farm Health Passport (PDF)
- One-click PDF report generation for every scan
- Includes diagnosis, treatment plan, execution plan, and weather summary
- Designed for use with banks and financial institutions for crop loan documentation

### 🗓️ Smart Cultivation Calendar
- AI-generated week-by-week farming schedule based on crop type, sow date, and live weather
- Risk banners, irrigation reminders, and spray windows

### 📡 Community Radar
- Heatmap of disease outbreaks reported by farmers within 5 km
- Live mandi price ticker for Odisha markets

### 🌐 Multi-Language Support
- 5+ Indian languages: English, Hindi, Odia, Telugu, Bengali, Tamil
- Language selection on first visit with auto-translation of all UI strings

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, Flask, Flask-SQLAlchemy |
| AI / Vision | Google Gemini 2.0 Flash (via `google-genai` SDK) |
| Database | SQLite (dev) / PostgreSQL (prod via `DATABASE_URL`) |
| Weather | Open-Meteo API (free, no key) + OpenWeatherMap (optional) |
| Maps | Leaflet.js + Leaflet.heat |
| PDF | FPDF (server) + jsPDF (client-side) |
| Frontend | Vanilla JS, CSS3 (glass morphism design system) |
| Fonts | Cormorant Garamond + DM Sans |
| Hosting | Render (web service + free tier) |
| Auth | Werkzeug password hashing, Flask session |
| Geocoding | Nominatim (OpenStreetMap) + ipapi.co fallback |

---

## 📁 Project Structure

```
agriustaad/
│
├── app.py                  # Main Flask app — routes, scan logic, weather enrichment
├── auth.py                 # Auth Blueprint — login/signup/profile/AI recommendations
├── models.py               # SQLAlchemy models: ScanRecord
│
├── services/
│   ├── ai_service.py       # Gemini AI — image analysis, chat, model fallback chain
│   ├── weather_service.py  # OpenWeatherMap forecast + spray safety logic
│   └── pdf_service.py      # Farm Health Passport PDF generation
│
├── templates/
│   ├── index.html          # Main SPA — scanner, weather, chat, profile, calendar
│   └── history.html        # Scan history page
│
├── static/
│   ├── uploads/
│   │   ├── manifest.json   # PWA manifest
│   │   └── sw.js           # Service worker (offline mode)
│   └── icons/
│       └── icon-192.png    # App icon
│
├── .env                    # Environment variables (never commit this)
├── requirements.txt        # Python dependencies
└── README.md
```

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.10 or higher
- A [Google Gemini API key](https://aistudio.google.com/app/apikey) (free tier available)

### 1. Clone the repository
```bash
git clone https://github.com/iPrateekPD/AgriUs.git
cd AgriUs
```

### 2. Create and activate a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
```bash
cp .env.example .env
# Edit .env and add your keys (see Environment Variables section below)
```

### 5. Run the app
```bash
python app.py
```

Visit `http://localhost:5000` in your browser.

---

## 🔐 Environment Variables

Create a `.env` file in the project root:

```env
# Required
GEMINI_API_KEY=your_gemini_api_key_here
FLASK_SECRET_KEY=your_random_secret_key_here

# Optional — for enhanced weather data
OPENWEATHER_API_KEY=your_openweathermap_key_here

# Optional — for production database
DATABASE_URL=postgresql://user:password@host/dbname
```

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ Yes | Google Gemini API key for AI features |
| `FLASK_SECRET_KEY` | ✅ Yes | Random string for session security |
| `OPENWEATHER_API_KEY` | ⚪ Optional | Enhanced weather forecasts (falls back to Open-Meteo if missing) |
| `DATABASE_URL` | ⚪ Optional | PostgreSQL URL for production (uses SQLite locally if missing) |

> ⚠️ **Never commit your `.env` file.** It's already in `.gitignore`.

---

## 📡 API Reference

### Scan & Analysis
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/analyze` | Upload crop image for AI diagnosis + weather advisory |
| `GET` | `/api/scans` | Fetch all scan history (latest 500) |
| `GET` | `/report/<scan_id>` | Download Farm Health Passport PDF |

### Chat
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Send message to AI agronomist. Body: `{message, system_note}` |

### Authentication & Profile
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create new farmer account |
| `POST` | `/api/auth/login` | Login with email + password |
| `POST` | `/api/auth/logout` | End session |
| `GET` | `/api/auth/me` | Get current user + profile |
| `PUT` | `/api/auth/profile` | Update farmer profile |
| `POST` | `/api/auth/recommend` | Get AI crop recommendations based on profile |

### Utilities
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/test-gemini` | Debug endpoint — check if Gemini is connected |
| `GET` | `/history` | Scan history page |

---

## 🗄 Database Schema

### `scan_records`
| Column | Type | Description |
|---|---|---|
| `id` | Integer (PK) | Auto-increment scan ID |
| `timestamp` | DateTime | UTC time of scan |
| `latitude` / `longitude` | Float | GPS coordinates |
| `disease_name` | String | AI-diagnosed condition |
| `severity_score` | Integer | 0–100 severity |
| `symptoms` | JSON Text | List of visual symptoms |
| `treatment_advice` | Text | AI treatment recommendation |
| `weather_summary` | JSON Text | Full weather dict at scan time |
| `spray_status` | String | green / yellow / red |
| `execution_plan` | Text | Combined diagnosis + weather advisory |
| `image_filename` | String | Original uploaded filename |

### `users`
| Column | Type | Description |
|---|---|---|
| `id` | Integer (PK) | User ID |
| `email` | String (unique) | Login email |
| `phone` | String | Optional phone number |
| `password_hash` | String | Bcrypt-hashed password |
| `role` | String | `farmer` or `admin` |

### `farmer_profiles`
| Column | Type | Description |
|---|---|---|
| `user_id` | FK → users | One-to-one with User |
| `full_name` / `age` / `location` | String/Int | Personal info |
| `field_size_acres` | Float | Farm size |
| `soil_type` / `soil_ph` | String/Float | Soil data |
| `budget_inr` | Integer | Investment capacity in ₹ |
| `previous_crops` / `planned_crops` | JSON Text | Crop history & plans |
| `irrigation` | String | Drip / Flood / Rain-fed / None |

---

## ☁️ Deployment (Render)

The app is configured for zero-config deployment on [Render](https://render.com).

1. Push your code to GitHub
2. Create a new **Web Service** on Render, connect your GitHub repo
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `gunicorn app:app`
5. Add environment variables in Render dashboard (see above)
6. Deploy — Render auto-redeploys on every `git push`

> The app uses SQLite by default. For production, set `DATABASE_URL` to a PostgreSQL connection string (Render offers a free PostgreSQL instance).

---

## 👥 Team

**Team AgriCore — Hacknovation 2.0**

Built with ❤️ for the farmers of India.

---

## 📄 License

This project was built for a hackathon. All rights reserved by Team AgriCore.
