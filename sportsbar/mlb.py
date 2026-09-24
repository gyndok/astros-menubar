"""MLB Stats API: fetching, parsing, and display formatting.

Everything here is free of AppKit/rumps so it can be unit tested anywhere.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import List

import requests

from .config import now_local


ASTROS_TEAM_ID = 117
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"

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


def fetch_league_scores() -> list:
    """Fetch today's games league-wide, with linescores and team abbreviations."""
    try:
        today = now_local().strftime("%Y-%m-%d")
        url = (
            f"{MLB_API_BASE}/schedule?sportId=1&date={today}"
            f"&hydrate=linescore,team"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [g for de in data.get("dates", []) for g in de.get("games", [])]
    except Exception as exc:
        logging.exception("fetch_league_scores failed: %s", exc)
        return []


NON_GAME_STATES = {"Postponed": "PPD", "Cancelled": "CNX", "Suspended": "SUSP"}


def format_league_game(game: dict) -> str:
    """One-line scoreboard row for a league-wide game."""
    away = game.get("teams", {}).get("away", {})
    home = game.get("teams", {}).get("home", {})
    away_abbr = away.get("team", {}).get("abbreviation", "?")
    home_abbr = home.get("team", {}).get("abbreviation", "?")
    star = "⭐ " if ASTROS_TEAM_ID in (
        away.get("team", {}).get("id"), home.get("team", {}).get("id")
    ) else ""

    detailed = game.get("status", {}).get("detailedState", "")
    if detailed in NON_GAME_STATES:
        return f"{star}{away_abbr} @ {home_abbr}   {NON_GAME_STATES[detailed]}"

    status = _game_status(game)
    if status == "live":
        ls = game.get("linescore", {})
        half = "▲" if ls.get("isTopInning", True) else "▼"
        inning = ls.get("currentInning", "")
        return (
            f"{star}{away_abbr} {away.get('score', 0)} — "
            f"{home_abbr} {home.get('score', 0)}   {half}{inning}"
        )
    if status == "final":
        innings = len(game.get("linescore", {}).get("innings", []))
        suffix = f"F/{innings}" if innings and innings != 9 else "F"
        return (
            f"{star}{away_abbr} {away.get('score', 0)} — "
            f"{home_abbr} {home.get('score', 0)}   {suffix}"
        )
    return f"{star}{away_abbr} @ {home_abbr}   {format_game_time(game)}"


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


def parse_scoring_plays(feed: dict, astros_side: str) -> list:
    """Extract scoring plays from the live feed, in chronological order."""
    plays = feed.get("liveData", {}).get("plays", {})
    all_plays = plays.get("allPlays", [])
    result = []
    for idx in plays.get("scoringPlays", []):
        try:
            play = all_plays[idx]
        except (IndexError, TypeError):
            continue
        about = play.get("about", {})
        res = play.get("result", {})
        half = about.get("halfInning", "top")
        batting_side = "away" if half == "top" else "home"
        result.append({
            "inning": about.get("inning", 0),
            "top": half == "top",
            "away_score": res.get("awayScore", 0),
            "home_score": res.get("homeScore", 0),
            "description": res.get("description", "").strip(),
            "astros": batting_side == astros_side,
        })
    return result


def parse_line_score(feed: dict) -> dict:
    """Extract the inning-by-inning line score from the live feed."""
    ls = feed.get("liveData", {}).get("linescore", {})
    innings = ls.get("innings", [])
    if not innings:
        return {}
    gd_teams = feed.get("gameData", {}).get("teams", {})
    totals = ls.get("teams", {})

    def tot(side: str) -> dict:
        t = totals.get(side, {})
        return {
            "runs": t.get("runs", 0),
            "hits": t.get("hits", 0),
            "errors": t.get("errors", 0),
        }

    return {
        "away_abbr": gd_teams.get("away", {}).get("abbreviation", "AWY"),
        "home_abbr": gd_teams.get("home", {}).get("abbreviation", "HME"),
        "innings": [
            {
                "num": inn.get("num", n + 1),
                "away": inn.get("away", {}).get("runs"),
                "home": inn.get("home", {}).get("runs"),
            }
            for n, inn in enumerate(innings)
        ],
        "away": tot("away"),
        "home": tot("home"),
    }


def format_line_score(line_score: dict, is_final: bool) -> List[str]:
    """Render a line score as three monospace-aligned rows:

           1  2  3  4  5  6  7  8  9    R  H  E
    HOU    1  0  0  0  0  1  0  0  0    2  5  0
    TB     0  0  0  0  2  0  1  0  X    3  7  0
    """
    innings = line_score["innings"]
    by_num = {inn["num"]: inn for inn in innings}
    last_num = innings[-1]["num"]
    n_shown = max(9, last_num)

    def cell(num: int, side: str) -> str:
        inn = by_num.get(num)
        if inn is None:
            return " "
        runs = inn[side]
        if runs is None:
            # Home never batted in the last inning of a final = classic X
            if side == "home" and is_final and num == last_num:
                return "X"
            return " "
        return str(runs)

    header = "     " + " ".join(f"{n:>2}" for n in range(1, n_shown + 1)) + "    R  H  E"
    rows = [header]
    for side, abbr in (("away", line_score["away_abbr"]), ("home", line_score["home_abbr"])):
        t = line_score[side]
        cells = " ".join(f"{cell(n, side):>2}" for n in range(1, n_shown + 1))
        rows.append(
            f"{abbr:<5}{cells}   {t['runs']:>2} {t['hits']:>2} {t['errors']:>2}"
        )
    return rows
