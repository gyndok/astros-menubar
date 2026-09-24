"""Ballpark weather from Open-Meteo."""

from __future__ import annotations

import logging

import requests

from .config import now_local
from .teams import MLB_BY_ID


WEATHER_API_BASE = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow",
    80: "Rain showers", 81: "Rain showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm + hail", 99: "Severe thunderstorm",
}


def to_fahrenheit(celsius: float) -> float:
    return (celsius * 9.0 / 5.0) + 32.0


def fetch_weather(team_id: int) -> dict:
    """Fetch current weather at the given MLB team's ballpark."""
    team = MLB_BY_ID.get(team_id)
    if team is None:
        return {}
    lat, lon = team.lat, team.lon
    try:
        url = (
            f"{WEATHER_API_BASE}"
            f"?latitude={lat}&longitude={lon}&current_weather=true"
            f"&daily=temperature_2m_max,temperature_2m_min&timezone=auto"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        cw = data.get("current_weather", {})
        daily = data.get("daily", {})
        return {
            "temp_c": float(cw.get("temperature", 0)),
            "temp_f": to_fahrenheit(float(cw.get("temperature", 0))),
            "code": int(cw.get("weathercode", 0)),
            "wind_kmh": float(cw.get("windspeed", 0)),
            "wind_mph": float(cw.get("windspeed", 0)) * 0.621371,
            "max_c": float(daily.get("temperature_2m_max", [0])[0]),
            "min_c": float(daily.get("temperature_2m_min", [0])[0]),
            "max_f": to_fahrenheit(float(daily.get("temperature_2m_max", [0])[0])),
            "min_f": to_fahrenheit(float(daily.get("temperature_2m_min", [0])[0])),
            "condition": WEATHER_CODES.get(int(cw.get("weathercode", 0)), "Unknown"),
            "updated": now_local().isoformat(timespec="minutes"),
        }
    except Exception as exc:
        logging.exception("fetch_weather failed: %s", exc)
        return {}
