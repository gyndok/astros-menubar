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
import random
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


LAUNCH_AGENT_LABEL = "com.gyndok.astros-menubar"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def install_launch_agent() -> None:
    """Auto-install LaunchAgent on first run so the app starts on login."""
    if LAUNCH_AGENT_PATH.exists():
        return
    # Determine the executable — if running from a .app bundle, use the
    # bundle's executable; otherwise use the script path directly.
    import sys
    executable = sys.executable
    script = str(Path(__file__).resolve())

    # If inside a .app bundle, the executable IS the app
    if ".app/Contents" in executable:
        program_args = f"<string>{executable}</string>"
    else:
        program_args = f"<string>{executable}</string>\n        <string>{script}</string>"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCH_AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        {program_args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{CONFIG_DIR / "stdout.log"}</string>
    <key>StandardErrorPath</key>
    <string>{CONFIG_DIR / "stderr.log"}</string>
</dict>
</plist>
"""
    try:
        LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAUNCH_AGENT_PATH.write_text(plist_content)
        subprocess.run(["launchctl", "load", str(LAUNCH_AGENT_PATH)], check=False)
        logging.info("LaunchAgent installed at %s", LAUNCH_AGENT_PATH)
    except Exception as exc:
        logging.exception("Failed to install LaunchAgent: %s", exc)


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


AL_DIVISION_IDS = {200, 201, 202}


def flatten_league_teams(standings: list, division_ids: set) -> list:
    """Flatten standings records into one list of team dicts for a league."""
    teams = []
    for record in standings:
        div_id = record.get("division", {}).get("id")
        if div_id not in division_ids:
            continue
        for tr in record.get("teamRecords", []):
            rec = tr.get("leagueRecord", {})
            teams.append({
                "id": tr.get("team", {}).get("id"),
                "name": tr.get("team", {}).get("name", "?"),
                "wins": int(rec.get("wins", 0)),
                "losses": int(rec.get("losses", 0)),
                "div_id": div_id,
                "games_back": tr.get("gamesBack", "-"),
                "league_rank": tr.get("leagueRank", ""),
                "magic_number": tr.get("magicNumber"),
                "elimination_number": tr.get("eliminationNumber"),
                "wc_elimination_number": tr.get("wildCardEliminationNumber"),
                "clinched": bool(tr.get("clinched", False)),
                "division_champ": bool(tr.get("divisionChamp", False)),
                "division_leader": bool(tr.get("divisionLeader", False)),
            })
    return teams


def magic_number_vs(team_wins: int, rival_losses: int) -> int:
    """Wins + rival losses still needed to guarantee finishing ahead of rival.

    Standard formula: 162 + 1 - W_team - L_rival, floored at 0.
    """
    return max(0, 163 - team_wins - rival_losses)


def compute_magic_numbers(standings: list) -> dict:
    """Compute Astros magic numbers from standings data.

    Returns division / playoff-berth / wild-card / #1-seed magic numbers.
    All numbers ignore tiebreakers (same convention as published numbers).
    The rival for each race is the relevant team with the fewest losses:
      - division: fewest losses among other AL West teams
      - playoffs (6 AL spots): 6th-fewest losses among the other 14 AL teams
      - wild card (3 spots): 4th-fewest losses among non-division-leaders
      - #1 seed: fewest losses among all other AL teams
    """
    teams = flatten_league_teams(standings, AL_DIVISION_IDS)
    astros = next((t for t in teams if t["id"] == ASTROS_TEAM_ID), None)
    if not astros:
        return {}
    others = [t for t in teams if t["id"] != ASTROS_TEAM_ID]
    if not others:
        return {}
    wins = astros["wins"]

    result = {
        "wins": wins,
        "losses": astros["losses"],
        "remaining": max(0, 162 - wins - astros["losses"]),
        "games_back": astros["games_back"],
        "league_rank": str(astros.get("league_rank", "")),
        "division_leader": astros["division_leader"],
        "division_champ": astros["division_champ"],
        "clinched_postseason": astros["clinched"],
        "division_eliminated": astros.get("elimination_number") == "E",
        "wc_eliminated": astros.get("wc_elimination_number") == "E",
    }

    # Division: prefer MLB's published magic number when present
    division_mn = None
    api_mn = astros.get("magic_number")
    if api_mn not in (None, "", "-"):
        try:
            division_mn = int(api_mn)
        except (TypeError, ValueError):
            division_mn = None
    div_rivals = [t for t in others if t["div_id"] == astros["div_id"]]
    if division_mn is None and div_rivals:
        division_mn = magic_number_vs(wins, min(t["losses"] for t in div_rivals))
    result["division"] = division_mn if division_mn is not None else 0

    # Playoff berth: hold off all but 5 other AL teams (6 total spots)
    all_losses = sorted(t["losses"] for t in others)
    result["playoffs"] = magic_number_vs(wins, all_losses[5]) if len(all_losses) > 5 else 0

    # Wild card: 3 spots among teams not leading their division
    non_leader_losses = sorted(
        t["losses"] for t in others if not t["division_leader"]
    )
    result["wild_card"] = (
        magic_number_vs(wins, non_leader_losses[3]) if len(non_leader_losses) > 3 else 0
    )

    # #1 AL seed: finish ahead of every other AL team
    result["top_seed"] = magic_number_vs(wins, all_losses[0])

    return result


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
        # Don't log the raw exception — request URLs embed the API key.
        logging.error("fetch_odds failed: %s", str(exc).replace(api_key, "***"))
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

def _game_status(game: dict) -> str:
    """Classify a single game as 'live', 'final', or 'pre'."""
    status = game.get("status", {})
    abstract = status.get("abstractGameState", "")
    detailed = status.get("detailedState", "")
    if abstract == "Live" or detailed == "In Progress":
        return "live"
    if abstract == "Final" or detailed == "Final":
        return "final"
    return "pre"


def detect_game_state(games: list) -> dict:
    """Determine current game state from today's schedule.

    Doubleheader-aware: prefer a live game, then the next un-played game,
    otherwise the last final. Postponed/cancelled games are ignored (they
    report abstractGameState 'Final' and would show a bogus 0-0 final).
    """
    today = now_local().strftime("%Y-%m-%d")
    todays_games = [
        g for g in games
        if g.get("officialDate") == today
        and g.get("status", {}).get("detailedState", "") not in
        ("Postponed", "Cancelled", "Suspended")
    ]

    if not todays_games:
        return {"state": "off", "game": None, "game_pk": None}

    for game in todays_games:
        if _game_status(game) == "live":
            return {"state": "live", "game": game, "game_pk": game["gamePk"]}
    for game in todays_games:
        if _game_status(game) == "pre":
            return {"state": "pre", "game": game, "game_pk": game["gamePk"]}
    game = todays_games[-1]
    return {"state": "final", "game": game, "game_pk": game["gamePk"]}


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


def generate_game_text(game_state: dict, live_data: dict, schedule_data: list) -> str:
    """Generate a witty, situational text message about the current Astros game."""
    state = game_state.get("state", "off")
    game = game_state.get("game")

    if state == "off" or not game:
        # Off day
        today = dt.datetime.now().strftime("%Y-%m-%d")
        next_game = next(
            (g for g in schedule_data if g.get("officialDate", "") > today), None
        )
        off_day_msgs = [
            "No Astros today. What am I supposed to do with my evening?",
            "Off day. Guess I'll just stare at my Altuve jersey.",
            "No game today. The Astros are resting. I am not.",
            "Day off for the boys. My blood pressure thanks them.",
        ]
        msg = random.choice(off_day_msgs)
        if next_game:
            opp_side = "home" if get_astros_side(next_game) == "away" else "away"
            opp = next_game["teams"][opp_side]["team"]["name"]
            msg += f" Next up: {opp}."
        return msg

    side = get_astros_side(game)
    opp_side = "home" if side == "away" else "away"
    opp_name = game["teams"][opp_side]["team"]["name"].split()[-1]

    if state == "pre":
        time_str = format_game_time(game)
        sp = get_probable_pitcher(game, side)
        pre_msgs = [
            f"Stros vs {opp_name} at {time_str}. {sp['name']} on the bump. Let's ride. 🤘",
            f"{sp['name']} dealing tonight against the {opp_name}. First pitch {time_str}. LFG!",
            f"Game day! {opp_name} have no idea what's coming. {time_str} CT. ⚾",
            f"It's {sp['name']} day. Stros vs {opp_name} at {time_str}. Shoot it! 🚀",
            f"Tonight: Astros. {opp_name}. {time_str}. {sp['name']} vs the world.",
        ]
        return random.choice(pre_msgs)

    if state == "final":
        a_score = game["teams"][side].get("score", 0) or 0
        o_score = game["teams"][opp_side].get("score", 0) or 0
        if a_score == o_score:
            return f"Final: Astros {a_score}, {opp_name} {o_score}. A tie?? In baseball?? What year is it."
        if a_score > o_score:
            win_msgs = [
                f"Astros {a_score}, {opp_name} {o_score}. SHOOT IT HOUSTON TEXAS! 🚀🤘",
                f"W. {a_score}-{o_score} over the {opp_name}. Good guys win again.",
                f"Stros take it {a_score}-{o_score}! {opp_name} in shambles. 😤",
                f"FINAL: Astros {a_score}, {opp_name} {o_score}. Go ahead and play the train horn. 🚂",
                f"Another one. Astros {a_score}, {opp_name} {o_score}. This team is different. 🔥",
            ]
            return random.choice(win_msgs)
        else:
            loss_msgs = [
                f"Astros {a_score}, {opp_name} {o_score}. We don't talk about this one.",
                f"L. {a_score}-{o_score} to the {opp_name}. Delete this from the record books.",
                f"Final: {a_score}-{o_score}. The {opp_name} got lucky. That's my story.",
                f"Stros fall {a_score}-{o_score}. Tomorrow we choose violence. 😤",
                f"Not our night. {a_score}-{o_score}. But 162 games is a marathon not a sprint.",
            ]
            return random.choice(loss_msgs)

    # Live game
    if not live_data:
        return f"Stros vs {opp_name} — game is live but I'm still loading. Hold tight."

    astros_runs = live_data.get(f"{side}_runs", 0)
    opp_runs = live_data.get(f"{opp_side}_runs", 0)
    inning = live_data.get("inning_ordinal", "")
    half = live_data.get("half", "")
    pitcher = live_data.get("pitcher", "someone")
    batter = live_data.get("batter", "someone")
    runners = live_data.get("runners", [])
    outs = live_data.get("outs", 0)
    diff = astros_runs - opp_runs

    if diff > 4:
        blowout_msgs = [
            f"Astros {astros_runs}, {opp_name} {opp_runs} in the {half} {inning}. This is a clinic. 🏥",
            f"{astros_runs}-{opp_runs} Stros. {opp_name} need to call their therapist.",
            f"Astros up {astros_runs}-{opp_runs}. I almost feel bad. Almost. 😏",
            f"It's {astros_runs}-{opp_runs} in the {inning}. {opp_name} already booking flights home.",
        ]
        return random.choice(blowout_msgs)

    if diff > 0:
        leading_msgs = [
            f"Astros {astros_runs}, {opp_name} {opp_runs}. {half} {inning}. We're cooking. 🔥",
            f"Stros up {astros_runs}-{opp_runs} in the {inning}. Keep it rolling boys!",
            f"{astros_runs}-{opp_runs} Astros, {half} {inning}. {batter} at the plate. Let's add on.",
            f"Leading {astros_runs}-{opp_runs} in the {inning}. Vibes are immaculate. ✨",
        ]
        return random.choice(leading_msgs)

    if diff == 0:
        tied_msgs = [
            f"Tied {astros_runs}-{opp_runs} in the {half} {inning}. Someone needs to be a hero.",
            f"All knotted up {astros_runs}-{opp_runs}, {half} {inning}. Clench time. 😬",
            f"{astros_runs}-{opp_runs} tie game in the {inning}. This is why we watch baseball.",
            f"Tied at {astros_runs} in the {inning}. {batter} up. DO SOMETHING.",
        ]
        return random.choice(tied_msgs)

    if diff >= -2:
        close_trail_msgs = [
            f"Astros down {astros_runs}-{opp_runs} in the {half} {inning}. Not worried. Yet. 😅",
            f"{opp_runs}-{astros_runs} {opp_name}, {half} {inning}. Plenty of game left. Come on Stros!",
            f"Trailing {astros_runs}-{opp_runs} in the {inning}. This team knows how to come back. 💪",
            f"Down {opp_runs - astros_runs} in the {inning}. {batter} at the plate. Rally caps on! 🧢",
        ]
        return random.choice(close_trail_msgs)

    # Down big
    down_bad_msgs = [
        f"Astros {astros_runs}, {opp_name} {opp_runs} in the {inning}. This is fine. Everything is fine. 🔥🐶🔥",
        f"Down {astros_runs}-{opp_runs}. I'm not panicking, you're panicking.",
        f"{opp_runs}-{astros_runs} {opp_name} in the {inning}. Fade me. 💀",
        f"It's {astros_runs}-{opp_runs} and I'm choosing to believe in miracles.",
    ]
    return random.choice(down_bad_msgs)


# ---------------------------------------------------------------------------
# Tasks 5-9: AstrosMenuBarApp class
# ---------------------------------------------------------------------------

class AstrosMenuBarApp(rumps.App):
    """Houston Astros macOS menu bar application."""

    def __init__(self) -> None:
        super().__init__(APP_NAME, title="⚾")
        self.config = load_config()

        # Data caches
        self.schedule_data: list = []
        self.game_state: dict = {"state": "off", "game": None, "game_pk": None}
        self.live_data: dict = {}
        self.lineup_data: list = []
        self.standings_data: list = []
        self.odds_data: dict = {}
        self.weather_data: dict = {}
        self.team_stats: dict = {}
        self.previous_astros_score: Optional[int] = None
        self.final_revert_time: Optional[dt.datetime] = None
        self._did_initial_refresh: bool = False
        self._starting_soon_pk: Optional[int] = None  # dedup "starting soon" notification
        self._score_watch_pk: Optional[int] = None    # reset score tracking per game
        self.pitcher_stats_cache: Dict[int, dict] = {}

        # Load cached data from disk
        self.schedule_data = read_cache("schedule").get("games", [])
        self.standings_data = read_cache("standings").get("records", [])
        self.odds_data = read_cache("odds")
        self.weather_data = read_cache("weather")
        self.team_stats = read_cache("team_stats")

        self._build_menu()

        # Primary polling timer. Owned explicitly (rather than via the
        # @rumps.timer decorator) so refresh_primary can adapt its interval
        # to the game state.
        self.primary_timer = rumps.Timer(self.refresh_primary, 60)
        self.primary_timer.start()

    # ------------------------------------------------------------------
    # Menu construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        """Create all menu items."""
        # Top context-aware lines
        self.top_line_1 = rumps.MenuItem("—", callback=self._noop)
        self.top_line_2 = rumps.MenuItem("—", callback=self._noop)
        self.top_line_3 = rumps.MenuItem("—", callback=self._noop)
        self.top_line_4 = rumps.MenuItem("—", callback=self._noop)
        self.top_line_5 = rumps.MenuItem("—", callback=self._noop)

        # Today's Game submenu
        self.todays_game_menu = rumps.MenuItem("⚾ Today's Game")
        self.tg_line_1 = rumps.MenuItem("—", callback=self._noop)
        self.tg_line_2 = rumps.MenuItem("—", callback=self._noop)
        self.tg_line_3 = rumps.MenuItem("—", callback=self._noop)
        self.tg_line_4 = rumps.MenuItem("—", callback=self._noop)
        self.tg_line_5 = rumps.MenuItem("—", callback=self._noop)
        self.tg_line_6 = rumps.MenuItem("—", callback=self._noop)
        self.todays_game_menu.update([
            self.tg_line_1, self.tg_line_2, self.tg_line_3,
            self.tg_line_4, self.tg_line_5, self.tg_line_6,
        ])

        # Schedule submenu (placeholder seeds _menu so .clear() works later)
        self.schedule_menu = rumps.MenuItem("📅 Schedule")
        self.schedule_menu.update([rumps.MenuItem("Loading...")])

        # Lineup submenu
        self.lineup_menu = rumps.MenuItem("👥 Lineup")
        self.lineup_menu.update([rumps.MenuItem("Loading...")])

        # Rotation submenu
        self.rotation_menu = rumps.MenuItem("⚾ Starting Rotation")
        self.rotation_menu.update([rumps.MenuItem("Loading...")])

        # Standings submenu
        self.standings_menu = rumps.MenuItem("📊 Standings")
        self.standings_menu.update([rumps.MenuItem("Loading...")])

        # Magic Numbers submenu
        self.magic_menu = rumps.MenuItem("🔮 Magic Numbers")
        self.magic_menu.update([rumps.MenuItem("Loading...")])

        # Odds submenu
        self.odds_menu = rumps.MenuItem("💰 Vegas Odds")
        self.odds_menu.update([rumps.MenuItem("Loading...")])

        # Weather submenu
        self.weather_menu = rumps.MenuItem("🌤 Ballpark Weather")
        self.weather_menu.update([rumps.MenuItem("Loading...")])

        # Quick Links submenu
        self.links_menu = rumps.MenuItem("🔗 Quick Links")
        for link in self.config.get("quick_links", []):
            item = rumps.MenuItem(link["name"], callback=self.open_link)
            item._url = link["url"]
            self.links_menu.update([item])

        # Team Stats submenu
        self.stats_menu = rumps.MenuItem("📊 Team Stats")
        self.stats_menu.update([rumps.MenuItem("Loading...")])

        # Game Text generator
        self.game_text_item = rumps.MenuItem("💬 Game Text", callback=self.copy_game_text)

        # Refresh item
        self.refresh_item = rumps.MenuItem("🔄 Refresh Now", callback=self.manual_refresh)

        # Settings submenu
        self.settings_menu = rumps.MenuItem("⚙️ Settings")

        notif_menu = rumps.MenuItem("Notifications")
        self.notif_game_starting = rumps.MenuItem(
            "Game Starting Soon", callback=self.toggle_notification
        )
        self.notif_final_score = rumps.MenuItem(
            "Final Score", callback=self.toggle_notification
        )
        self.notif_scoring_plays = rumps.MenuItem(
            "Astros Scoring Plays", callback=self.toggle_notification
        )
        self.notif_lineup_posted = rumps.MenuItem(
            "Lineup Posted", callback=self.toggle_notification
        )
        notif_menu.update([
            self.notif_game_starting,
            self.notif_final_score,
            self.notif_scoring_plays,
            self.notif_lineup_posted,
        ])
        self._sync_notification_states()

        edit_config_item = rumps.MenuItem("Edit Config", callback=self.edit_config)
        quit_item = rumps.MenuItem("Quit", callback=self.quit_app)

        self.settings_menu.update([notif_menu, edit_config_item, quit_item])

        self.menu = [
            self.top_line_1,
            self.top_line_2,
            self.top_line_3,
            self.top_line_4,
            self.top_line_5,
            None,  # separator
            self.todays_game_menu,
            self.schedule_menu,
            self.lineup_menu,
            self.rotation_menu,
            None,  # separator
            self.standings_menu,
            self.magic_menu,
            self.odds_menu,
            self.weather_menu,
            None,  # separator
            self.links_menu,
            self.stats_menu,
            self.game_text_item,
            self.refresh_item,
            None,  # separator
            self.settings_menu,
        ]

    # ------------------------------------------------------------------
    # Notification helpers
    # ------------------------------------------------------------------

    def _sync_notification_states(self) -> None:
        """Read config and set .state on each notification menu item."""
        notifs = self.config.get("notifications", {})
        self.notif_game_starting.state = int(notifs.get("game_starting", True))
        self.notif_final_score.state = int(notifs.get("final_score", True))
        self.notif_scoring_plays.state = int(notifs.get("scoring_plays", False))
        self.notif_lineup_posted.state = int(notifs.get("lineup_posted", False))

    def toggle_notification(self, sender: rumps.MenuItem) -> None:
        """Toggle a notification preference on/off."""
        sender.state = not sender.state
        key_map = {
            "Game Starting Soon": "game_starting",
            "Final Score": "final_score",
            "Astros Scoring Plays": "scoring_plays",
            "Lineup Posted": "lineup_posted",
        }
        config_key = key_map.get(sender.title)
        if config_key:
            if not isinstance(self.config.get("notifications"), dict):
                self.config["notifications"] = {}
            self.config["notifications"][config_key] = bool(sender.state)
            ensure_paths()
            with CONFIG_PATH.open("w", encoding="utf-8") as f:
                yaml.safe_dump(self.config, f, sort_keys=False)

    # ------------------------------------------------------------------
    # Action callbacks
    # ------------------------------------------------------------------

    def open_link(self, sender: rumps.MenuItem) -> None:
        """Open sender._url in the default browser."""
        url = getattr(sender, "_url", None)
        if url:
            webbrowser.open(url)

    def edit_config(self, _sender: Any) -> None:
        """Open CONFIG_PATH with the default editor."""
        subprocess.Popen(["open", str(CONFIG_PATH)])

    def quit_app(self, _sender: Any) -> None:
        """Quit the application."""
        rumps.quit_application()

    @staticmethod
    def _noop(_sender: Any) -> None:
        """No-op callback so menu items render as enabled (not greyed out)."""
        pass

    def _item(self, title: str) -> rumps.MenuItem:
        """Create an info-only menu item that appears enabled."""
        return rumps.MenuItem(title, callback=self._noop)

    def copy_game_text(self, _sender: Any) -> None:
        """Generate a witty game text and copy to clipboard."""
        text = generate_game_text(self.game_state, self.live_data, self.schedule_data)
        try:
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            rumps.notification(APP_NAME, "Game Text Copied! 📋", text)
        except Exception as exc:
            logging.exception("copy_game_text failed: %s", exc)

    def manual_refresh(self, _sender: Any) -> None:
        """Trigger a full refresh, reloading config from disk."""
        self.config = load_config()
        self.refresh_all(None)

    def send_notification(self, title: str, message: str) -> None:
        """Send a macOS notification."""
        rumps.notification(APP_NAME, title, message)

    # ------------------------------------------------------------------
    # Title / top section updates
    # ------------------------------------------------------------------

    def update_title(self) -> None:
        """Set menu bar icon based on game state."""
        state = self.game_state.get("state", "off")
        if state == "live":
            game = self.game_state.get("game")
            if game and self.live_data:
                side = get_astros_side(game)
                ld = self.live_data
                astros_runs = ld.get(f"{side}_runs", 0)
                opp_side = "home" if side == "away" else "away"
                opp_runs = ld.get(f"{opp_side}_runs", 0)
                if astros_runs > opp_runs:
                    self.title = "⚾🟢"
                elif astros_runs < opp_runs:
                    self.title = "⚾🔴"
                else:
                    self.title = "⚾🟡"
            else:
                self.title = "⚾"
        elif state == "final":
            # Revert to plain ⚾ after 30 minutes
            if self.final_revert_time and now_local() >= self.final_revert_time:
                self.title = "⚾"
            else:
                game = self.game_state.get("game")
                if game:
                    side = get_astros_side(game)
                    teams = game.get("teams", {})
                    astros_score = teams.get(side, {}).get("score", 0) or 0
                    opp_side = "home" if side == "away" else "away"
                    opp_score = teams.get(opp_side, {}).get("score", 0) or 0
                    if astros_score > opp_score:
                        self.title = "⚾🟢"
                    elif astros_score < opp_score:
                        self.title = "⚾🔴"
                    else:
                        self.title = "⚾🟡"
                else:
                    self.title = "⚾"
        else:
            self.title = "⚾"

    def update_top_section(self) -> None:
        """Update the five context-aware lines at the top of the menu."""
        state = self.game_state.get("state", "off")
        game = self.game_state.get("game")
        lines = ["—", "—", "—", "—", "—"]

        if state == "live" and game and self.live_data:
            ld = self.live_data
            side = get_astros_side(game)
            opp_side = "home" if side == "away" else "away"
            away_abbr = ld.get("away_abbr", "AWY")
            home_abbr = ld.get("home_abbr", "HME")
            away_runs = ld.get("away_runs", 0)
            home_runs = ld.get("home_runs", 0)
            inning_ord = ld.get("inning_ordinal", "")
            half = ld.get("half", "")
            balls = ld.get("balls", 0)
            strikes = ld.get("strikes", 0)
            outs = ld.get("outs", 0)
            runners = ld.get("runners", [])
            pitcher = ld.get("pitcher", "")
            batter = ld.get("batter", "")
            tv = get_tv_broadcast(game)
            lines[0] = f"{away_abbr} {away_runs} — {home_abbr} {home_runs}  |  {half} {inning_ord}"
            lines[1] = f"Runners: {', '.join(runners) if runners else 'None'}  |  {balls}-{strikes}, {outs} out"
            lines[2] = f"P: {pitcher}  vs  B: {batter}"
            lines[3] = f"TV: {tv}"
            lines[4] = "—"

        elif state == "pre" and game:
            side = get_astros_side(game)
            opp_side = "home" if side == "away" else "away"
            opp_name = game["teams"][opp_side]["team"]["name"]
            game_time = format_game_time(game)
            at_symbol = "@" if side == "away" else "vs"
            astros_rec = format_record(game, side)
            opp_rec = format_record(game, opp_side)
            tv = get_tv_broadcast(game)
            astros_sp = get_probable_pitcher(game, side)
            opp_sp = get_probable_pitcher(game, opp_side)
            lines[0] = f"Astros {at_symbol} {opp_name}  |  {game_time}"
            lines[1] = f"HOU ({astros_rec}) vs {opp_name.split()[-1]} ({opp_rec})"
            lines[2] = f"SP: {astros_sp['name']} vs {opp_sp['name']}"
            lines[3] = f"TV: {tv}"
            lines[4] = "—"

        elif state == "final" and game:
            side = get_astros_side(game)
            opp_side = "home" if side == "away" else "away"
            teams = game.get("teams", {})
            astros_score = teams.get(side, {}).get("score", 0) or 0
            opp_score = teams.get(opp_side, {}).get("score", 0) or 0
            opp_name = game["teams"][opp_side]["team"]["name"]
            rec = format_record(game, side)
            result = "W" if astros_score > opp_score else ("L" if astros_score < opp_score else "T")
            lines[0] = f"FINAL: Astros {astros_score}, {opp_name.split()[-1]} {opp_score}  ({result})"
            lines[1] = f"Season: {rec}"
            lines[2] = "—"
            lines[3] = "—"
            lines[4] = "—"

        else:
            # Off day
            today = now_local().strftime("%Y-%m-%d")
            next_game = next(
                (g for g in self.schedule_data if g.get("officialDate", "") > today),
                None
            )
            lines[0] = "No game today"
            if next_game:
                nside = get_astros_side(next_game)
                nopp_side = "home" if nside == "away" else "away"
                nopp_name = next_game["teams"][nopp_side]["team"]["name"]
                ntime = format_game_time(next_game)
                nat_sym = "@" if nside == "away" else "vs"
                ndate = next_game.get("officialDate", "")
                lines[1] = f"Next: {ndate} {nat_sym} {nopp_name}  {ntime}"
            lines[2] = "—"
            lines[3] = "—"
            lines[4] = "—"

        items = [self.top_line_1, self.top_line_2, self.top_line_3, self.top_line_4, self.top_line_5]
        for item, text in zip(items, lines):
            item.title = text

    # ------------------------------------------------------------------
    # Submenu updates
    # ------------------------------------------------------------------

    def update_todays_game_menu(self) -> None:
        """Update the Today's Game submenu with detailed info."""
        state = self.game_state.get("state", "off")
        game = self.game_state.get("game")

        if state == "live":
            self.todays_game_menu.title = "⚾ Live Game"
        else:
            self.todays_game_menu.title = "⚾ Today's Game"

        lines = ["—", "—", "—", "—", "—", "—"]

        if state == "live" and game and self.live_data:
            ld = self.live_data
            side = get_astros_side(game)
            opp_side = "home" if side == "away" else "away"
            away_abbr = ld.get("away_abbr", "AWY")
            home_abbr = ld.get("home_abbr", "HME")
            away_runs = ld.get("away_runs", 0)
            home_runs = ld.get("home_runs", 0)
            inning_ord = ld.get("inning_ordinal", "")
            half = ld.get("half", "")
            balls = ld.get("balls", 0)
            strikes = ld.get("strikes", 0)
            outs = ld.get("outs", 0)
            runners = ld.get("runners", [])
            pitcher = ld.get("pitcher", "")
            batter = ld.get("batter", "")
            astros_rec = format_record(game, side)
            tv = get_tv_broadcast(game)
            lines[0] = f"{away_abbr} {away_runs} — {home_abbr} {home_runs}"
            lines[1] = f"{half} {inning_ord}  |  {balls}-{strikes}, {outs} out"
            lines[2] = f"Runners: {', '.join(runners) if runners else 'Bases empty'}"
            lines[3] = f"Pitching: {pitcher}  |  Batting: {batter}"
            lines[4] = f"Record: {astros_rec}"
            lines[5] = f"TV: {tv}"

        elif state == "pre" and game:
            side = get_astros_side(game)
            opp_side = "home" if side == "away" else "away"
            opp_name = game["teams"][opp_side]["team"]["name"]
            game_time = format_game_time(game)
            at_symbol = "@" if side == "away" else "vs"
            astros_rec = format_record(game, side)
            opp_rec = format_record(game, opp_side)
            astros_sp = get_probable_pitcher(game, side)
            opp_sp = get_probable_pitcher(game, opp_side)
            tv = get_tv_broadcast(game)
            venue = game.get("venue", {}).get("name", "")
            lines[0] = f"Astros {at_symbol} {opp_name}  |  {game_time}"
            lines[1] = f"HOU ({astros_rec}) vs {opp_name.split()[-1]} ({opp_rec})"
            lines[2] = f"SP — HOU: {astros_sp['name']}  vs  OPP: {opp_sp['name']}"
            lines[3] = f"Venue: {venue}"
            lines[4] = f"TV: {tv}"
            lines[5] = "—"

        elif state == "final" and game:
            side = get_astros_side(game)
            opp_side = "home" if side == "away" else "away"
            teams = game.get("teams", {})
            astros_score = teams.get(side, {}).get("score", 0) or 0
            opp_score = teams.get(opp_side, {}).get("score", 0) or 0
            opp_name = game["teams"][opp_side]["team"]["name"]
            rec = format_record(game, side)
            result = "W" if astros_score > opp_score else ("L" if astros_score < opp_score else "T")
            at_symbol = "@" if side == "away" else "vs"
            venue = game.get("venue", {}).get("name", "")
            lines[0] = f"FINAL: Astros {at_symbol} {opp_name}"
            lines[1] = f"Score: {astros_score} — {opp_score}  ({result})"
            lines[2] = f"Season Record: {rec}"
            lines[3] = f"Venue: {venue}"
            lines[4] = "—"
            lines[5] = "—"

        else:
            today = now_local().strftime("%Y-%m-%d")
            next_game = next(
                (g for g in self.schedule_data if g.get("officialDate", "") > today),
                None
            )
            lines[0] = "No game today"
            if next_game:
                nside = get_astros_side(next_game)
                nopp_side = "home" if nside == "away" else "away"
                nopp_name = next_game["teams"][nopp_side]["team"]["name"]
                ntime = format_game_time(next_game)
                nat_sym = "@" if nside == "away" else "vs"
                ndate = next_game.get("officialDate", "")
                nsp = get_probable_pitcher(next_game, nside)
                lines[1] = f"Next: {ndate}  {nat_sym} {nopp_name}  {ntime}"
                lines[2] = f"Probable SP: {nsp['name']}"
            lines[3] = "—"
            lines[4] = "—"
            lines[5] = "—"

        tg_items = [
            self.tg_line_1, self.tg_line_2, self.tg_line_3,
            self.tg_line_4, self.tg_line_5, self.tg_line_6,
        ]
        for item, text in zip(tg_items, lines):
            item.title = text

    def update_schedule_menu(self) -> None:
        """Populate the Schedule submenu with next 10 games."""
        today = now_local().strftime("%Y-%m-%d")
        upcoming = [g for g in self.schedule_data if g.get("officialDate", "") >= today]
        upcoming = upcoming[:10]

        self.schedule_menu.clear()

        for game in upcoming:
            side = get_astros_side(game)
            opp_side = "home" if side == "away" else "away"
            opp_name = game["teams"][opp_side]["team"]["name"]
            date_str = game.get("officialDate", "")
            gtime = format_game_time(game)
            at_sym = "@" if side == "away" else "vs"
            label = f"{date_str}  {at_sym} {opp_name}  {gtime}"

            game_item = rumps.MenuItem(label)
            sp_astros = get_probable_pitcher(game, side)
            sp_opp = get_probable_pitcher(game, opp_side)
            tv = get_tv_broadcast(game)
            game_item.update([
                rumps.MenuItem(f"SP: {sp_astros['name']} vs {sp_opp['name']}", callback=AstrosMenuBarApp._noop),
                rumps.MenuItem(f"TV: {tv}", callback=AstrosMenuBarApp._noop),
            ])
            self.schedule_menu.update([game_item])

        view_all = rumps.MenuItem("View Full Schedule...", callback=self.open_link)
        view_all._url = "https://www.mlb.com/astros/schedule"
        self.schedule_menu.update([None, view_all])

    def update_lineup_menu(self) -> None:
        """Show batting order 1-9 or a placeholder."""
        self.lineup_menu.clear()
        if not self.lineup_data:
            self.lineup_menu.update([rumps.MenuItem("Lineup not yet announced", callback=AstrosMenuBarApp._noop)])
            return
        for i, player in enumerate(self.lineup_data, start=1):
            self.lineup_menu.update([
                rumps.MenuItem(f"{i}. {player['name']} ({player['position']})", callback=AstrosMenuBarApp._noop)
            ])

    def update_rotation_menu(self) -> None:
        """Show probable pitchers from upcoming games with stats."""
        today = now_local().strftime("%Y-%m-%d")
        upcoming = [g for g in self.schedule_data if g.get("officialDate", "") >= today]

        seen_ids: set = set()
        pitchers: List[Dict[str, Any]] = []
        for game in upcoming:
            side = get_astros_side(game)
            sp = get_probable_pitcher(game, side)
            pid = sp.get("id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                pitchers.append({
                    "name": sp["name"],
                    "id": pid,
                    "date": game.get("officialDate", ""),
                })

        self.rotation_menu.clear()
        if not pitchers:
            self.rotation_menu.update([rumps.MenuItem("No rotation data available", callback=AstrosMenuBarApp._noop)])
            return

        for p in pitchers[:6]:
            stats = self.pitcher_stats_cache.get(p["id"], {})
            wins = stats.get("wins", 0)
            losses = stats.get("losses", 0)
            era = stats.get("era", "—")
            label = f"{p['name']} — Next: {p['date']} ({wins}-{losses}, {era} ERA)"
            self.rotation_menu.update([rumps.MenuItem(label, callback=AstrosMenuBarApp._noop)])

    def update_standings_menu(self) -> None:
        """Full drill-down standings: MLB > League > Division."""
        self.standings_menu.clear()
        if not self.standings_data:
            self.standings_menu.update([rumps.MenuItem("Standings unavailable", callback=AstrosMenuBarApp._noop)])
            return

        # Build division-id → records lookup
        div_lookup: Dict[int, list] = {}
        for record in self.standings_data:
            div_id = record.get("division", {}).get("id")
            if div_id is not None:
                div_lookup[div_id] = record.get("teamRecords", [])

        for league_name, league_id in LEAGUES.items():
            league_item = rumps.MenuItem(league_name)
            league_divs = {
                name: did for name, did in DIVISIONS.items()
                if (league_id == 103 and name.startswith("AL")) or
                   (league_id == 104 and name.startswith("NL"))
            }

            # Wild card — teams not in 1st place per division
            wc_teams: List[Dict[str, Any]] = []

            for div_name, div_id in sorted(league_divs.items()):
                team_records = div_lookup.get(div_id, [])
                div_item = rumps.MenuItem(div_name)

                for tr in team_records:
                    tname = tr.get("team", {}).get("name", "Unknown")
                    rec = tr.get("leagueRecord", {})
                    wins = rec.get("wins", 0)
                    losses = rec.get("losses", 0)
                    pct = tr.get("winningPercentage", ".000")
                    gb = tr.get("gamesBack", "—")
                    streak = tr.get("streak", {}).get("streakCode", "—")
                    row = f"{tname}  {wins}-{losses}  {pct}  GB: {gb}  {streak}"
                    div_item.update([rumps.MenuItem(row, callback=AstrosMenuBarApp._noop)])
                    # Collect non-division leaders for wild card
                    if tr.get("divisionRank", "1") != "1":
                        wc_teams.append(tr)

                league_item.update([div_item])

            # Wild Card section
            wc_item = rumps.MenuItem("Wild Card")

            def _wc_key(tr: dict) -> int:
                try:
                    return int(tr.get("wildCardRank"))
                except (TypeError, ValueError):
                    return 999

            wc_teams_sorted = sorted(wc_teams, key=_wc_key)[:10]
            for tr in wc_teams_sorted:
                tname = tr.get("team", {}).get("name", "Unknown")
                rec = tr.get("leagueRecord", {})
                wins = rec.get("wins", 0)
                losses = rec.get("losses", 0)
                wcgb = tr.get("wildCardGamesBack", "—")
                wc_item.update([rumps.MenuItem(f"{tname}  {wins}-{losses}  WC GB: {wcgb}", callback=AstrosMenuBarApp._noop)])
            league_item.update([wc_item])

            self.standings_menu.update([league_item])

    def update_magic_menu(self) -> None:
        """Show magic numbers: division, playoff berth, wild card, #1 seed."""
        self.magic_menu.clear()
        mn = compute_magic_numbers(self.standings_data)
        if not mn:
            self.magic_menu.update([self._item("Standings unavailable")])
            return

        rows: List[Any] = [
            self._item(f"HOU {mn['wins']}-{mn['losses']}  |  {mn['remaining']} games left"),
            None,
        ]

        # Division
        if mn["division_champ"]:
            rows.append(self._item("🏆 AL West: ✅ CLINCHED"))
        elif mn["division_eliminated"]:
            rows.append(self._item("🏆 AL West: ✗ Eliminated"))
        else:
            label = f"🏆 Win AL West: {mn['division']}"
            if not mn["division_leader"]:
                label += f"  ({mn['games_back']} GB)"
            rows.append(self._item(label))

        # Playoff berth
        if mn["clinched_postseason"]:
            rows.append(self._item("🎟 Playoff Berth: ✅ CLINCHED"))
        elif mn["division_eliminated"] and mn["wc_eliminated"]:
            rows.append(self._item("🎟 Playoffs: ✗ Eliminated"))
        else:
            rows.append(self._item(f"🎟 Make the Playoffs: {mn['playoffs']}"))

        # Wild card
        if mn["wc_eliminated"]:
            rows.append(self._item("🃏 Wild Card: ✗ Eliminated"))
        else:
            rows.append(self._item(f"🃏 Clinch a Wild Card: {mn['wild_card']}"))

        # 1 seed
        seed_label = f"🥇 Clinch #1 AL Seed: {mn['top_seed']}"
        if mn["league_rank"] and mn["league_rank"] != "1":
            seed_label += f"  (now #{mn['league_rank']} in AL)"
        rows.append(self._item(seed_label))

        rows.append(None)
        rows.append(self._item("Magic # = HOU wins + rival losses needed (no tiebreakers)"))
        self.magic_menu.update(rows)

    def _refresh_pitcher_stats(self) -> None:
        """Fetch season stats for upcoming probable starters (network calls —
        only invoked from the full/slow refresh paths, not every tick)."""
        today = now_local().strftime("%Y-%m-%d")
        upcoming = [g for g in self.schedule_data if g.get("officialDate", "") >= today]
        pitcher_ids: List[int] = []
        for game in upcoming:
            sp = get_probable_pitcher(game, get_astros_side(game))
            pid = sp.get("id")
            if pid and pid not in pitcher_ids:
                pitcher_ids.append(pid)
        for pid in pitcher_ids[:6]:
            stats = fetch_pitcher_stats(pid)
            if stats:
                self.pitcher_stats_cache[pid] = stats

    def update_odds_menu(self) -> None:
        """Show odds for the Astros game."""
        self.odds_menu.clear()
        api_key = self.config.get("odds_api_key", "")
        if not api_key:
            self.odds_menu.update([rumps.MenuItem("No API key — add odds_api_key to config", callback=AstrosMenuBarApp._noop)])
            return
        if not self.odds_data:
            self.odds_menu.update([rumps.MenuItem("No odds available", callback=AstrosMenuBarApp._noop)])
            return
        parsed = parse_odds(self.odds_data)
        matchup = parsed.get("matchup", "")
        ml = parsed.get("moneyline", {})
        spread = parsed.get("spread", {})
        total = parsed.get("total", {})
        updated = parsed.get("updated", "")

        away_ml = format_odds_price(ml.get("away", {}).get("price", 0)) if ml.get("away") else "—"
        home_ml = format_odds_price(ml.get("home", {}).get("price", 0)) if ml.get("home") else "—"
        away_sp = spread.get("away", {})
        home_sp = spread.get("home", {})
        over_d = total.get("over", {})
        under_d = total.get("under", {})

        # commence_time is the game's first pitch (UTC ISO) — show local time
        first_pitch = updated
        try:
            first_pitch = (
                dt.datetime.fromisoformat(updated.replace("Z", "+00:00"))
                .astimezone().strftime("%a %-I:%M %p")
            )
        except Exception:
            pass

        self.odds_menu.update([
            rumps.MenuItem(f"Game: {matchup}", callback=AstrosMenuBarApp._noop),
            None,
            rumps.MenuItem(f"Moneyline — Away: {away_ml}  Home: {home_ml}", callback=AstrosMenuBarApp._noop),
            rumps.MenuItem(
                f"Run Line — Away: {away_sp.get('point', '—')} ({format_odds_price(away_sp.get('price', 0)) if away_sp else '—'})"
                f"  Home: {home_sp.get('point', '—')} ({format_odds_price(home_sp.get('price', 0)) if home_sp else '—'})",
                callback=AstrosMenuBarApp._noop,
            ),
            rumps.MenuItem(
                f"O/U: {over_d.get('point', '—')}  Over {format_odds_price(over_d.get('price', 0)) if over_d else '—'}"
                f"  Under {format_odds_price(under_d.get('price', 0)) if under_d else '—'}",
                callback=AstrosMenuBarApp._noop,
            ),
            None,
            rumps.MenuItem(f"First Pitch: {first_pitch}", callback=AstrosMenuBarApp._noop),
        ])

    def update_weather_menu(self) -> None:
        """Show ballpark weather."""
        self.weather_menu.clear()
        w = self.weather_data
        if not w:
            self.weather_menu.update([rumps.MenuItem("Weather unavailable", callback=AstrosMenuBarApp._noop)])
            return
        temp_f = w.get("temp_f", 0)
        temp_c = w.get("temp_c", 0)
        condition = w.get("condition", "Unknown")
        max_f = w.get("max_f", 0)
        min_f = w.get("min_f", 0)
        max_c = w.get("max_c", 0)
        min_c = w.get("min_c", 0)
        wind_mph = w.get("wind_mph", 0)
        wind_kmh = w.get("wind_kmh", 0)
        updated = w.get("updated", "")

        # Name the ballpark the forecast is for
        game = self.game_state.get("game")
        venue_name = (game or {}).get("venue", {}).get("name", "") or "Daikin Park"

        self.weather_menu.update([
            rumps.MenuItem(f"📍 {venue_name}", callback=AstrosMenuBarApp._noop),
            rumps.MenuItem(f"Temp: {temp_f:.0f}°F / {temp_c:.0f}°C", callback=AstrosMenuBarApp._noop),
            rumps.MenuItem(f"Condition: {condition}", callback=AstrosMenuBarApp._noop),
            rumps.MenuItem(f"H/L: {max_f:.0f}°F / {min_f:.0f}°F  ({max_c:.0f}°C / {min_c:.0f}°C)", callback=AstrosMenuBarApp._noop),
            rumps.MenuItem(f"Wind: {wind_mph:.0f} mph ({wind_kmh:.0f} km/h)", callback=AstrosMenuBarApp._noop),
            None,
            rumps.MenuItem(f"Updated: {updated}", callback=AstrosMenuBarApp._noop),
        ])

    def update_stats_menu(self) -> None:
        """Show Astros team stats."""
        self.stats_menu.clear()
        h = self.team_stats.get("hitting", {})
        p = self.team_stats.get("pitching", {})
        if not h and not p:
            self.stats_menu.update([rumps.MenuItem("Stats unavailable", callback=AstrosMenuBarApp._noop)])
            return

        record = f"{h.get('wins', '—')}-{h.get('losses', '—')}"
        avg = h.get("avg", "—")
        hr = h.get("homeRuns", "—")
        runs = h.get("runs", "—")
        ops = h.get("ops", "—")
        era = p.get("era", "—")

        self.stats_menu.update([
            rumps.MenuItem(f"Record: {record}", callback=AstrosMenuBarApp._noop),
            rumps.MenuItem(f"Batting Avg: {avg}", callback=AstrosMenuBarApp._noop),
            rumps.MenuItem(f"Home Runs: {hr}", callback=AstrosMenuBarApp._noop),
            rumps.MenuItem(f"Runs Scored: {runs}", callback=AstrosMenuBarApp._noop),
            rumps.MenuItem(f"OPS: {ops}", callback=AstrosMenuBarApp._noop),
            rumps.MenuItem(f"Team ERA: {era}", callback=AstrosMenuBarApp._noop),
        ])

    # ------------------------------------------------------------------
    # Refresh logic
    # ------------------------------------------------------------------

    def _update_all_menus(self) -> None:
        """Call all update_* methods."""
        self.update_title()
        self.update_top_section()
        self.update_todays_game_menu()
        self.update_schedule_menu()
        self.update_lineup_menu()
        self.update_rotation_menu()
        self.update_standings_menu()
        self.update_magic_menu()
        self.update_odds_menu()
        self.update_weather_menu()
        self.update_stats_menu()

    def refresh_all(self, _sender: Any) -> None:
        """Full refresh of all data sources."""
        logging.info("refresh_all called")
        try:
            today = now_local().strftime("%Y-%m-%d")
            end = (now_local() + dt.timedelta(days=14)).strftime("%Y-%m-%d")
            self.schedule_data = fetch_schedule(today, end)
            write_cache("schedule", {"games": self.schedule_data})

            self.game_state = detect_game_state(self.schedule_data)
            state = self.game_state.get("state", "off")
            game_pk = self.game_state.get("game_pk")

            # Keep the final-score icon color for 30 min, then revert —
            # also when the app starts up on an already-final game.
            if state == "final":
                if self.final_revert_time is None:
                    self.final_revert_time = now_local() + dt.timedelta(minutes=30)
            else:
                self.final_revert_time = None

            if state == "live" and game_pk:
                feed = fetch_live_game(game_pk)
                self.live_data = parse_live_data(feed)
                boxscore = fetch_boxscore(game_pk)
                new_lineup = parse_lineup(boxscore, ASTROS_TEAM_ID)
                if new_lineup:
                    self.lineup_data = new_lineup
            elif state in ("final", "pre") and game_pk:
                boxscore = fetch_boxscore(game_pk)
                new_lineup = parse_lineup(boxscore, ASTROS_TEAM_ID)
                if new_lineup:
                    self.lineup_data = new_lineup
                    write_cache("lineup", {"lineup": self.lineup_data})

            self.standings_data = fetch_standings()
            write_cache("standings", {"records": self.standings_data})

            self.team_stats = fetch_team_stats()
            write_cache("team_stats", self.team_stats)

            self._refresh_pitcher_stats()

            api_key = self.config.get("odds_api_key", "")
            if api_key:
                self.odds_data = fetch_odds(api_key)
                write_cache("odds", self.odds_data)

            game = self.game_state.get("game")
            if game:
                astros_side = get_astros_side(game)
                venue_team = ASTROS_TEAM_ID if astros_side == "home" else opponent_team_id(game)
            else:
                venue_team = ASTROS_TEAM_ID
            self.weather_data = fetch_weather(venue_team)
            write_cache("weather", self.weather_data)

        except Exception as exc:
            logging.exception("refresh_all error: %s", exc)
        finally:
            self._update_all_menus()

    def _set_interval(self, seconds: int) -> None:
        """Adjust the primary timer interval if it changed."""
        try:
            if self.primary_timer.interval != seconds:
                self.primary_timer.interval = seconds
                logging.info("primary timer interval -> %ss", seconds)
        except Exception as exc:
            logging.exception("_set_interval failed: %s", exc)

    def refresh_primary(self, sender: Any) -> None:
        """Primary tick; handles game-state transitions. Interval adapts:
        60s live/near game time, 15 min pre-game/final, 30 min off days."""
        # On first tick, do a full refresh so all data is populated immediately
        if not self._did_initial_refresh:
            self._did_initial_refresh = True
            self.refresh_all(None)
            return
        logging.info("refresh_primary tick")
        try:
            today = now_local().strftime("%Y-%m-%d")
            end = (now_local() + dt.timedelta(days=14)).strftime("%Y-%m-%d")
            new_schedule = fetch_schedule(today, end)
            if new_schedule:
                self.schedule_data = new_schedule
                write_cache("schedule", {"games": self.schedule_data})

            old_state = self.game_state.get("state", "off")
            new_game_state = detect_game_state(self.schedule_data)
            new_state = new_game_state.get("state", "off")
            game_pk = new_game_state.get("game_pk")
            game = new_game_state.get("game")

            # Commit the new state FIRST so a failure below can never leave
            # us stuck re-detecting the same transition forever.
            self.game_state = new_game_state

            # State transition: entering live
            if old_state != "live" and new_state == "live":
                logging.info("Game going live")
                notifs = self.config.get("notifications", {})
                if notifs.get("game_starting", True):
                    self.send_notification("Game Starting", "The Astros game is underway!")

            # State transition: live ending → final
            if old_state == "live" and new_state == "final":
                logging.info("Game ended — final")
                notifs = self.config.get("notifications", {})
                if notifs.get("final_score", True) and game:
                    side = get_astros_side(game)
                    opp_side = "home" if side == "away" else "away"
                    teams = game.get("teams", {})
                    astros_score = teams.get(side, {}).get("score", 0) or 0
                    opp_score = teams.get(opp_side, {}).get("score", 0) or 0
                    opp_name = game["teams"][opp_side]["team"]["name"]
                    result = "W" if astros_score > opp_score else "L"
                    self.send_notification(
                        "Final Score",
                        f"Astros {astros_score}, {opp_name.split()[-1]} {opp_score} — {result}"
                    )

            # Final-score icon: hold color 30 min, then revert
            if new_state == "final":
                if self.final_revert_time is None:
                    self.final_revert_time = now_local() + dt.timedelta(minutes=30)
            else:
                self.final_revert_time = None

            # Adaptive polling interval + "starting soon" notification
            if new_state == "live":
                self._set_interval(60)
            elif new_state == "final":
                self._set_interval(900)
            elif new_state == "off":
                self._set_interval(1800)
            elif new_state == "pre":
                minutes_until = None
                game_date_str = (game or {}).get("gameDate", "")
                if game_date_str:
                    try:
                        utc_dt = dt.datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
                        local_dt = utc_dt.astimezone()
                        minutes_until = (local_dt - now_local().astimezone()).total_seconds() / 60
                    except Exception:
                        minutes_until = None
                # Poll fast near first pitch so "live" is caught promptly
                if minutes_until is not None and minutes_until <= 30:
                    self._set_interval(60)
                else:
                    self._set_interval(900)
                notifs = self.config.get("notifications", {})
                if (
                    minutes_until is not None
                    and 0 < minutes_until <= 15
                    and notifs.get("game_starting", True)
                    and self._starting_soon_pk != game_pk  # only notify once per game
                ):
                    self._starting_soon_pk = game_pk
                    self.send_notification(
                        "Game Starting Soon",
                        f"Astros game starts in ~{int(minutes_until)} min!"
                    )

            # If live: fetch live data, check scoring plays, update lineup
            if new_state == "live" and game_pk:
                # New game (or game 2 of a doubleheader): reset score tracking
                if game_pk != self._score_watch_pk:
                    self._score_watch_pk = game_pk
                    self.previous_astros_score = None
                feed = fetch_live_game(game_pk)
                self.live_data = parse_live_data(feed)

                # Scoring plays notification
                if game:
                    side = get_astros_side(game)
                    opp_side = "home" if side == "away" else "away"
                    current_astros_runs = self.live_data.get(f"{side}_runs", 0) or 0
                    notifs = self.config.get("notifications", {})
                    if (
                        self.previous_astros_score is not None
                        and current_astros_runs > self.previous_astros_score
                        and notifs.get("scoring_plays", False)
                    ):
                        opp_runs = self.live_data.get(f"{opp_side}_runs", 0) or 0
                        away_abbr = self.live_data.get("away_abbr", "AWY")
                        home_abbr = self.live_data.get("home_abbr", "HME")
                        self.send_notification(
                            "Astros Score!",
                            f"{away_abbr} {self.live_data.get('away_runs', 0)} — "
                            f"{home_abbr} {self.live_data.get('home_runs', 0)}"
                        )
                    self.previous_astros_score = current_astros_runs

                # Update lineup
                boxscore = fetch_boxscore(game_pk)
                new_lineup = parse_lineup(boxscore, ASTROS_TEAM_ID)
                if new_lineup:
                    had_lineup = bool(self.lineup_data)
                    self.lineup_data = new_lineup
                    notifs = self.config.get("notifications", {})
                    if not had_lineup and notifs.get("lineup_posted", False):
                        self.send_notification("Lineup Posted", "Astros lineup has been announced!")

        except Exception as exc:
            logging.exception("refresh_primary error: %s", exc)
        finally:
            self._update_all_menus()

    @rumps.timer(7200)
    def refresh_slow(self, _sender: Any) -> None:
        """Called every 2 hours: standings, team stats, odds, weather."""
        logging.info("refresh_slow tick")
        try:
            self.standings_data = fetch_standings()
            write_cache("standings", {"records": self.standings_data})

            self.team_stats = fetch_team_stats()
            write_cache("team_stats", self.team_stats)

            self._refresh_pitcher_stats()

            api_key = self.config.get("odds_api_key", "")
            if api_key:
                self.odds_data = fetch_odds(api_key)
                write_cache("odds", self.odds_data)

            game = self.game_state.get("game")
            if game:
                astros_side = get_astros_side(game)
                venue_team = ASTROS_TEAM_ID if astros_side == "home" else opponent_team_id(game)
            else:
                venue_team = ASTROS_TEAM_ID
            self.weather_data = fetch_weather(venue_team)
            write_cache("weather", self.weather_data)

        except Exception as exc:
            logging.exception("refresh_slow error: %s", exc)
        finally:
            self.update_standings_menu()
            self.update_magic_menu()
            self.update_stats_menu()
            self.update_rotation_menu()
            self.update_odds_menu()
            self.update_weather_menu()


if __name__ == "__main__":
    setup_logging()
    install_launch_agent()
    try:
        app = AstrosMenuBarApp()
        app.run()
    except Exception as error:
        logging.exception("Fatal app error: %s", error)
