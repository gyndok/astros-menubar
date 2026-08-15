# Houston Astros Menu Bar App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a macOS menu bar app that lets the user follow the Houston Astros with live scores, schedules, lineups, standings, odds, and weather.

**Architecture:** Single-file Python app using `rumps` for the macOS menu bar. Data from MLB Stats API (free), The Odds API (key required), and Open-Meteo (free). YAML config at `~/.config/astros-menubar/config.yaml`, JSON file caching, LaunchAgent for auto-start.

**Tech Stack:** Python 3, rumps, requests, pyyaml

---

## File Structure

```
~/astros-menubar/
  astros_menubar.py       # Main application
  install.sh              # Setup script
  uninstall.sh            # Removal script
  requirements.txt        # Python dependencies
  README.md               # Usage documentation
  docs/                   # Design spec and plans
```

All files are in `~/astros-menubar/`. Config/cache/logs live at `~/.config/astros-menubar/`.

---

### Task 1: Project Scaffolding and Dependencies

**Files:**
- Create: `~/astros-menubar/requirements.txt`
- Create: `~/astros-menubar/astros_menubar.py` (skeleton)

- [ ] **Step 1: Create requirements.txt**

```
rumps>=0.4.0
requests>=2.28.0
pyyaml>=6.0
```

- [ ] **Step 2: Install dependencies**

Run: `pip3 install -r ~/astros-menubar/requirements.txt`
Expected: All packages install successfully.

- [ ] **Step 3: Create the application skeleton**

Write `~/astros-menubar/astros_menubar.py` with these contents:

```python
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
    144: (34.0736, -118.2406),   # Los Angeles Angels - Angel Stadium
    145: (40.7527, -73.8458),    # New York Mets - Citi Field
    146: (42.3389, -83.0486),    # Detroit Tigers - Comerica Park
    147: (40.8296, -73.9262),    # New York Yankees - Yankee Stadium
    158: (43.0281, -87.9712),    # Milwaukee Brewers duplicate
    160: (34.0739, -118.2400),   # Los Angeles Angels - Angel Stadium
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
```

- [ ] **Step 4: Verify skeleton runs**

Run: `python3 ~/astros-menubar/astros_menubar.py`
Expected: Prints "Astros Menu Bar skeleton loaded." and exits.

- [ ] **Step 5: Commit**

```bash
cd ~/astros-menubar && git init && git add requirements.txt astros_menubar.py && git commit -m "feat: project scaffolding with constants, config, and dependencies"
```

---

### Task 2: MLB API Data Fetching (Schedule, Live Game, Standings, Stats)

**Files:**
- Modify: `~/astros-menubar/astros_menubar.py`

This task adds all the MLB Stats API helper functions. They are pure data-fetching functions (no menu code), so they can be verified independently.

- [ ] **Step 1: Add cache read/write helpers**

Add after the `now_local()` function:

```python
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
```

- [ ] **Step 2: Add fetch_schedule function**

```python
def fetch_schedule(start_date: str, end_date: str) -> List[dict]:
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
```

- [ ] **Step 3: Add fetch_live_game function**

```python
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
```

- [ ] **Step 4: Add fetch_boxscore function (for lineups)**

```python
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


def parse_lineup(boxscore: dict, team_id: int) -> List[dict]:
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
```

- [ ] **Step 5: Add fetch_standings function**

```python
def fetch_standings() -> List[dict]:
    """Fetch all MLB division standings."""
    try:
        url = f"{MLB_API_BASE}/standings?leagueId=103,104&season={now_local().year}&standingsTypes=regularSeason"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json().get("records", [])
    except Exception as exc:
        logging.exception("fetch_standings failed: %s", exc)
        return []
```

- [ ] **Step 6: Add fetch_team_stats function**

```python
def fetch_team_stats() -> dict:
    """Fetch Astros team hitting and pitching stats for current season."""
    result = {}
    try:
        year = now_local().year
        # Hitting
        url = f"{MLB_API_BASE}/teams/{ASTROS_TEAM_ID}/stats?stats=season&group=hitting&season={year}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        hitting_stats = resp.json().get("stats", [])
        if hitting_stats:
            splits = hitting_stats[0].get("splits", [])
            if splits:
                result["hitting"] = splits[0].get("stat", {})

        # Pitching
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
```

- [ ] **Step 7: Add fetch_pitcher_stats function**

```python
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
```

- [ ] **Step 8: Verify API functions work**

Add a temporary test block at the bottom of the file (replace the existing `if __name__` block temporarily):

```python
if __name__ == "__main__":
    setup_logging()
    today = now_local().strftime("%Y-%m-%d")
    end = (now_local() + dt.timedelta(days=7)).strftime("%Y-%m-%d")

    print("=== Schedule ===")
    games = fetch_schedule(today, end)
    for g in games[:3]:
        away = g["teams"]["away"]["team"]["name"]
        home = g["teams"]["home"]["team"]["name"]
        print(f"  {g['officialDate']}: {away} @ {home}")

    print("\n=== Standings ===")
    records = fetch_standings()
    for rec in records:
        div_id = rec.get("division", {}).get("id")
        teams = [(tr["team"]["name"], tr["leagueRecord"]["wins"], tr["leagueRecord"]["losses"]) for tr in rec.get("teamRecords", [])]
        print(f"  Division {div_id}: {teams[:2]}...")

    print("\n=== Team Stats ===")
    stats = fetch_team_stats()
    h = stats.get("hitting", {})
    p = stats.get("pitching", {})
    print(f"  AVG: {h.get('avg')}  HR: {h.get('homeRuns')}  ERA: {p.get('era')}")

    print("\nAll API functions working.")
```

Run: `python3 ~/astros-menubar/astros_menubar.py`
Expected: Schedule, standings, and stats data prints successfully.

- [ ] **Step 9: Commit**

```bash
cd ~/astros-menubar && git add astros_menubar.py && git commit -m "feat: add MLB Stats API data fetching functions"
```

---

### Task 3: Odds and Weather API Functions

**Files:**
- Modify: `~/astros-menubar/astros_menubar.py`

- [ ] **Step 1: Add fetch_odds function**

Add after `fetch_pitcher_stats`:

```python
def fetch_odds(api_key: str) -> dict:
    """Fetch Astros game odds from The Odds API.

    Returns odds for the next upcoming Astros game, or empty dict if unavailable.
    """
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
                    direction = o["name"].lower()  # "Over" or "Under"
                    result["total"][direction] = {"price": o["price"], "point": o.get("point", 0)}
        break  # Use first bookmaker only
    return result
```

- [ ] **Step 2: Add fetch_weather function**

```python
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
```

- [ ] **Step 3: Verify both functions**

Update the test block at the bottom:

```python
if __name__ == "__main__":
    setup_logging()
    config = load_config()

    print("=== Weather (Minute Maid Park) ===")
    w = fetch_weather(ASTROS_TEAM_ID)
    print(f"  {w.get('temp_f', 0):.0f}°F, {w.get('condition', 'Unknown')}, Wind: {w.get('wind_mph', 0):.0f} mph")

    print("\n=== Odds ===")
    odds_key = config.get("odds_api_key", "")
    if odds_key:
        raw = fetch_odds(odds_key)
        parsed = parse_odds(raw)
        print(f"  {parsed['matchup']}")
        ml = parsed.get("moneyline", {})
        for side in ("away", "home"):
            info = ml.get(side, {})
            print(f"  {info.get('name', '?')}: {info.get('price', '?')}")
    else:
        print("  No API key configured — skipping odds test")

    print("\nAPI functions verified.")
```

Run: `python3 ~/astros-menubar/astros_menubar.py`
Expected: Weather data prints. Odds prints data if key is configured, or skips gracefully.

- [ ] **Step 4: Commit**

```bash
cd ~/astros-menubar && git add astros_menubar.py && git commit -m "feat: add odds and weather API functions"
```

---

### Task 4: Game State Detection and Helper Functions

**Files:**
- Modify: `~/astros-menubar/astros_menubar.py`

These functions determine what state the Astros game is in and format display data. They sit between the API functions and the menu UI.

- [ ] **Step 1: Add game state detection**

Add after the API functions:

```python
def detect_game_state(games: List[dict]) -> dict:
    """Determine current game state from today's schedule.

    Returns a dict with:
      - state: "live", "pre", "final", "off"
      - game: the game dict (if any today)
      - game_pk: gamePk for live/boxscore queries
    """
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

    # Runners
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
```

- [ ] **Step 2: Verify helpers**

Update the test block:

```python
if __name__ == "__main__":
    setup_logging()
    today = now_local().strftime("%Y-%m-%d")
    end = (now_local() + dt.timedelta(days=7)).strftime("%Y-%m-%d")
    games = fetch_schedule(today, end)

    state_info = detect_game_state(games)
    print(f"Game state: {state_info['state']}")

    if state_info["game"]:
        g = state_info["game"]
        side = get_astros_side(g)
        print(f"Astros are: {side}")
        print(f"Time: {format_game_time(g)}")
        print(f"TV: {get_tv_broadcast(g)}")
        print(f"Record: {format_record(g, side)}")
        pp = get_probable_pitcher(g, side)
        print(f"Probable: {pp['name']}")

    if games:
        for g in games[:3]:
            print(f"  {g['officialDate']}: {format_game_time(g)} - TV: {get_tv_broadcast(g)}")

    print("\nHelpers verified.")
```

Run: `python3 ~/astros-menubar/astros_menubar.py`
Expected: Game state, side, time, TV, record all print correctly.

- [ ] **Step 3: Commit**

```bash
cd ~/astros-menubar && git add astros_menubar.py && git commit -m "feat: add game state detection and display helpers"
```

---

### Task 5: Menu Bar App — Core Menu Structure

**Files:**
- Modify: `~/astros-menubar/astros_menubar.py`

This is the main `AstrosMenuBarApp` class with full menu structure and the context-aware top section.

- [ ] **Step 1: Add the AstrosMenuBarApp class with __init__ and _build_menu**

Replace the test `if __name__` block. Add the class before it:

```python
class AstrosMenuBarApp(rumps.App):
    """Main menubar application class."""

    def __init__(self) -> None:
        super().__init__(APP_NAME, title="⚾", quit_button=None)
        self.config = load_config()

        # Cached data
        self.schedule_data: List[dict] = []
        self.game_state: dict = {"state": "off", "game": None, "game_pk": None}
        self.live_data: dict = {}
        self.lineup_data: List[dict] = []
        self.standings_data: List[dict] = []
        self.odds_data: dict = {}
        self.weather_data: dict = {}
        self.team_stats: dict = {}
        self.previous_astros_score: Optional[int] = None
        self.final_revert_time: Optional[dt.datetime] = None

        # Load cached data
        cached_standings = read_cache("standings")
        if cached_standings:
            self.standings_data = cached_standings.get("records", [])
        cached_odds = read_cache("odds")
        if cached_odds:
            self.odds_data = cached_odds
        cached_weather = read_cache("weather")
        if cached_weather:
            self.weather_data = cached_weather

        self._build_menu()
        self.refresh_all(None)

        # Timers
        self.primary_timer = rumps.Timer(self.refresh_primary, 60)
        self.slow_timer = rumps.Timer(self.refresh_slow, 7200)
        self.primary_timer.start()
        self.slow_timer.start()

    def _build_menu(self) -> None:
        self.menu.clear()

        # --- Top section (context-aware) ---
        self.top_line_1 = rumps.MenuItem("Loading...")
        self.top_line_2 = rumps.MenuItem("")
        self.top_line_3 = rumps.MenuItem("")
        self.top_line_4 = rumps.MenuItem("")
        self.top_line_5 = rumps.MenuItem("")

        # --- Today's Game ---
        self.todays_game_menu = rumps.MenuItem("⚾ Today's Game")

        # --- Schedule ---
        self.schedule_menu = rumps.MenuItem("📅 Schedule")

        # --- Lineup ---
        self.lineup_menu = rumps.MenuItem("👥 Lineup")

        # --- Starting Rotation ---
        self.rotation_menu = rumps.MenuItem("⚾ Starting Rotation")

        # --- Standings ---
        self.standings_menu = rumps.MenuItem("📊 Standings")

        # --- Vegas Odds ---
        self.odds_menu = rumps.MenuItem("💰 Vegas Odds")

        # --- Weather ---
        self.weather_menu = rumps.MenuItem("🌤 Ballpark Weather")

        # --- Quick Links ---
        self.links_menu = rumps.MenuItem("🔗 Quick Links")
        for link in self.config.get("quick_links", []):
            name = str(link.get("name", ""))
            url = str(link.get("url", ""))
            item = rumps.MenuItem(name, callback=self.open_link)
            item._url = url
            self.links_menu.add(item)

        # --- Team Stats ---
        self.stats_menu = rumps.MenuItem("📊 Team Stats")

        # --- Refresh ---
        self.refresh_item = rumps.MenuItem("🔄 Refresh Now", callback=self.manual_refresh)

        # --- Settings ---
        self.settings_menu = rumps.MenuItem("⚙️ Settings")
        self.notif_menu = rumps.MenuItem("Notifications")
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
        self._sync_notification_states()
        self.notif_menu.add(self.notif_game_starting)
        self.notif_menu.add(self.notif_final_score)
        self.notif_menu.add(self.notif_scoring_plays)
        self.notif_menu.add(self.notif_lineup_posted)
        self.settings_menu.add(self.notif_menu)
        self.settings_menu.add(rumps.MenuItem("Edit Config", callback=self.edit_config))
        self.settings_menu.add(rumps.MenuItem("Quit", callback=self.quit_app))

        # === Assemble ===
        self.menu.add(self.top_line_1)
        self.menu.add(self.top_line_2)
        self.menu.add(self.top_line_3)
        self.menu.add(self.top_line_4)
        self.menu.add(self.top_line_5)
        self.menu.add(rumps.separator)
        self.menu.add(self.todays_game_menu)
        self.menu.add(self.schedule_menu)
        self.menu.add(self.lineup_menu)
        self.menu.add(self.rotation_menu)
        self.menu.add(rumps.separator)
        self.menu.add(self.standings_menu)
        self.menu.add(self.odds_menu)
        self.menu.add(self.weather_menu)
        self.menu.add(rumps.separator)
        self.menu.add(self.links_menu)
        self.menu.add(self.stats_menu)
        self.menu.add(self.refresh_item)
        self.menu.add(rumps.separator)
        self.menu.add(self.settings_menu)

    def _sync_notification_states(self) -> None:
        notifs = self.config.get("notifications", {})
        self.notif_game_starting.state = notifs.get("game_starting", True)
        self.notif_final_score.state = notifs.get("final_score", True)
        self.notif_scoring_plays.state = notifs.get("scoring_plays", False)
        self.notif_lineup_posted.state = notifs.get("lineup_posted", False)

    def toggle_notification(self, sender) -> None:
        sender.state = not sender.state
        mapping = {
            "Game Starting Soon": "game_starting",
            "Final Score": "final_score",
            "Astros Scoring Plays": "scoring_plays",
            "Lineup Posted": "lineup_posted",
        }
        key = mapping.get(sender.title)
        if key:
            self.config.setdefault("notifications", {})[key] = bool(sender.state)
            try:
                with CONFIG_PATH.open("w", encoding="utf-8") as f:
                    yaml.safe_dump(self.config, f, sort_keys=False)
            except Exception as exc:
                logging.exception("Failed saving config: %s", exc)

    def open_link(self, sender) -> None:
        url = getattr(sender, "_url", "")
        if url:
            webbrowser.open(url)

    def edit_config(self, _sender) -> None:
        try:
            subprocess.Popen(["open", str(CONFIG_PATH)])
        except Exception as exc:
            logging.exception("Failed opening config: %s", exc)

    def quit_app(self, _sender) -> None:
        rumps.quit_application()

    def manual_refresh(self, _sender) -> None:
        self.refresh_all(None)

    def send_notification(self, title: str, message: str) -> None:
        try:
            rumps.notification(APP_NAME, title, message)
        except Exception as exc:
            logging.exception("Notification failed: %s", exc)
```

- [ ] **Step 2: Commit**

```bash
cd ~/astros-menubar && git add astros_menubar.py && git commit -m "feat: add AstrosMenuBarApp class with full menu structure"
```

---

### Task 6: Refresh Logic and Dynamic Title

**Files:**
- Modify: `~/astros-menubar/astros_menubar.py`

Add the refresh methods to `AstrosMenuBarApp` and the dynamic menu bar title with status indicator.

- [ ] **Step 1: Add update_title method**

Add inside the class, after `send_notification`:

```python
    def update_title(self) -> None:
        """Update menu bar icon based on game state."""
        state = self.game_state.get("state", "off")

        # Check if we should revert from final state
        if self.final_revert_time and now_local() > self.final_revert_time:
            self.final_revert_time = None
            self.title = "⚾"
            return

        if state == "live" and self.live_data:
            astros_side = get_astros_side(self.game_state["game"])
            opp_side = "home" if astros_side == "away" else "away"
            astros_runs = self.live_data.get(f"{astros_side}_runs", 0)
            opp_runs = self.live_data.get(f"{opp_side}_runs", 0)
            if astros_runs > opp_runs:
                self.title = "⚾🟢"
            elif astros_runs < opp_runs:
                self.title = "⚾🔴"
            else:
                self.title = "⚾🟡"
        elif state == "final" and self.game_state.get("game"):
            game = self.game_state["game"]
            astros_side = get_astros_side(game)
            opp_side = "home" if astros_side == "away" else "away"
            astros_score = game["teams"][astros_side].get("score", 0) or 0
            opp_score = game["teams"][opp_side].get("score", 0) or 0
            if astros_score > opp_score:
                self.title = "⚾🟢"
            else:
                self.title = "⚾🔴"
            if not self.final_revert_time:
                self.final_revert_time = now_local() + dt.timedelta(minutes=30)
        else:
            self.title = "⚾"
```

- [ ] **Step 2: Add update_top_section method**

```python
    def update_top_section(self) -> None:
        """Update the context-aware top section of the menu."""
        state = self.game_state.get("state", "off")
        game = self.game_state.get("game")

        if state == "live" and self.live_data:
            ld = self.live_data
            self.top_line_1.title = f"{ld['away_abbr']} {ld['away_runs']} - {ld['home_abbr']} {ld['home_runs']} ({ld['half']} {ld['inning_ordinal']})"
            runners_str = ", ".join(ld["runners"]) if ld["runners"] else "Bases empty"
            self.top_line_2.title = f"Runners: {runners_str}, {ld['outs']} Out"
            self.top_line_3.title = f"Count: {ld['balls']}-{ld['strikes']}"
            self.top_line_4.title = f"Pitching: {ld['pitcher']} vs {ld['batter']}"
            self.top_line_5.title = f"TV: {get_tv_broadcast(game)}" if game else ""

        elif state == "pre" and game:
            side = get_astros_side(game)
            opp_side = "home" if side == "away" else "away"
            opp_name = game["teams"][opp_side]["team"]["name"]
            at_vs = "@" if side == "away" else "vs"
            pp_astros = get_probable_pitcher(game, side)
            pp_opp = get_probable_pitcher(game, opp_side)
            self.top_line_1.title = f"HOU {at_vs} {opp_name} — {format_game_time(game)} CT"
            self.top_line_2.title = f"Probable: {pp_astros['name']} vs {pp_opp['name']}"
            self.top_line_3.title = f"TV: {get_tv_broadcast(game)}"
            self.top_line_4.title = f"Record: {format_record(game, side)}"
            self.top_line_5.title = ""

        elif state == "final" and game:
            side = get_astros_side(game)
            opp_side = "home" if side == "away" else "away"
            astros_score = game["teams"][side].get("score", 0) or 0
            opp_score = game["teams"][opp_side].get("score", 0) or 0
            opp_abbr = game["teams"][opp_side]["team"]["name"]
            result = "W" if astros_score > opp_score else "L"
            self.top_line_1.title = f"Final: HOU {astros_score} - {opp_abbr} {opp_score} ({result})"
            self.top_line_2.title = f"Record: {format_record(game, side)}"
            self.top_line_3.title = ""
            self.top_line_4.title = ""
            self.top_line_5.title = ""

        else:
            # Off day
            self.top_line_1.title = "No game today"
            # Find next game
            today = now_local().strftime("%Y-%m-%d")
            future_games = [g for g in self.schedule_data if g.get("officialDate", "") > today]
            if future_games:
                ng = future_games[0]
                side = get_astros_side(ng)
                opp_side = "home" if side == "away" else "away"
                opp_name = ng["teams"][opp_side]["team"]["name"]
                at_vs = "@" if side == "away" else "vs"
                try:
                    game_dt = dt.datetime.fromisoformat(ng["gameDate"].replace("Z", "+00:00")).astimezone()
                    date_str = game_dt.strftime("%a %b %-d, %-I:%M %p")
                except Exception:
                    date_str = ng.get("officialDate", "")
                self.top_line_2.title = f"Next: HOU {at_vs} {opp_name} — {date_str}"
            else:
                self.top_line_2.title = "No upcoming games found"
            self.top_line_3.title = ""
            self.top_line_4.title = ""
            self.top_line_5.title = ""
```

- [ ] **Step 3: Add update_schedule_menu method**

```python
    def update_schedule_menu(self) -> None:
        """Populate the schedule submenu with upcoming games."""
        keys = list(self.schedule_menu.keys())
        for k in keys:
            del self.schedule_menu[k]

        today = now_local().strftime("%Y-%m-%d")
        upcoming = [g for g in self.schedule_data if g.get("officialDate", "") >= today][:10]

        if not upcoming:
            self.schedule_menu.add(rumps.MenuItem("No upcoming games"))
            return

        for g in upcoming:
            side = get_astros_side(g)
            opp_side = "home" if side == "away" else "away"
            opp_name = g["teams"][opp_side]["team"]["name"]
            at_vs = "@" if side == "away" else "vs"
            pp = get_probable_pitcher(g, side)
            time_str = format_game_time(g)
            tv = get_tv_broadcast(g)
            date_str = g.get("officialDate", "")

            game_item = rumps.MenuItem(f"{date_str}: HOU {at_vs} {opp_name} — {time_str}")
            game_item.add(rumps.MenuItem(f"SP: {pp['name']}"))
            game_item.add(rumps.MenuItem(f"TV: {tv}"))
            self.schedule_menu.add(game_item)

        open_full = rumps.MenuItem("View Full Schedule...", callback=self.open_link)
        open_full._url = "https://www.mlb.com/astros/schedule"
        self.schedule_menu.add(rumps.separator)
        self.schedule_menu.add(open_full)
```

- [ ] **Step 4: Add update_lineup_menu method**

```python
    def update_lineup_menu(self) -> None:
        """Populate the lineup submenu."""
        keys = list(self.lineup_menu.keys())
        for k in keys:
            del self.lineup_menu[k]

        if not self.lineup_data:
            self.lineup_menu.add(rumps.MenuItem("Lineup not yet announced"))
            return

        for i, player in enumerate(self.lineup_data, 1):
            self.lineup_menu.add(
                rumps.MenuItem(f"{i}. {player['name']} — {player['position']}")
            )
```

- [ ] **Step 5: Add update_standings_menu method**

```python
    def update_standings_menu(self) -> None:
        """Build the full drill-down standings menu."""
        keys = list(self.standings_menu.keys())
        for k in keys:
            del self.standings_menu[k]

        if not self.standings_data:
            self.standings_menu.add(rumps.MenuItem("Standings unavailable"))
            return

        div_id_to_name = {v: k for k, v in DIVISIONS.items()}
        league_id_to_name = {v: k for k, v in LEAGUES.items()}

        # Group records by league
        by_league: Dict[int, List[dict]] = {}
        for rec in self.standings_data:
            lid = rec.get("league", {}).get("id", 0)
            by_league.setdefault(lid, []).append(rec)

        for league_id in (103, 104):  # AL first, then NL
            league_name = league_id_to_name.get(league_id, f"League {league_id}")
            league_menu = rumps.MenuItem(league_name)

            records = by_league.get(league_id, [])
            for rec in records:
                div_id = rec.get("division", {}).get("id", 0)
                div_name = div_id_to_name.get(div_id, f"Division {div_id}")
                div_menu = rumps.MenuItem(div_name)

                for tr in rec.get("teamRecords", []):
                    team_name = tr["team"]["name"]
                    w = tr["leagueRecord"]["wins"]
                    l = tr["leagueRecord"]["losses"]
                    pct = tr["leagueRecord"]["pct"]
                    gb = tr.get("gamesBack", "-")
                    streak = tr.get("streak", {}).get("streakCode", "")
                    div_menu.add(rumps.MenuItem(f"{team_name}: {w}-{l} ({pct}) GB: {gb} {streak}"))

                league_menu.add(div_menu)

            # Wild card
            wc_menu = rumps.MenuItem(f"{'AL' if league_id == 103 else 'NL'} Wild Card")
            all_teams = []
            for rec in records:
                for tr in rec.get("teamRecords", []):
                    all_teams.append(tr)
            # Sort by wildCardGamesBack (non-division leaders)
            for tr in sorted(all_teams, key=lambda x: int(x.get("leagueRank", "99"))):
                team_name = tr["team"]["name"]
                w = tr["leagueRecord"]["wins"]
                l = tr["leagueRecord"]["losses"]
                wc_gb = tr.get("wildCardGamesBack", "-")
                wc_menu.add(rumps.MenuItem(f"{team_name}: {w}-{l} WC GB: {wc_gb}"))
            league_menu.add(wc_menu)

            self.standings_menu.add(league_menu)
```

- [ ] **Step 6: Add update_odds_menu method**

```python
    def update_odds_menu(self) -> None:
        """Populate the odds submenu."""
        keys = list(self.odds_menu.keys())
        for k in keys:
            del self.odds_menu[k]

        if not self.odds_data or not self.odds_data.get("matchup"):
            if not self.config.get("odds_api_key"):
                self.odds_menu.add(rumps.MenuItem("No API key — set in config.yaml"))
            else:
                self.odds_menu.add(rumps.MenuItem("No odds available"))
            return

        self.odds_menu.add(rumps.MenuItem(self.odds_data["matchup"]))
        self.odds_menu.add(rumps.separator)

        ml = self.odds_data.get("moneyline", {})
        if ml:
            away_ml = ml.get("away", {})
            home_ml = ml.get("home", {})
            self.odds_menu.add(rumps.MenuItem(
                f"Moneyline: {away_ml.get('name', '?')} {format_odds_price(away_ml.get('price', 0))} / "
                f"{home_ml.get('name', '?')} {format_odds_price(home_ml.get('price', 0))}"
            ))

        sp = self.odds_data.get("spread", {})
        if sp:
            away_sp = sp.get("away", {})
            home_sp = sp.get("home", {})
            self.odds_menu.add(rumps.MenuItem(
                f"Run Line: {away_sp.get('name', '?')} {away_sp.get('point', 0):+.1f} ({format_odds_price(away_sp.get('price', 0))}) / "
                f"{home_sp.get('name', '?')} {home_sp.get('point', 0):+.1f} ({format_odds_price(home_sp.get('price', 0))})"
            ))

        total = self.odds_data.get("total", {})
        if total:
            over = total.get("over", {})
            under = total.get("under", {})
            point = over.get("point", under.get("point", 0))
            self.odds_menu.add(rumps.MenuItem(
                f"Over/Under: {point} (O {format_odds_price(over.get('price', 0))} / U {format_odds_price(under.get('price', 0))})"
            ))

        self.odds_menu.add(rumps.separator)
        updated = self.odds_data.get("updated", "")
        self.odds_menu.add(rumps.MenuItem(f"Updated: {updated}"))
```

- [ ] **Step 7: Add update_weather_menu method**

```python
    def update_weather_menu(self) -> None:
        """Populate the weather submenu."""
        keys = list(self.weather_menu.keys())
        for k in keys:
            del self.weather_menu[k]

        if not self.weather_data:
            self.weather_menu.add(rumps.MenuItem("Weather unavailable"))
            return

        w = self.weather_data
        self.weather_menu.add(rumps.MenuItem(
            f"{w.get('temp_f', 0):.0f}°F / {w.get('temp_c', 0):.0f}°C — {w.get('condition', 'Unknown')}"
        ))
        self.weather_menu.add(rumps.MenuItem(
            f"H/L: {w.get('max_f', 0):.0f}/{w.get('min_f', 0):.0f}°F"
        ))
        self.weather_menu.add(rumps.MenuItem(
            f"Wind: {w.get('wind_mph', 0):.0f} mph"
        ))
```

- [ ] **Step 8: Add update_stats_menu method**

```python
    def update_stats_menu(self) -> None:
        """Populate the team stats submenu."""
        keys = list(self.stats_menu.keys())
        for k in keys:
            del self.stats_menu[k]

        hitting = self.team_stats.get("hitting", {})
        pitching = self.team_stats.get("pitching", {})

        if not hitting and not pitching:
            self.stats_menu.add(rumps.MenuItem("Stats unavailable"))
            return

        # Record from current game state or standings
        if self.game_state.get("game"):
            side = get_astros_side(self.game_state["game"])
            record = format_record(self.game_state["game"], side)
            self.stats_menu.add(rumps.MenuItem(f"Record: {record}"))

        if hitting:
            self.stats_menu.add(rumps.MenuItem(f"Batting Avg: {hitting.get('avg', '--')}"))
            self.stats_menu.add(rumps.MenuItem(f"Home Runs: {hitting.get('homeRuns', '--')}"))
            self.stats_menu.add(rumps.MenuItem(f"Runs: {hitting.get('runs', '--')}"))
            self.stats_menu.add(rumps.MenuItem(f"OPS: {hitting.get('ops', '--')}"))

        if pitching:
            self.stats_menu.add(rumps.MenuItem(f"Team ERA: {pitching.get('era', '--')}"))
```

- [ ] **Step 9: Commit**

```bash
cd ~/astros-menubar && git add astros_menubar.py && git commit -m "feat: add all menu update methods and dynamic title"
```

---

### Task 7: Refresh Orchestration and Notifications

**Files:**
- Modify: `~/astros-menubar/astros_menubar.py`

Wire up the timer callbacks that call the API functions and feed the menu update methods. Add notification logic.

- [ ] **Step 1: Add refresh_all, refresh_primary, refresh_slow methods**

Add inside the class:

```python
    def refresh_all(self, _sender) -> None:
        """Full refresh of all data sources."""
        try:
            today = now_local().strftime("%Y-%m-%d")
            end = (now_local() + dt.timedelta(days=14)).strftime("%Y-%m-%d")
            self.schedule_data = fetch_schedule(today, end)
            self.game_state = detect_game_state(self.schedule_data)

            if self.game_state["state"] == "live" and self.game_state["game_pk"]:
                feed = fetch_live_game(self.game_state["game_pk"])
                if feed:
                    self.live_data = parse_live_data(feed)

            if self.game_state["game_pk"]:
                boxscore = fetch_boxscore(self.game_state["game_pk"])
                new_lineup = parse_lineup(boxscore, ASTROS_TEAM_ID)
                if new_lineup and not self.lineup_data:
                    # Lineup just became available
                    if self.config.get("notifications", {}).get("lineup_posted", False):
                        self.send_notification("Lineup Posted", "Today's Astros lineup is available")
                self.lineup_data = new_lineup

            self.standings_data = fetch_standings()
            write_cache("standings", {"records": self.standings_data})

            self.team_stats = fetch_team_stats()

            odds_key = self.config.get("odds_api_key", "")
            if odds_key and self.config.get("show_odds", True):
                raw_odds = fetch_odds(odds_key)
                self.odds_data = parse_odds(raw_odds)
                write_cache("odds", self.odds_data)

            if self.config.get("show_weather", True):
                # Weather for the game-day ballpark
                if self.game_state.get("game"):
                    opp_id = opponent_team_id(self.game_state["game"])
                    side = get_astros_side(self.game_state["game"])
                    park_team = ASTROS_TEAM_ID if side == "home" else opp_id
                else:
                    park_team = ASTROS_TEAM_ID
                self.weather_data = fetch_weather(park_team)
                write_cache("weather", self.weather_data)

            self._update_all_menus()
        except Exception as exc:
            logging.exception("refresh_all failed: %s", exc)

    def refresh_primary(self, _sender) -> None:
        """Primary timer — handles live game polling and game state changes."""
        try:
            today = now_local().strftime("%Y-%m-%d")
            end = (now_local() + dt.timedelta(days=14)).strftime("%Y-%m-%d")

            old_state = self.game_state.get("state", "off")
            self.schedule_data = fetch_schedule(today, end)
            self.game_state = detect_game_state(self.schedule_data)
            new_state = self.game_state.get("state", "off")

            # State transitions
            if old_state != "live" and new_state == "live":
                # Game just started — switch to fast polling
                self.primary_timer.interval = 60
                if self.config.get("notifications", {}).get("game_starting", True):
                    self.send_notification("Game Starting", "The Astros game is underway!")

            elif old_state == "live" and new_state == "final":
                # Game just ended
                self.primary_timer.interval = 1800  # 30 min
                if self.config.get("notifications", {}).get("final_score", True):
                    game = self.game_state["game"]
                    side = get_astros_side(game)
                    opp_side = "home" if side == "away" else "away"
                    a_score = game["teams"][side].get("score", 0) or 0
                    o_score = game["teams"][opp_side].get("score", 0) or 0
                    result = "Win" if a_score > o_score else "Loss"
                    self.send_notification("Final Score", f"HOU {a_score} - {game['teams'][opp_side]['team']['name']} {o_score} ({result})")
                self.previous_astros_score = None

            elif new_state == "pre":
                self.primary_timer.interval = 1800  # 30 min
                # Check if game is about to start (within 15 min)
                if self.game_state.get("game"):
                    try:
                        game_dt_str = self.game_state["game"].get("gameDate", "")
                        game_dt = dt.datetime.fromisoformat(game_dt_str.replace("Z", "+00:00"))
                        minutes_until = (game_dt - dt.datetime.now(dt.timezone.utc)).total_seconds() / 60
                        if 0 < minutes_until <= 15:
                            if self.config.get("notifications", {}).get("game_starting", True):
                                self.send_notification("Game Starting Soon", f"First pitch in ~{int(minutes_until)} minutes")
                            self.primary_timer.interval = 60  # Start polling faster
                    except Exception:
                        pass

            elif new_state == "off":
                self.primary_timer.interval = 3600  # 1 hour

            # If live, fetch live data
            if new_state == "live" and self.game_state["game_pk"]:
                feed = fetch_live_game(self.game_state["game_pk"])
                if feed:
                    new_live = parse_live_data(feed)
                    # Check for scoring play notification
                    if self.config.get("notifications", {}).get("scoring_plays", False):
                        side = get_astros_side(self.game_state["game"])
                        new_score = new_live.get(f"{side}_runs", 0)
                        if self.previous_astros_score is not None and new_score > self.previous_astros_score:
                            self.send_notification(
                                "Astros Score!",
                                f"{new_live['away_abbr']} {new_live['away_runs']} - {new_live['home_abbr']} {new_live['home_runs']}"
                            )
                        self.previous_astros_score = new_score
                    self.live_data = new_live

                # Refresh lineup during game too
                boxscore = fetch_boxscore(self.game_state["game_pk"])
                new_lineup = parse_lineup(boxscore, ASTROS_TEAM_ID)
                if new_lineup:
                    self.lineup_data = new_lineup

            self._update_all_menus()

        except Exception as exc:
            logging.exception("refresh_primary failed: %s", exc)

    def refresh_slow(self, _sender) -> None:
        """Slow timer — standings, odds, weather, stats (every 2 hours)."""
        try:
            self.standings_data = fetch_standings()
            write_cache("standings", {"records": self.standings_data})

            self.team_stats = fetch_team_stats()

            odds_key = self.config.get("odds_api_key", "")
            if odds_key and self.config.get("show_odds", True):
                raw_odds = fetch_odds(odds_key)
                self.odds_data = parse_odds(raw_odds)
                write_cache("odds", self.odds_data)

            if self.config.get("show_weather", True):
                if self.game_state.get("game"):
                    opp_id = opponent_team_id(self.game_state["game"])
                    side = get_astros_side(self.game_state["game"])
                    park_team = ASTROS_TEAM_ID if side == "home" else opp_id
                else:
                    park_team = ASTROS_TEAM_ID
                self.weather_data = fetch_weather(park_team)
                write_cache("weather", self.weather_data)

            self.update_standings_menu()
            self.update_odds_menu()
            self.update_weather_menu()
            self.update_stats_menu()

        except Exception as exc:
            logging.exception("refresh_slow failed: %s", exc)

    def _update_all_menus(self) -> None:
        """Update all menu sections."""
        self.update_title()
        self.update_top_section()
        self.update_schedule_menu()
        self.update_lineup_menu()
        self.update_standings_menu()
        self.update_odds_menu()
        self.update_weather_menu()
        self.update_stats_menu()
```

- [ ] **Step 2: Update the main block**

Replace the test `if __name__` block with the real one:

```python
if __name__ == "__main__":
    setup_logging()
    try:
        app = AstrosMenuBarApp()
        app.run()
    except Exception as error:
        logging.exception("Fatal app error: %s", error)
```

- [ ] **Step 3: Test the app runs**

Run: `python3 ~/astros-menubar/astros_menubar.py`
Expected: ⚾ appears in the menu bar. Clicking it shows the full menu with live data from the APIs. Check that schedule, standings, weather, and stats sections are populated.

- [ ] **Step 4: Commit**

```bash
cd ~/astros-menubar && git add astros_menubar.py && git commit -m "feat: add refresh orchestration, notifications, and dynamic title"
```

---

### Task 8: Starting Rotation Submenu

**Files:**
- Modify: `~/astros-menubar/astros_menubar.py`

- [ ] **Step 1: Add update_rotation_menu method**

Add inside the class:

```python
    def update_rotation_menu(self) -> None:
        """Populate rotation from upcoming schedule's probable pitchers."""
        keys = list(self.rotation_menu.keys())
        for k in keys:
            del self.rotation_menu[k]

        # Collect unique probable pitchers from upcoming schedule
        seen_pitchers = {}
        today = now_local().strftime("%Y-%m-%d")
        upcoming = [g for g in self.schedule_data if g.get("officialDate", "") >= today]

        for g in upcoming:
            side = get_astros_side(g)
            pp = get_probable_pitcher(g, side)
            pid = pp.get("id")
            if pid and pid not in seen_pitchers:
                seen_pitchers[pid] = {
                    "name": pp["name"],
                    "next_start": g.get("officialDate", ""),
                    "id": pid,
                }

        if not seen_pitchers:
            self.rotation_menu.add(rumps.MenuItem("Rotation unavailable"))
            return

        for pid, info in seen_pitchers.items():
            stats = fetch_pitcher_stats(pid)
            w = stats.get("wins", 0)
            l = stats.get("losses", 0)
            era = stats.get("era", "--")
            self.rotation_menu.add(
                rumps.MenuItem(f"{info['name']} — Next: {info['next_start']} ({w}-{l}, {era} ERA)")
            )
```

- [ ] **Step 2: Call it from _update_all_menus**

Add `self.update_rotation_menu()` to the `_update_all_menus` method, after `self.update_lineup_menu()`:

```python
    def _update_all_menus(self) -> None:
        """Update all menu sections."""
        self.update_title()
        self.update_top_section()
        self.update_schedule_menu()
        self.update_lineup_menu()
        self.update_rotation_menu()
        self.update_standings_menu()
        self.update_odds_menu()
        self.update_weather_menu()
        self.update_stats_menu()
```

- [ ] **Step 3: Test rotation submenu**

Run: `python3 ~/astros-menubar/astros_menubar.py`
Expected: ⚾ Starting Rotation submenu shows pitchers with their next start date, W-L, and ERA.

- [ ] **Step 4: Commit**

```bash
cd ~/astros-menubar && git add astros_menubar.py && git commit -m "feat: add starting rotation submenu with pitcher stats"
```

---

### Task 9: Today's Game Submenu

**Files:**
- Modify: `~/astros-menubar/astros_menubar.py`

- [ ] **Step 1: Add update_todays_game_menu method**

Add inside the class:

```python
    def update_todays_game_menu(self) -> None:
        """Populate the Today's Game / Live Game submenu."""
        keys = list(self.todays_game_menu.keys())
        for k in keys:
            del self.todays_game_menu[k]

        state = self.game_state.get("state", "off")
        game = self.game_state.get("game")

        if state == "off":
            self.todays_game_menu.title = "⚾ Today's Game"
            self.todays_game_menu.add(rumps.MenuItem("No game today"))
            return

        if state == "live":
            self.todays_game_menu.title = "⚾ Live Game"
            if self.live_data:
                ld = self.live_data
                self.todays_game_menu.add(rumps.MenuItem(
                    f"{ld['away_abbr']} {ld['away_runs']} - {ld['home_abbr']} {ld['home_runs']} ({ld['half']} {ld['inning_ordinal']})"
                ))
                runners = ", ".join(ld["runners"]) if ld["runners"] else "Bases empty"
                self.todays_game_menu.add(rumps.MenuItem(f"Runners: {runners}, {ld['outs']} Out"))
                self.todays_game_menu.add(rumps.MenuItem(f"Count: {ld['balls']}-{ld['strikes']}"))
                self.todays_game_menu.add(rumps.MenuItem(f"AB: {ld['batter']}"))
                self.todays_game_menu.add(rumps.MenuItem(f"P: {ld['pitcher']}"))
            if game:
                self.todays_game_menu.add(rumps.separator)
                self.todays_game_menu.add(rumps.MenuItem(f"TV: {get_tv_broadcast(game)}"))
        elif state == "pre":
            self.todays_game_menu.title = "⚾ Today's Game"
            if game:
                side = get_astros_side(game)
                opp_side = "home" if side == "away" else "away"
                opp_name = game["teams"][opp_side]["team"]["name"]
                at_vs = "@" if side == "away" else "vs"
                pp_astros = get_probable_pitcher(game, side)
                pp_opp = get_probable_pitcher(game, opp_side)
                self.todays_game_menu.add(rumps.MenuItem(f"HOU {at_vs} {opp_name} — {format_game_time(game)}"))
                self.todays_game_menu.add(rumps.MenuItem(f"SP: {pp_astros['name']} vs {pp_opp['name']}"))
                self.todays_game_menu.add(rumps.MenuItem(f"TV: {get_tv_broadcast(game)}"))
        elif state == "final":
            self.todays_game_menu.title = "⚾ Today's Game (Final)"
            if game:
                side = get_astros_side(game)
                opp_side = "home" if side == "away" else "away"
                a_score = game["teams"][side].get("score", 0) or 0
                o_score = game["teams"][opp_side].get("score", 0) or 0
                opp_name = game["teams"][opp_side]["team"]["name"]
                self.todays_game_menu.add(rumps.MenuItem(f"Final: HOU {a_score} - {opp_name} {o_score}"))
```

- [ ] **Step 2: Call it from _update_all_menus**

Update `_update_all_menus` to include `self.update_todays_game_menu()` right after `self.update_top_section()`:

```python
    def _update_all_menus(self) -> None:
        self.update_title()
        self.update_top_section()
        self.update_todays_game_menu()
        self.update_schedule_menu()
        self.update_lineup_menu()
        self.update_rotation_menu()
        self.update_standings_menu()
        self.update_odds_menu()
        self.update_weather_menu()
        self.update_stats_menu()
```

- [ ] **Step 3: Test**

Run: `python3 ~/astros-menubar/astros_menubar.py`
Expected: Today's Game submenu shows appropriate content based on game state.

- [ ] **Step 4: Commit**

```bash
cd ~/astros-menubar && git add astros_menubar.py && git commit -m "feat: add Today's Game submenu with live/pre/final states"
```

---

### Task 10: Install/Uninstall Scripts and LaunchAgent

**Files:**
- Create: `~/astros-menubar/install.sh`
- Create: `~/astros-menubar/uninstall.sh`

- [ ] **Step 1: Create install.sh**

```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_SCRIPT="$SCRIPT_DIR/astros_menubar.py"
PLIST_NAME="com.gyndok.astros-menubar"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "=== Astros Menu Bar Installer ==="

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements.txt"

# Create config directory
mkdir -p "$HOME/.config/astros-menubar/cache"
echo "Config directory created at ~/.config/astros-menubar/"

# Create LaunchAgent plist
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(which python3)</string>
        <string>$APP_SCRIPT</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$HOME/.config/astros-menubar/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.config/astros-menubar/stderr.log</string>
</dict>
</plist>
PLIST

# Load the LaunchAgent
launchctl load "$PLIST_PATH"

echo ""
echo "=== Installation Complete ==="
echo "The ⚾ icon should appear in your menu bar."
echo ""
echo "To configure odds, edit ~/.config/astros-menubar/config.yaml"
echo "and add your API key from https://the-odds-api.com"
echo ""
echo "To uninstall: bash $SCRIPT_DIR/uninstall.sh"
```

- [ ] **Step 2: Create uninstall.sh**

```bash
#!/bin/bash

PLIST_NAME="com.gyndok.astros-menubar"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "=== Astros Menu Bar Uninstaller ==="

# Kill running process
pkill -f "astros_menubar.py" 2>/dev/null && echo "Stopped running app." || echo "App was not running."

# Unload and remove LaunchAgent
if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null
    rm -f "$PLIST_PATH"
    echo "Removed LaunchAgent."
else
    echo "No LaunchAgent found."
fi

echo ""
read -p "Delete config and cache at ~/.config/astros-menubar/? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$HOME/.config/astros-menubar"
    echo "Config and cache deleted."
else
    echo "Config preserved at ~/.config/astros-menubar/"
fi

echo ""
echo "=== Uninstall Complete ==="
```

- [ ] **Step 3: Make scripts executable**

Run: `chmod +x ~/astros-menubar/install.sh ~/astros-menubar/uninstall.sh`

- [ ] **Step 4: Commit**

```bash
cd ~/astros-menubar && git add install.sh uninstall.sh && git commit -m "feat: add install and uninstall scripts with LaunchAgent"
```

---

### Task 11: Final Integration Test and Launch

- [ ] **Step 1: Kill any running instance**

Run: `pkill -f "astros_menubar.py" 2>/dev/null; echo "done"`

- [ ] **Step 2: Run install script**

Run: `bash ~/astros-menubar/install.sh`
Expected: Dependencies install, LaunchAgent loads, ⚾ appears in menu bar.

- [ ] **Step 3: Verify all menu sections**

Click ⚾ in the menu bar and verify:
- Top section shows correct game state (live/pre/off/final)
- Schedule shows upcoming games with times, pitchers, TV
- Lineup shows batting order (if announced)
- Rotation shows pitchers with stats
- Standings drill-down works (MLB > League > Division)
- Odds show (if API key configured) or graceful message
- Weather shows ballpark conditions
- Quick Links open in browser
- Team Stats show batting/pitching numbers
- Refresh Now triggers a full refresh
- Settings > Notifications toggles work
- Settings > Edit Config opens config file
- Settings > Quit stops the app

- [ ] **Step 4: Verify dynamic title**

If a game is live: menu bar should show ⚾🟢 (winning), ⚾🔴 (losing), or ⚾🟡 (tied).
If no game: menu bar should show ⚾.

- [ ] **Step 5: Verify auto-start on login**

Run: `launchctl list | grep astros`
Expected: `com.gyndok.astros-menubar` appears in the list.

- [ ] **Step 6: Commit final state**

```bash
cd ~/astros-menubar && git add -A && git commit -m "feat: Astros menu bar app v1.0 — complete implementation"
```
