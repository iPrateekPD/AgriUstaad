"""
AgriCopilot - Weather Service (OpenWeatherMap)
Fetches 24-hour forecasts and computes spray safety status for precision agriculture.

SPRAY STATUS LOGIC:
  GREEN  → Safe to spray   (rain prob < 20%, wind < 15 km/h)
  YELLOW → Caution         (rain prob 20-50% OR wind 15-25 km/h)
  RED    → Do NOT spray    (rain prob > 50% OR wind > 25 km/h)
"""

import os
import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

OWM_BASE_URL = "https://api.openweathermap.org/data/2.5"
OWM_FORECAST_URL = f"{OWM_BASE_URL}/forecast"

# Spray safety thresholds
RAIN_PROB_SAFE = 0.20       # 20% probability = upper safe limit
RAIN_PROB_CAUTION = 0.50    # 50% probability = upper caution limit
WIND_SAFE_KMH = 15.0        # km/h upper safe wind limit
WIND_CAUTION_KMH = 25.0     # km/h upper caution wind limit


def fetch_weather_forecast(lat: float, lon: float) -> dict:
    """
    Fetch 24-hour weather forecast for given coordinates.

    Args:
        lat: Latitude (WGS84)
        lon: Longitude (WGS84)

    Returns:
        dict with: hourly_summary, max_rain_prob, max_wind_kmh,
                   spray_status, status_color, status_reason,
                   temperature_c, humidity_pct, location_name
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
        data = response.json()

        return _parse_forecast(data)

    except requests.exceptions.Timeout:
        logger.error("OpenWeatherMap API request timed out.")
        raise ConnectionError("Weather API timed out. Using default conservative estimate.")
    except requests.exceptions.HTTPError as e:
        logger.error(f"OpenWeatherMap API HTTP error: {e.response.status_code}")
        if e.response.status_code == 401:
            raise ValueError("Invalid OpenWeatherMap API key.") from e
        raise
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        raise


def _parse_forecast(data: dict) -> dict:
    """Parse OWM forecast JSON into AgriCopilot weather summary."""
    intervals = data.get("list", [])
    location_name = data.get("city", {}).get("name", "Unknown Location")
    country = data.get("city", {}).get("country", "")

    if not intervals:
        raise ValueError("No forecast data returned from OpenWeatherMap.")

    # Compute maximums across the 24-hour window
    max_rain_prob = 0.0
    max_wind_kmh = 0.0
    hourly_summaries = []
    temps = []
    humidities = []

    for item in intervals:
        dt = datetime.fromtimestamp(item["dt"], tz=timezone.utc)
        rain_prob = float(item.get("pop", 0))           # probability of precipitation (0-1)
        wind_ms = float(item.get("wind", {}).get("speed", 0))
        wind_kmh = wind_ms * 3.6
        temp = float(item.get("main", {}).get("temp", 0))
        humidity = float(item.get("main", {}).get("humidity", 0))
        desc = item.get("weather", [{}])[0].get("description", "")

        max_rain_prob = max(max_rain_prob, rain_prob)
        max_wind_kmh = max(max_wind_kmh, wind_kmh)
        temps.append(temp)
        humidities.append(humidity)

        hourly_summaries.append({
            "time": dt.strftime("%H:%M UTC"),
            "rain_prob_pct": round(rain_prob * 100),
            "wind_kmh": round(wind_kmh, 1),
            "temp_c": round(temp, 1),
            "humidity_pct": round(humidity),
            "description": desc.capitalize(),
        })

    avg_temp = round(sum(temps) / len(temps), 1) if temps else 0
    avg_humidity = round(sum(humidities) / len(humidities)) if humidities else 0

    # Determine spray safety status
    spray_status, status_color, status_reason = _calculate_spray_status(
        max_rain_prob, max_wind_kmh
    )

    return {
        "location_name": f"{location_name}, {country}".strip(", "),
        "hourly_summary": hourly_summaries,
        "max_rain_prob_pct": round(max_rain_prob * 100),
        "max_wind_kmh": round(max_wind_kmh, 1),
        "temperature_c": avg_temp,
        "humidity_pct": avg_humidity,
        "spray_status": spray_status,
        "status_color": status_color,
        "status_reason": status_reason,
        "forecast_window_hours": len(intervals) * 3,
    }


def _calculate_spray_status(rain_prob: float, wind_kmh: float) -> tuple:
    """
    Apply precision agriculture spray safety rules.

    Returns:
        (status_text, color_code, reason_string)
    """
    # Rain takes priority (chemical efficacy and runoff)
    if rain_prob > RAIN_PROB_CAUTION or wind_kmh > WIND_CAUTION_KMH:
        return (
            "RED",
            "#FF3B30",
            (
                f"⛔ DO NOT SPRAY — "
                + (f"High rain probability: {round(rain_prob*100)}%"
                   if rain_prob > RAIN_PROB_CAUTION else "")
                + (" | " if rain_prob > RAIN_PROB_CAUTION and wind_kmh > WIND_CAUTION_KMH else "")
                + (f"Wind too high: {round(wind_kmh, 1)} km/h"
                   if wind_kmh > WIND_CAUTION_KMH else "")
            )
        )
    elif rain_prob > RAIN_PROB_SAFE or wind_kmh > WIND_SAFE_KMH:
        return (
            "YELLOW",
            "#FF9500",
            (
                f"⚠️ SPRAY WITH CAUTION — "
                + (f"Moderate rain probability: {round(rain_prob*100)}%"
                   if rain_prob > RAIN_PROB_SAFE else "")
                + (" | " if rain_prob > RAIN_PROB_SAFE and wind_kmh > WIND_SAFE_KMH else "")
                + (f"Moderate wind: {round(wind_kmh, 1)} km/h"
                   if wind_kmh > WIND_SAFE_KMH else "")
            )
        )
    else:
        return (
            "GREEN",
            "#34C759",
            (
                f"✅ SAFE TO SPRAY — "
                f"Rain probability: {round(rain_prob*100)}% | "
                f"Wind speed: {round(wind_kmh, 1)} km/h"
            )
        )


def _get_demo_weather(lat: float, lon: float) -> dict:
    """Demo weather data for testing without an API key."""
    return {
        "location_name": f"Field Location ({lat:.3f}, {lon:.3f})",
        "hourly_summary": [
            {"time": f"{h:02d}:00 UTC", "rain_prob_pct": 10, "wind_kmh": 8.5,
             "temp_c": 24.0, "humidity_pct": 62, "description": "Partly cloudy"}
            for h in range(0, 24, 3)
        ],
        "max_rain_prob_pct": 12,
        "max_wind_kmh": 9.2,
        "temperature_c": 24.0,
        "humidity_pct": 62,
        "spray_status": "GREEN",
        "status_color": "#34C759",
        "status_reason": "✅ SAFE TO SPRAY — Rain probability: 12% | Wind speed: 9.2 km/h",
        "forecast_window_hours": 24,
        "demo_mode": True,
    }