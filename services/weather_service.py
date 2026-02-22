"""
AgriCopilot - Weather Service (OpenWeatherMap)
Fetches 24-hour forecasts and computes spray safety status for precision agriculture.

SPRAY STATUS LOGIC:
  green  → Safe to spray   (rain prob < 20%, wind < 15 km/h)
  yellow → Caution         (rain prob 20-50% OR wind 15-25 km/h)
  red    → Do NOT spray    (rain prob > 50% OR wind > 25 km/h)
"""

import os
import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

OWM_BASE_URL     = "https://api.openweathermap.org/data/2.5"
OWM_FORECAST_URL = f"{OWM_BASE_URL}/forecast"

# Spray safety thresholds
RAIN_PROB_SAFE    = 0.20    # 20% probability = upper safe limit
RAIN_PROB_CAUTION = 0.50    # 50% probability = upper caution limit
WIND_SAFE_KMH     = 15.0    # km/h upper safe wind limit
WIND_CAUTION_KMH  = 25.0    # km/h upper caution wind limit


def fetch_weather_forecast(lat: float, lon: float) -> dict:
    """
    Fetch 24-hour weather forecast for given coordinates.

    Returns a dict with keys that match what the frontend and app.py expect:
        temp_max, temp_min, humidity, rainfall, wind_speed,
        spray_status (lowercase), status_reason, location_name, ...
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        logger.warning("OPENWEATHER_API_KEY not set. Returning demo weather data.")
        return _get_demo_weather(lat, lon)

    try:
        params = {
            "lat": lat,
            "lon": lon,
            "appid": api_key,
            "units": "metric",
            "cnt": 8,   # 8 x 3-hour intervals = 24 hours
        }

        response = requests.get(OWM_FORECAST_URL, params=params, timeout=10)
        response.raise_for_status()
        return _parse_forecast(response.json())

    except requests.exceptions.Timeout:
        logger.error("OpenWeatherMap API request timed out.")
        raise ConnectionError("Weather API timed out.")
    except requests.exceptions.HTTPError as e:
        logger.error(f"OpenWeatherMap HTTP error: {e.response.status_code}")
        if e.response.status_code == 401:
            raise ValueError("Invalid OpenWeatherMap API key.") from e
        raise
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        raise


def _parse_forecast(data: dict) -> dict:
    """Parse OWM forecast JSON into a weather summary the frontend understands."""
    intervals     = data.get("list", [])
    location_name = data.get("city", {}).get("name", "Unknown Location")
    country       = data.get("city", {}).get("country", "")

    if not intervals:
        raise ValueError("No forecast data returned from OpenWeatherMap.")

    max_rain_prob = 0.0
    max_wind_kmh  = 0.0
    temps         = []
    humidities    = []
    rainfalls     = []
    hourly_summaries = []

    for item in intervals:
        dt        = datetime.fromtimestamp(item["dt"], tz=timezone.utc)
        rain_prob = float(item.get("pop", 0))
        wind_ms   = float(item.get("wind", {}).get("speed", 0))
        wind_kmh  = wind_ms * 3.6
        temp      = float(item.get("main", {}).get("temp", 0))
        humidity  = float(item.get("main", {}).get("humidity", 0))
        rain_mm   = item.get("rain", {}).get("3h", 0.0)   # rainfall in last 3h window
        desc      = item.get("weather", [{}])[0].get("description", "")

        max_rain_prob = max(max_rain_prob, rain_prob)
        max_wind_kmh  = max(max_wind_kmh, wind_kmh)
        temps.append(temp)
        humidities.append(humidity)
        rainfalls.append(rain_mm)

        hourly_summaries.append({
            "time":         dt.strftime("%H:%M UTC"),
            "rain_prob_pct": round(rain_prob * 100),
            "wind_kmh":     round(wind_kmh, 1),
            "temp_c":       round(temp, 1),
            "humidity_pct": round(humidity),
            "description":  desc.capitalize(),
        })

    avg_temp     = round(sum(temps) / len(temps), 1)       if temps       else 0
    avg_humidity = round(sum(humidities) / len(humidities)) if humidities else 0
    total_rain   = round(sum(rainfalls), 1)

    spray_status, status_color, status_reason = _calculate_spray_status(
        max_rain_prob, max_wind_kmh
    )

    return {
        # ── Frontend-expected field names ──────────────────────────────────────
        "temp_max":   round(max(temps), 1) if temps else None,
        "temp_min":   round(min(temps), 1) if temps else None,
        "humidity":   avg_humidity,          # matches frontend w.humidity
        "rainfall":   total_rain,            # matches frontend w.rainfall
        "wind_speed": round(max_wind_kmh, 1),# matches frontend w.wind_speed
        "spray_status": spray_status,        # lowercase: "green"/"yellow"/"red"
        "status_reason": status_reason,

        # ── Extra context kept for execution plan / history ────────────────────
        "location_name":        f"{location_name}, {country}".strip(", "),
        "hourly_summary":       hourly_summaries,
        "max_rain_prob_pct":    round(max_rain_prob * 100),
        "max_wind_kmh":         round(max_wind_kmh, 1),
        "temperature_c":        avg_temp,    # kept for backwards compat
        "humidity_pct":         avg_humidity,
        "status_color":         status_color,
        "forecast_window_hours": len(intervals) * 3,
    }


def _calculate_spray_status(rain_prob: float, wind_kmh: float) -> tuple:
    """
    Apply precision agriculture spray safety rules.
    Returns (status_text, color_code, reason_string).
    NOTE: status_text is lowercase ("green"/"yellow"/"red") so the frontend badge works.
    """
    if rain_prob > RAIN_PROB_CAUTION or wind_kmh > WIND_CAUTION_KMH:
        reason = "⛔ DO NOT SPRAY — "
        parts  = []
        if rain_prob > RAIN_PROB_CAUTION:
            parts.append(f"High rain probability: {round(rain_prob * 100)}%")
        if wind_kmh > WIND_CAUTION_KMH:
            parts.append(f"Wind too high: {round(wind_kmh, 1)} km/h")
        return "red", "#FF3B30", reason + " | ".join(parts)

    elif rain_prob > RAIN_PROB_SAFE or wind_kmh > WIND_SAFE_KMH:
        reason = "⚠️ SPRAY WITH CAUTION — "
        parts  = []
        if rain_prob > RAIN_PROB_SAFE:
            parts.append(f"Moderate rain probability: {round(rain_prob * 100)}%")
        if wind_kmh > WIND_SAFE_KMH:
            parts.append(f"Moderate wind: {round(wind_kmh, 1)} km/h")
        return "yellow", "#FF9500", reason + " | ".join(parts)

    else:
        return (
            "green", "#34C759",
            f"✅ SAFE TO SPRAY — Rain probability: {round(rain_prob * 100)}% | "
            f"Wind speed: {round(wind_kmh, 1)} km/h"
        )


def _get_demo_weather(lat: float, lon: float) -> dict:
    """Demo weather data for testing without an API key."""
    return {
        # ── Frontend-expected field names ──
        "temp_max":    32.0,
        "temp_min":    22.0,
        "humidity":    62,
        "rainfall":    1.2,
        "wind_speed":  9.2,
        "spray_status":  "green",
        "status_reason": "✅ SAFE TO SPRAY — Rain probability: 12% | Wind speed: 9.2 km/h",

        # ── Extra context ──
        "location_name":        f"Field Location ({lat:.3f}, {lon:.3f})",
        "hourly_summary": [
            {"time": f"{h:02d}:00 UTC", "rain_prob_pct": 10, "wind_kmh": 8.5,
             "temp_c": 24.0, "humidity_pct": 62, "description": "Partly cloudy"}
            for h in range(0, 24, 3)
        ],
        "max_rain_prob_pct":    12,
        "max_wind_kmh":         9.2,
        "temperature_c":        24.0,
        "humidity_pct":         62,
        "status_color":         "#34C759",
        "forecast_window_hours": 24,
        "demo_mode":            True,
    }
