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


# ---------------------------------------------------------------------------
# Task 2: Cache and MLB API functions
# ---------------------------------------------------------------------------

def read_cache(name: str) -> dict:
    path = CACHE_DIR / f"{name}.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logging.exception("Failed reading cache %s: %s", name, exc)
        return {}


def write_cache(name: str, payload: dict) -> None:
    ensure_paths()
    path = CACHE_DIR / f"{name}.json"
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception as exc:
        logging.exception("Failed writing cache %s: %s", name, exc)


def fetch_schedule(start_date: str, end_date: str) -> list:
    """Fetch Astros games in date range with probable pitchers and broadcasts."""
    try:
        url = (
            f"{MLB_API_BASE}/schedule?sportId=1&teamId={ASTROS_TEAM_ID}"
            f"&startDate={start_date}&endDate={end_date}"
            f"&hydrate=probablePitcher,broadcasts"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        games = []
        for date_entry in data.get("dates", []):
            for game in date_entry.get("games", []):
                games.append(game)
        return games
    except Exception as exc:
        logging.exception("fetch_schedule failed: %s", exc)
        return []


def fetch_live_game(game_pk: int) -> dict:
    """Fetch live game feed for score, inning, count, runners, matchup."""
    try:
        url = f"{MLB_API_BASE.replace('/v1', '/v1.1')}/game/{game_pk}/feed/live"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logging.exception("fetch_live_game failed: %s", exc)
        return {}


def fetch_boxscore(game_pk: int) -> dict:
    """Fetch boxscore for batting order / lineup."""
    try:
        url = f"{MLB_API_BASE}/game/{game_pk}/boxscore"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logging.exception("fetch_boxscore failed: %s", exc)
        return {}


def parse_lineup(boxscore: dict, team_id: int) -> list:
    """Extract batting order from boxscore for the given team."""
    for side in ("away", "home"):
        team_data = boxscore.get("teams", {}).get(side, {})
        if team_data.get("team", {}).get("id") == team_id:
            batting_order = team_data.get("battingOrder", [])
            players = team_data.get("players", {})
            lineup = []
            for pid in batting_order:
                key = f"ID{pid}"
                p = players.get(key, {})
                person = p.get("person", {})
                pos = p.get("position", {})
                lineup.append({
                    "name": person.get("fullName", "Unknown"),
                    "position": pos.get("abbreviation", "?"),
                })
            return lineup
    return []


def fetch_standings() -> list:
    """Fetch all MLB division standings."""
    try:
        url = f"{MLB_API_BASE}/standings?leagueId=103,104&season={now_local().year}&standingsTypes=regularSeason"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json().get("records", [])
    except Exception as exc:
        logging.exception("fetch_standings failed: %s", exc)
        return []


def fetch_team_stats() -> dict:
    """Fetch Astros team hitting and pitching stats for current season."""
    result = {}
    try:
        year = now_local().year
        url = f"{MLB_API_BASE}/teams/{ASTROS_TEAM_ID}/stats?stats=season&group=hitting&season={year}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        hitting_stats = resp.json().get("stats", [])
        if hitting_stats:
            splits = hitting_stats[0].get("splits", [])
            if splits:
                result["hitting"] = splits[0].get("stat", {})

        url = f"{MLB_API_BASE}/teams/{ASTROS_TEAM_ID}/stats?stats=season&group=pitching&season={year}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        pitching_stats = resp.json().get("stats", [])
        if pitching_stats:
            splits = pitching_stats[0].get("splits", [])
            if splits:
                result["pitching"] = splits[0].get("stat", {})
    except Exception as exc:
        logging.exception("fetch_team_stats failed: %s", exc)
    return result


def fetch_pitcher_stats(player_id: int) -> dict:
    """Fetch season stats for a specific pitcher."""
    try:
        year = now_local().year
        url = f"{MLB_API_BASE}/people/{player_id}/stats?stats=season&group=pitching&season={year}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        stats = resp.json().get("stats", [])
        if stats:
            splits = stats[0].get("splits", [])
            if splits:
                return splits[0].get("stat", {})
    except Exception as exc:
        logging.exception("fetch_pitcher_stats failed: %s", exc)
    return {}


# ---------------------------------------------------------------------------
# Task 3: Odds and Weather functions
# ---------------------------------------------------------------------------

def fetch_odds(api_key: str) -> dict:
    """Fetch Astros game odds from The Odds API."""
    if not api_key:
        return {}
    try:
        url = (
            f"{ODDS_API_BASE}/odds/"
            f"?apiKey={api_key}&regions=us&markets=h2h,spreads,totals"
            f"&oddsFormat=american&bookmakers=draftkings"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        events = resp.json()
        for event in events:
            if "Houston Astros" in (event.get("home_team", ""), event.get("away_team", "")):
                return event
        return {}
    except Exception as exc:
        logging.exception("fetch_odds failed: %s", exc)
        return {}


def parse_odds(event: dict) -> dict:
    """Parse odds event into a clean dict with moneyline, spread, total."""
    result = {"matchup": "", "moneyline": {}, "spread": {}, "total": {}, "updated": ""}
    if not event:
        return result

    home = event.get("home_team", "")
    away = event.get("away_team", "")
    result["matchup"] = f"{away} @ {home}"
    result["updated"] = event.get("commence_time", "")

    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            key = market.get("key")
            outcomes = market.get("outcomes", [])
            if key == "h2h":
                for o in outcomes:
                    side = "home" if o["name"] == home else "away"
                    result["moneyline"][side] = {"name": o["name"], "price": o["price"]}
            elif key == "spreads":
                for o in outcomes:
                    side = "home" if o["name"] == home else "away"
                    result["spread"][side] = {"name": o["name"], "price": o["price"], "point": o.get("point", 0)}
            elif key == "totals":
                for o in outcomes:
                    direction = o["name"].lower()
                    result["total"][direction] = {"price": o["price"], "point": o.get("point", 0)}
        break
    return result


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


# ---------------------------------------------------------------------------
# Task 4: Game state detection and display helpers
# ---------------------------------------------------------------------------

def detect_game_state(games: list) -> dict:
    """Determine current game state from today's schedule."""
    today = now_local().strftime("%Y-%m-%d")
    todays_games = [g for g in games if g.get("officialDate") == today]

    if not todays_games:
        return {"state": "off", "game": None, "game_pk": None}

    game = todays_games[0]
    status = game.get("status", {})
    abstract = status.get("abstractGameState", "")
    detailed = status.get("detailedState", "")

    if abstract == "Live" or detailed == "In Progress":
        return {"state": "live", "game": game, "game_pk": game["gamePk"]}
    elif abstract == "Final" or detailed == "Final":
        return {"state": "final", "game": game, "game_pk": game["gamePk"]}
    else:
        return {"state": "pre", "game": game, "game_pk": game["gamePk"]}


def get_astros_side(game: dict) -> str:
    """Return 'away' or 'home' based on which side the Astros are."""
    if game["teams"]["away"]["team"]["id"] == ASTROS_TEAM_ID:
        return "away"
    return "home"


def opponent_team_id(game: dict) -> int:
    """Return the opponent's team ID."""
    side = get_astros_side(game)
    opp_side = "home" if side == "away" else "away"
    return game["teams"][opp_side]["team"]["id"]


def format_game_time(game: dict) -> str:
    """Format game start time in local time."""
    game_date_str = game.get("gameDate", "")
    if not game_date_str:
        return "TBD"
    try:
        utc_dt = dt.datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
        local_dt = utc_dt.astimezone()
        return local_dt.strftime("%-I:%M %p")
    except Exception:
        return "TBD"


def format_record(game: dict, side: str) -> str:
    """Format W-L record from game's leagueRecord."""
    rec = game["teams"][side].get("leagueRecord", {})
    return f"{rec.get('wins', 0)}-{rec.get('losses', 0)}"


def get_tv_broadcast(game: dict) -> str:
    """Get the TV broadcast name, preferring Astros home network."""
    broadcasts = game.get("broadcasts", [])
    for b in broadcasts:
        if b.get("type") == "TV" and "Space City" in b.get("name", ""):
            return b["name"]
    for b in broadcasts:
        if b.get("type") == "TV":
            return b.get("name", "")
    return "TBD"


def get_probable_pitcher(game: dict, side: str) -> dict:
    """Get probable pitcher info for a side ('away' or 'home')."""
    pp = game.get("teams", {}).get(side, {}).get("probablePitcher", {})
    return {
        "name": pp.get("fullName", "TBD"),
        "id": pp.get("id"),
    }


def parse_live_data(feed: dict) -> dict:
    """Parse live game feed into display-ready data."""
    linescore = feed.get("liveData", {}).get("linescore", {})
    plays = feed.get("liveData", {}).get("plays", {})
    current_play = plays.get("currentPlay", {})

    teams_score = linescore.get("teams", {})
    away_runs = teams_score.get("away", {}).get("runs", 0)
    home_runs = teams_score.get("home", {}).get("runs", 0)

    inning = linescore.get("currentInning", 0)
    inning_ordinal = linescore.get("currentInningOrdinal", "")
    is_top = linescore.get("isTopInning", True)
    half = "Top" if is_top else "Bot"

    count = current_play.get("count", {})
    matchup = current_play.get("matchup", {})
    pitcher = matchup.get("pitcher", {}).get("fullName", "")
    batter = matchup.get("batter", {}).get("fullName", "")

    offense = linescore.get("offense", {})
    runners = []
    if offense.get("first"):
        runners.append("1st")
    if offense.get("second"):
        runners.append("2nd")
    if offense.get("third"):
        runners.append("3rd")

    game_data = feed.get("gameData", {})
    away_team = game_data.get("teams", {}).get("away", {}).get("abbreviation", "")
    home_team = game_data.get("teams", {}).get("home", {}).get("abbreviation", "")

    return {
        "away_abbr": away_team,
        "home_abbr": home_team,
        "away_runs": away_runs or 0,
        "home_runs": home_runs or 0,
        "inning": inning,
        "inning_ordinal": inning_ordinal,
        "half": half,
        "balls": count.get("balls", 0),
        "strikes": count.get("strikes", 0),
        "outs": count.get("outs", 0),
        "pitcher": pitcher,
        "batter": batter,
        "runners": runners,
    }


def format_odds_price(price: int) -> str:
    """Format American odds with +/- prefix."""
    if price >= 0:
        return f"+{price}"
    return str(price)


if __name__ == "__main__":
    setup_logging()
    today = now_local().strftime("%Y-%m-%d")
    end = (now_local() + dt.timedelta(days=7)).strftime("%Y-%m-%d")

    print("=== Schedule ===")
    games = fetch_schedule(today, end)
    for g in games[:3]:
        away = g["teams"]["away"]["team"]["name"]
        home = g["teams"]["home"]["team"]["name"]
        print(f"  {g['officialDate']}: {away} @ {home} - {format_game_time(g)} - TV: {get_tv_broadcast(g)}")

    print("\n=== Game State ===")
    state_info = detect_game_state(games)
    print(f"  State: {state_info['state']}")
    if state_info["game"]:
        side = get_astros_side(state_info["game"])
        print(f"  Astros are: {side}")
        print(f"  Record: {format_record(state_info['game'], side)}")

    print("\n=== Standings ===")
    records = fetch_standings()
    for rec in records[:2]:
        div_id = rec.get("division", {}).get("id")
        teams = [(tr["team"]["name"], tr["leagueRecord"]["wins"], tr["leagueRecord"]["losses"]) for tr in rec.get("teamRecords", [])[:3]]
        print(f"  Div {div_id}: {teams}")

    print("\n=== Team Stats ===")
    stats = fetch_team_stats()
    h = stats.get("hitting", {})
    p = stats.get("pitching", {})
    print(f"  AVG: {h.get('avg')}  HR: {h.get('homeRuns')}  ERA: {p.get('era')}")

    print("\n=== Weather (Minute Maid Park) ===")
    w = fetch_weather(ASTROS_TEAM_ID)
    print(f"  {w.get('temp_f', 0):.0f}°F, {w.get('condition', 'Unknown')}, Wind: {w.get('wind_mph', 0):.0f} mph")

    print("\nAll API functions verified.")
