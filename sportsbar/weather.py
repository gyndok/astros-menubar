"""Ballpark weather from Open-Meteo."""

from __future__ import annotations

import logging

import requests

from .config import now_local


WEATHER_API_BASE = "https://api.open-meteo.com/v1/forecast"

# Ballpark coordinates for weather (lat, lon)
BALLPARK_COORDS = {
    108: (33.4455, -112.0667),   # Arizona Diamondbacks - Chase Field
    109: (33.7353, -84.3899),    # Atlanta Braves - Truist Park
    110: (39.2838, -76.6218),    # Baltimore Orioles - Camden Yards
    111: (42.3467, -71.0972),    # Boston Red Sox - Fenway Park
    112: (41.9484, -87.6553),    # Chicago Cubs - Wrigley Field
    113: (41.8299, -87.6338),    # Chicago White Sox - Guaranteed Rate Field
    114: (39.0974, -84.5082),    # Cincinnati Reds - Great American Ball Park
    115: (41.4958, -81.6853),    # Cleveland Guardians - Progressive Field
    116: (39.7561, -104.9942),   # Colorado Rockies - Coors Field
    117: (29.7573, -95.3555),    # Houston Astros - Minute Maid Park
    118: (39.0517, -94.4803),    # Kansas City Royals - Kauffman Stadium
    119: (34.0739, -118.2400),   # Los Angeles Dodgers - Dodger Stadium
    120: (25.7781, -80.2196),    # Miami Marlins - loanDepot park
    121: (43.0281, -87.9712),    # Milwaukee Brewers - American Family Field
    133: (38.5806, -121.5083),   # Oakland Athletics - Sutter Health Park (Sacramento)
    134: (40.4469, -80.0057),    # Pittsburgh Pirates - PNC Park
    135: (32.7076, -117.1570),   # San Diego Padres - Petco Park
    136: (47.5914, -122.3325),   # Seattle Mariners - T-Mobile Park
    137: (37.7786, -122.3893),   # San Francisco Giants - Oracle Park
    138: (38.6226, -90.1928),    # St. Louis Cardinals - Busch Stadium
    139: (27.7682, -82.6534),    # Tampa Bay Rays - Tropicana Field
    140: (32.7512, -97.0832),    # Texas Rangers - Globe Life Field
    141: (43.6414, -79.3894),    # Toronto Blue Jays - Rogers Centre
    142: (44.9818, -93.2775),    # Minnesota Twins - Target Field
    143: (38.8730, -77.0074),    # Washington Nationals - Nationals Park
    144: (33.8003, -117.8827),   # Los Angeles Angels - Angel Stadium
    145: (40.7527, -73.8458),    # New York Mets - Citi Field
    146: (42.3389, -83.0486),    # Detroit Tigers - Comerica Park
    147: (40.8296, -73.9262),    # New York Yankees - Yankee Stadium
}

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
    """Fetch current weather at the given team's ballpark."""
    coords = BALLPARK_COORDS.get(team_id)
    if not coords:
        return {}
    lat, lon = coords
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
