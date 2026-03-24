"""Open-Meteo weather integration. Free, no API key needed."""

from datetime import date, time, datetime, timedelta, timezone
import requests
from models import db, WeatherForecast, WeatherHourly


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_and_store_weather(lat: float, lon: float) -> dict:
    """Fetch 7-day daily + 48-hour hourly forecast and store in DB."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
            "precipitation_sum",
            "wind_speed_10m_max",
            "weather_code",
            "sunrise",
            "sunset",
        ]),
        "hourly": ",".join([
            "temperature_2m",
            "precipitation_probability",
            "precipitation",
            "wind_speed_10m",
            "weather_code",
        ]),
        "timezone": "auto",
        "forecast_days": 7,
        "forecast_hours": 48,
    }

    resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    tz_name = data.get("timezone", "auto")

    # --- Daily ---
    daily = data["daily"]
    daily_results = []

    for i, date_str in enumerate(daily["time"]):
        forecast_date = date.fromisoformat(date_str)

        existing = WeatherForecast.query.filter_by(date=forecast_date).first()
        if not existing:
            existing = WeatherForecast(date=forecast_date)
            db.session.add(existing)

        existing.temp_max = daily["temperature_2m_max"][i]
        existing.temp_min = daily["temperature_2m_min"][i]
        existing.precipitation_probability = daily["precipitation_probability_max"][i]
        existing.precipitation_mm = daily["precipitation_sum"][i]
        existing.wind_speed_max = daily["wind_speed_10m_max"][i]
        existing.weather_code = daily["weather_code"][i]
        existing.fetched_at = datetime.utcnow()

        if daily["sunrise"][i]:
            existing.sunrise = datetime.fromisoformat(daily["sunrise"][i]).time()
        if daily["sunset"][i]:
            existing.sunset = datetime.fromisoformat(daily["sunset"][i]).time()

        existing.run_score = _calculate_run_score(
            existing.temp_max,
            existing.precipitation_probability,
            existing.wind_speed_max,
        )
        daily_results.append(existing.to_dict())

    # --- Hourly (48 hours) ---
    hourly = data.get("hourly", {})
    hourly_results = []

    if hourly and "time" in hourly:
        for i, time_str in enumerate(hourly["time"]):
            dt_local = datetime.fromisoformat(time_str)
            # Use local time as-is since Open-Meteo returns in requested timezone
            dt_utc = dt_local  # approximate — good enough for planning

            existing = WeatherHourly.query.filter_by(datetime_local=dt_local).first()
            if not existing:
                existing = WeatherHourly(datetime_utc=dt_utc, datetime_local=dt_local)
                db.session.add(existing)

            existing.temperature = hourly["temperature_2m"][i]
            existing.precipitation_probability = hourly["precipitation_probability"][i]
            existing.precipitation_mm = hourly["precipitation"][i]
            existing.wind_speed = hourly["wind_speed_10m"][i]
            existing.weather_code = hourly["weather_code"][i]
            existing.fetched_at = datetime.utcnow()

            hourly_results.append(existing.to_dict())

    db.session.commit()
    return {"daily": daily_results, "hourly": hourly_results, "timezone": tz_name}


def _calculate_run_score(temp_max, precip_prob, wind_max) -> int:
    """Simple heuristic for how good a day is for outdoor running.

    100 = perfect, 0 = terrible. Not science, just useful.
    """
    score = 100

    # Temperature penalty (ideal: 8-18°C)
    if temp_max is not None:
        if temp_max < 2:
            score -= 30
        elif temp_max < 8:
            score -= 10
        elif temp_max > 28:
            score -= 30
        elif temp_max > 22:
            score -= 10

    # Rain penalty
    if precip_prob is not None:
        if precip_prob > 80:
            score -= 40
        elif precip_prob > 50:
            score -= 20
        elif precip_prob > 30:
            score -= 10

    # Wind penalty
    if wind_max is not None:
        if wind_max > 40:
            score -= 25
        elif wind_max > 25:
            score -= 10

    return max(0, min(100, score))
