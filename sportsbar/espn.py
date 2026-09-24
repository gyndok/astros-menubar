"""ESPN site API: NFL, college football, NBA, and NHL.

ESPN's `site.api.espn.com` endpoints are free and keyless but
undocumented, so everything that knows their JSON layout lives in this
module — if ESPN changes a field, this is the one file to fix. Parsed
games come out as `models.Game`.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Collection, Dict, Iterable, List, Optional

import requests

from .models import CANCELED, FINAL, LIVE, POSTPONED, PRE, Game, Side, TeamRef

ESPN_API_BASE = "https://site.api.espn.com/apis/site/v2/sports"


@dataclass(frozen=True)
class League:
    key: str                  # config name: "nfl"
    name: str                 # "NFL"
    emoji: str
    sport: str                # ESPN path: "football"
    path: str                 # ESPN path: "nfl"
    period_prefix: str        # "Q" → "Q3 4:12"
    regulation_periods: int   # 4 quarters
    scoreboard_params: Dict[str, str] = field(default_factory=dict)
    teams_params: Dict[str, str] = field(default_factory=dict)
    ranked: bool = False      # has a top-25 poll
    daily: bool = False       # scoreboard is today's games, not the week's
    start_verb: str = "kick off"          # "Rockets tip off in ~10 min!"
    score_alerts: bool = True  # alert on every score (not basketball)
    shootout: bool = False    # regular-season ties end in a shootout (NHL)

    @property
    def base(self) -> str:
        return f"{ESPN_API_BASE}/{self.sport}/{self.path}"

    def team_url(self, team_id: str) -> str:
        return f"https://www.espn.com/{self.path}/team/_/id/{team_id}"


LEAGUES: Dict[str, League] = {
    "nfl": League("nfl", "NFL", "🏈", "football", "nfl", "Q", 4),
    "ncaaf": League(
        "ncaaf", "College Football", "🏈", "football", "college-football", "Q", 4,
        # groups=80 = all of FBS (the default scoreboard is only the top 25)
        scoreboard_params={"groups": "80", "limit": "300"},
        teams_params={"limit": "1000"},
        ranked=True,
    ),
    "nba": League(
        "nba", "NBA", "🏀", "basketball", "nba", "Q", 4,
        daily=True, start_verb="tip off", score_alerts=False,
    ),
    "nhl": League(
        "nhl", "NHL", "🏒", "hockey", "nhl", "P", 3,
        daily=True, start_verb="drop the puck", shootout=True,
    ),
}

REGULAR_SEASON = 2

STATE_MAP = {"pre": PRE, "in": LIVE, "post": FINAL}
POSTPONED_NAMES = {"STATUS_POSTPONED", "STATUS_DELAYED"}
CANCELED_NAMES = {"STATUS_CANCELED", "STATUS_CANCELLED", "STATUS_FORFEIT"}


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _get(url: str, params: Optional[dict] = None) -> dict:
    resp = requests.get(url, params=params or None, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_teams(league: League) -> List[TeamRef]:
    """Every team in the league (ESPN's own ids and names)."""
    try:
        data = _get(f"{league.base}/teams", league.teams_params)
        return parse_teams(data, league.key)
    except Exception as exc:
        logging.exception("espn fetch_teams(%s) failed: %s", league.key, exc)
        return []


def fetch_scoreboard(league: League) -> dict:
    """The league's current scoreboard (this week's games), raw JSON."""
    try:
        return _get(f"{league.base}/scoreboard", league.scoreboard_params)
    except Exception as exc:
        logging.exception("espn fetch_scoreboard(%s) failed: %s", league.key, exc)
        return {}


def fetch_team_schedule(league: League, team_id: str) -> dict:
    """A team's season schedule and results, raw JSON."""
    try:
        return _get(f"{league.base}/teams/{team_id}/schedule")
    except Exception as exc:
        logging.exception("espn fetch_team_schedule(%s, %s) failed: %s", league.key, team_id, exc)
        return {}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _team_ref(team: dict, league_key: str) -> TeamRef:
    return TeamRef(
        league=league_key,
        id=str(team.get("id", "")),
        abbr=team.get("abbreviation", "") or "?",
        name=team.get("displayName", "") or team.get("name", ""),
        short_name=team.get("shortDisplayName", "") or team.get("name", ""),
        location=team.get("location", ""),
        nickname=team.get("name", ""),
    )


def parse_teams(data: dict, league_key: str) -> List[TeamRef]:
    teams = []
    for sport in data.get("sports", []):
        for lg in sport.get("leagues", []):
            for entry in lg.get("teams", []):
                team = entry.get("team", entry)
                if team.get("id"):
                    teams.append(_team_ref(team, league_key))
    return teams


def resolve_team(teams: Iterable[TeamRef], ref) -> Optional[TeamRef]:
    """Find the team a config entry means, most specific match first:
    id, abbreviation, full name, short name, school/city, nickname.
    An ambiguous name ("Tigers") resolves to nothing rather than a guess."""
    teams = list(teams)
    needle = str(ref).strip().lower()
    for attr in ("id", "abbr", "name", "short_name", "location", "nickname"):
        matches = [t for t in teams if str(getattr(t, attr)).lower() == needle]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            logging.warning(
                "Favorite %r is ambiguous (%s) — use the abbreviation",
                ref, ", ".join(t.name for t in matches),
            )
            return None
    return None


def _score(value) -> Optional[int]:
    if isinstance(value, dict):
        value = value.get("value", value.get("displayValue"))
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _record(comp: dict) -> str:
    for key in ("records", "record"):
        for rec in comp.get(key) or []:
            if rec.get("type") in (None, "total") or rec.get("name") == "overall":
                summary = rec.get("summary") or rec.get("displayValue")
                if summary:
                    return summary
    return ""


def _side(comp: dict, league_key: str) -> Side:
    rank = (comp.get("curatedRank") or {}).get("current")
    return Side(
        team=_team_ref(comp.get("team", {}), league_key),
        home=comp.get("homeAway") == "home",
        score=_score(comp.get("score")),
        record=_record(comp),
        rank=rank if isinstance(rank, int) and 1 <= rank <= 25 else None,
        winner=comp.get("winner"),
        periods=[_score(ls) for ls in comp.get("linescores") or []],
    )


def _parse_time(value: str) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _broadcast(comp: dict) -> str:
    for b in comp.get("broadcasts") or []:
        names = b.get("names")
        if names:
            return names[0]
        media = (b.get("media") or {}).get("shortName")
        if media:
            return media
    for b in comp.get("geoBroadcasts") or []:
        media = (b.get("media") or {}).get("shortName")
        if media:
            return media
    return ""


def parse_event(event: dict, league_key: str) -> Optional[Game]:
    """One ESPN event (from a scoreboard or team schedule) → Game."""
    comps = event.get("competitions") or []
    if not comps:
        return None
    comp = comps[0]
    competitors = comp.get("competitors") or []
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    if away is None or home is None:
        return None

    status = comp.get("status") or event.get("status") or {}
    stype = status.get("type") or {}
    name = stype.get("name", "")
    state = STATE_MAP.get(stype.get("state"), PRE)
    if name in POSTPONED_NAMES and state != LIVE:
        state = POSTPONED
    elif name in CANCELED_NAMES:
        state = CANCELED

    venue = comp.get("venue") or {}
    situation = comp.get("situation") or {}
    season = event.get("seasonType") or event.get("season") or {}
    return Game(
        league=league_key,
        id=str(event.get("id", comp.get("id", ""))),
        start=_parse_time(comp.get("date") or event.get("date", "")),
        state=state,
        status_name=name,
        detail=stype.get("shortDetail") or stype.get("detail", ""),
        period=int(status.get("period") or 0),
        clock=status.get("displayClock", ""),
        away=_side(away, league_key),
        home=_side(home, league_key),
        venue=venue.get("fullName", ""),
        city=(venue.get("address") or {}).get("city", ""),
        indoor=venue.get("indoor"),
        broadcast=_broadcast(comp),
        week=(event.get("week") or {}).get("number"),
        season_type=season.get("type") if isinstance(season.get("type"), int) else None,
        down_distance=situation.get("downDistanceText", ""),
        possession_id=str(situation.get("possession", "") or ""),
        red_zone=bool(situation.get("isRedZone")),
        last_play=(situation.get("lastPlay") or {}).get("text", ""),
    )


def parse_games(data: dict, league_key: str) -> List[Game]:
    """All games in a scoreboard or team-schedule response, by start time."""
    games = [g for g in (parse_event(e, league_key) for e in data.get("events", [])) if g]
    far_future = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    return sorted(games, key=lambda g: g.start or far_future)


def current_game(
    scoreboard: List[Game], schedule: List[Game], team_id: str, now: dt.datetime
) -> Optional[Game]:
    """The game to feature for a team right now.

    This week's scoreboard game if it has one (live, upcoming, or just
    finished) — otherwise (bye week) its next scheduled game.
    """
    week = [g for g in scoreboard if g.involves(team_id) and g.state != CANCELED]
    live = [g for g in week if g.state == LIVE]
    if live:
        return live[0]
    if week:
        # Weeks rarely have two games for a team; prefer the upcoming one.
        upcoming = [g for g in week if g.state == PRE]
        return upcoming[0] if upcoming else week[-1]
    return next_game(schedule, now)


def next_game(schedule: List[Game], now: dt.datetime) -> Optional[Game]:
    return next(
        (g for g in schedule if g.state == PRE and g.start and g.start >= now), None
    )


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def period_name(game: Game, league: League) -> str:
    """ "Q3" / "P2" in regulation; "OT", "2OT", or (NHL regular season,
    after one OT) "SO" beyond it."""
    ot = game.period - league.regulation_periods
    if ot <= 0:
        return f"{league.period_prefix}{game.period}"
    if league.shootout and ot >= 2 and game.season_type in (None, REGULAR_SEASON):
        return "SO"
    return "OT" if ot == 1 else f"{ot}OT"


def period_label(game: Game, league: League) -> str:
    """Compact game clock: "Q3 4:12", "P2 8:31", "Half", "End P2", "F",
    "F/OT", "F/SO", "PPD"."""
    if game.state == POSTPONED:
        return "PPD"
    if game.state == CANCELED:
        return "CNX"
    if game.state == FINAL:
        if game.period > league.regulation_periods:
            return f"F/{period_name(game, league)}"
        return "F"
    if game.state == LIVE:
        if game.status_name == "STATUS_HALFTIME":
            return "Half"
        name = period_name(game, league)
        if game.status_name == "STATUS_END_PERIOD":
            return f"End {name}"
        if name == "SO":
            return name
        return f"{name} {game.clock}".strip()
    return kickoff_label(game)


def short_period(game: Game, league: League) -> str:
    """Period without the clock, for the menu bar: "Q3", "P2", "Half",
    "End P2", "OT"."""
    if game.state == LIVE and game.status_name not in ("STATUS_HALFTIME", "STATUS_END_PERIOD"):
        return period_name(game, league)
    return period_label(game, league)


def clock_seconds(game: Game) -> Optional[float]:
    """Game clock as seconds left in the period ("4:32" → 272, "38.5")."""
    try:
        if ":" in game.clock:
            minutes, seconds = game.clock.split(":", 1)
            return int(minutes) * 60 + float(seconds)
        return float(game.clock)
    except (TypeError, ValueError):
        return None


def is_crunch_time(game: Game, league: League) -> bool:
    """Close game late: last period (or OT), under 5:00, within 5 points."""
    if game.state != LIVE or game.away.score is None or game.home.score is None:
        return False
    if game.period < league.regulation_periods or game.status_name == "STATUS_END_PERIOD":
        return False
    left = clock_seconds(game)
    return left is not None and left <= 300 and abs(game.away.score - game.home.score) <= 5


def kickoff_label(game: Game, with_day: bool = True) -> str:
    """Local start time: "Sun 12:00 PM" ("TBD" if unknown)."""
    if not game.start:
        return "TBD"
    local = game.start.astimezone()
    return local.strftime("%a %-I:%M %p" if with_day else "%-I:%M %p")


def score_line(game: Game) -> str:
    """ "HOU 21 — #7 TEX 17" (away first)."""
    return (
        f"{game.away.label} {game.away.score if game.away.score is not None else 0} — "
        f"{game.home.label} {game.home.score if game.home.score is not None else 0}"
    )


def scoreboard_row(game: Game, league: League, favorite_ids: Collection[str] = ()) -> str:
    star = "⭐ " if any(game.involves(t) for t in favorite_ids) else ""
    if game.state in (LIVE, FINAL):
        return f"{star}{score_line(game)}   {period_label(game, league)}"
    return f"{star}{game.away.label} @ {game.home.label}   {period_label(game, league)}"


def result_for(game: Game, team_id: str) -> str:
    """ "W", "L", or "T" for a finished game from `team_id`'s side."""
    me, them = game.side_of(team_id), game.opponent_of(team_id)
    if not me or not them or me.score is None or them.score is None:
        return ""
    if me.score > them.score:
        return "W"
    return "L" if me.score < them.score else "T"


def status_lines(game: Optional[Game], team: TeamRef, league: League) -> List[str]:
    """The few lines that describe a favorite team's current game."""
    if game is None:
        return [f"No {team.short_name} game scheduled"]
    me, them = game.side_of(team.id), game.opponent_of(team.id)
    if me is None or them is None:
        return [f"No {team.short_name} game scheduled"]
    at = "@" if not me.home else "vs"
    matchup = f"{team.short_name} {at} {them.label if them.rank else them.team.short_name}"

    if game.state == LIVE:
        lines = [f"{score_line(game)}   {period_label(game, league)}"]
        if game.down_distance:
            ball = game.side_of(game.possession_id)
            who = f"{ball.team.abbr} ball · " if ball else ""
            zone = " · 🔴 Red zone" if game.red_zone else ""
            lines.append(f"{who}{game.down_distance}{zone}")
        if game.broadcast:
            lines.append(f"TV: {game.broadcast}")
        return lines
    if game.state == FINAL:
        result = result_for(game, team.id)
        lines = [f"Final: {score_line(game)}   ({result})" if result else f"Final: {score_line(game)}"]
        if me.record:
            lines.append(f"Record: {me.record}")
        return lines
    if game.state in (POSTPONED, CANCELED):
        return [f"{matchup} — {'Postponed' if game.state == POSTPONED else 'Canceled'}"]

    lines = [f"{matchup}  |  {kickoff_label(game)}"]
    records = " · ".join(
        f"{s.team.abbr} {s.record}" for s in (game.away, game.home) if s.record
    )
    if records:
        lines.append(records)
    if game.broadcast:
        lines.append(f"TV: {game.broadcast}")
    if game.venue:
        lines.append(f"📍 {game.venue}" + (f", {game.city}" if game.city else ""))
    return lines


def headline(game: Optional[Game], team: TeamRef, league: League) -> str:
    """One line for the top of the menu, or "" when there's nothing current."""
    if game is None:
        return ""
    them = game.opponent_of(team.id)
    if them is None:
        return ""
    if game.state == LIVE:
        return f"{league.emoji} {score_line(game)}   {period_label(game, league)}"
    if game.state == FINAL:
        result = result_for(game, team.id)
        return f"{league.emoji} Final: {score_line(game)}" + (f"  ({result})" if result else "")
    if game.state == PRE:
        at = "@" if game.side_of(team.id).home is False else "vs"
        return f"{league.emoji} {team.short_name} {at} {them.team.short_name}  |  {kickoff_label(game)}"
    return ""


def schedule_row(game: Game, team_id: str, league: League) -> str:
    """ "W 24-17  vs IND" for results, "Sun 9/28  @ JAX  12:00 PM" ahead."""
    me, them = game.side_of(team_id), game.opponent_of(team_id)
    if me is None or them is None:
        return ""
    at = "@" if not me.home else "vs"
    opp = them.label
    if game.state == FINAL and me.score is not None and them.score is not None:
        return f"{result_for(game, team_id)} {me.score}-{them.score}  {at} {opp}"
    if game.state in (POSTPONED, CANCELED):
        return f"{at} {opp}  {period_label(game, league)}"
    if not game.start:
        return f"TBD  {at} {opp}"
    local = game.start.astimezone()
    return f"{local.strftime('%a %-m/%-d')}  {at} {opp}  {local.strftime('%-I:%M %p')}"


def line_score_rows(game: Game, league: League) -> List[str]:
    """Monospace line score by period:

             1   2   3   4    T
        HOU  7   3  14   0   24
        JAX  0  10   0   7   17
    """
    n = max(league.regulation_periods, len(game.away.periods), len(game.home.periods))
    if not game.away.periods and not game.home.periods:
        return []
    def label(i: int) -> str:
        if i <= league.regulation_periods:
            return str(i)
        return period_name(dataclasses.replace(game, period=i), league)

    labels = [label(i) for i in range(1, n + 1)]
    width = max(len(game.away.team.abbr), len(game.home.team.abbr), 3) + 1

    def cells(side: Side) -> str:
        vals = side.periods + [None] * (n - len(side.periods))
        return " ".join(f"{'' if v is None else v:>3}" for v in vals)

    header = " " * width + " ".join(f"{label:>3}" for label in labels) + "     T"
    rows = [header]
    for side in (game.away, game.home):
        total = "" if side.score is None else side.score
        rows.append(f"{side.team.abbr:<{width}}{cells(side)}   {total:>3}")
    return rows
