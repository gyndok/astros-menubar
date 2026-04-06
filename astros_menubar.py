#!/usr/bin/env python3
"""
Houston Astros Menu Bar App.

Follow the Astros all season from your macOS menu bar.
Built with rumps for macOS menubar display.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import rumps
import yaml

APP_NAME = "Astros Menu Bar"
CONFIG_DIR = Path.home() / ".config" / "astros-menubar"
CONFIG_PATH = CONFIG_DIR / "config.yaml"
CACHE_DIR = CONFIG_DIR / "cache"
LOG_PATH = CONFIG_DIR / "app.log"

ASTROS_TEAM_ID = 117
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports/baseball_mlb"
WEATHER_API_BASE = "https://api.open-meteo.com/v1/forecast"

# Division IDs
DIVISIONS = {
    "AL East": 201,
    "AL Central": 202,
    "AL West": 200,
    "NL East": 204,
    "NL Central": 205,
    "NL West": 203,
}

# League IDs
LEAGUES = {
    "American League": 103,
    "National League": 104,
}

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
    134: (40.8296, -73.9262),    # Pittsburgh Pirates - PNC Park
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

DEFAULT_CONFIG = {
    "odds_api_key": "",
    "notifications": {
        "game_starting": True,
        "final_score": True,
        "scoring_plays": False,
        "lineup_posted": False,
    },
    "show_odds": True,
    "show_weather": True,
    "quick_links": [
        {"name": "Astros.com", "url": "https://www.mlb.com/astros"},
        {"name": "MLB.tv", "url": "https://www.mlb.com/tv"},
        {"name": "Space City Home Network", "url": "https://www.spacecityhomenetwork.com"},
        {"name": "r/Astros", "url": "https://www.reddit.com/r/Astros/"},
        {"name": "Astros on X", "url": "https://x.com/astros"},
    ],
}


def ensure_paths() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_paths()
    if not CONFIG_PATH.exists():
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            yaml.safe_dump(DEFAULT_CONFIG, f, sort_keys=False)
        return DEFAULT_CONFIG.copy()
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    merged = DEFAULT_CONFIG.copy()
    merged.update(loaded)
    if not isinstance(merged.get("notifications"), dict):
        merged["notifications"] = DEFAULT_CONFIG["notifications"]
    if not isinstance(merged.get("quick_links"), list):
        merged["quick_links"] = DEFAULT_CONFIG["quick_links"]
    return merged


def setup_logging() -> None:
    ensure_paths()
    logging.basicConfig(
        filename=str(LOG_PATH),
        filemode="a",
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def to_fahrenheit(celsius: float) -> float:
    return (celsius * 9.0 / 5.0) + 32.0


def now_local() -> dt.datetime:
    return dt.datetime.now()


if __name__ == "__main__":
    setup_logging()
    print("Astros Menu Bar skeleton loaded.")
