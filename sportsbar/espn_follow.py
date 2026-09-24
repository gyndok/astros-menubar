"""Following favorite teams in ESPN leagues (NFL, college football, NBA, NHL).

`ESPNFollower` owns the per-team state: resolving config references to
ESPN teams, fetching scoreboards and schedules (on the worker thread),
picking each team's current game, and turning state changes into
notifications. It knows nothing about menus — the app renders from it.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from . import espn
from .config import read_cache, write_cache
from .espn import League
from .models import FINAL, LIVE, PRE, Game, TeamRef

TEAMS_TTL = dt.timedelta(days=7)
SCHEDULE_TTL = dt.timedelta(hours=2)
FINAL_HOLD = dt.timedelta(minutes=30)


class TitleCandidate(NamedTuple):
    rank: int      # 0 = live game, 1 = just-finished game
    text: str
    color: str     # green / red / yellow


@dataclass
class Followed:
    league: League
    ref: str                              # as written in the config
    team: Optional[TeamRef] = None        # once resolved against ESPN
    game: Optional[Game] = None           # the game to feature right now
    schedule: List[Game] = field(default_factory=list)
    schedule_fetched: Optional[dt.datetime] = None
    unresolved: bool = False              # ESPN has no such team
    # Change tracking for notifications
    seen_game_id: Optional[str] = None
    seen_state: Optional[str] = None
    seen_score: Optional[int] = None
    soon_notified: Optional[str] = None
    crunch_notified: Optional[str] = None
    final_until: Optional[dt.datetime] = None

    @property
    def label(self) -> str:
        return self.team.short_name if self.team else self.ref


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_ts(value) -> Optional[dt.datetime]:
    try:
        return dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


class ESPNFollower:
    def __init__(self, now: Optional[Callable[[], dt.datetime]] = None) -> None:
        self.now = now or _now
        self.followed: List[Followed] = []
        self.teams: Dict[str, List[TeamRef]] = {}
        self.teams_fetched: Dict[str, dt.datetime] = {}
        self.scoreboards: Dict[str, List[Game]] = {}

    # -- configuration ------------------------------------------------------------

    def configure(self, refs: List[Tuple[str, str]]) -> None:
        """Follow exactly these (league, team ref) favorites, in order,
        keeping state for ones already followed."""
        existing = {(f.league.key, f.ref.lower()): f for f in self.followed}
        followed = []
        for league_key, ref in refs:
            league = espn.LEAGUES.get(league_key)
            if league is None:
                continue
            f = existing.get((league_key, ref.lower())) or Followed(league, ref)
            followed.append(f)
        self.followed = followed

    def leagues(self) -> List[League]:
        seen: List[League] = []
        for f in self.followed:
            if f.league not in seen:
                seen.append(f.league)
        return seen

    def team_ids(self, league_key: str) -> List[str]:
        return [f.team.id for f in self.followed if f.team and f.league.key == league_key]

    # -- cache ------------------------------------------------------------------------

    def load_cache(self) -> None:
        """Populate from disk so menus fill instantly on launch."""
        for league in self.leagues():
            self._load_teams_cache(league)
            board = read_cache(f"espn_{league.key}_scoreboard")
            if board:
                self.scoreboards[league.key] = espn.parse_games(board, league.key)
        self._resolve_all()
        for f in self.followed:
            if f.team:
                sched = read_cache(f"espn_{f.league.key}_{f.team.id}_schedule")
                if sched:
                    f.schedule = espn.parse_games(sched, f.league.key)
            self._update_game(f, notify=False)

    def _load_teams_cache(self, league: League) -> None:
        if league.key in self.teams:
            return
        cached = read_cache(f"espn_{league.key}_teams")
        if cached.get("data"):
            self.teams[league.key] = espn.parse_teams(cached["data"], league.key)
            fetched = _parse_ts(cached.get("fetched"))
            if fetched:
                self.teams_fetched[league.key] = fetched

    # -- refresh (worker thread) -----------------------------------------------------

    def refresh(self, notifications: dict, full: bool = False) -> List[Tuple[str, str]]:
        """Fetch what's needed and update every followed team.

        Returns (title, message) notifications for state changes, filtered
        by the user's `notifications` preferences.
        """
        now = self.now()
        for league in self.leagues():
            self._ensure_teams(league, now)
        self._resolve_all()

        for league in self.leagues():
            data = espn.fetch_scoreboard(league)
            if data.get("events") is not None:
                self.scoreboards[league.key] = espn.parse_games(data, league.key)
                write_cache(f"espn_{league.key}_scoreboard", data)

        alerts: List[Tuple[str, str]] = []
        for f in self.followed:
            if not f.team:
                continue
            stale = f.schedule_fetched is None or now - f.schedule_fetched > SCHEDULE_TTL
            if full or stale:
                data = espn.fetch_team_schedule(f.league, f.team.id)
                if data.get("events") is not None:
                    f.schedule = espn.parse_games(data, f.league.key)
                    f.schedule_fetched = now
                    write_cache(f"espn_{f.league.key}_{f.team.id}_schedule", data)
            alerts.extend(self._update_game(f, notify=True))
        return [(t, m) for kind, t, m in alerts if notifications.get(kind, kind != "scoring_plays")]

    def _ensure_teams(self, league: League, now: dt.datetime) -> None:
        self._load_teams_cache(league)
        fetched = self.teams_fetched.get(league.key)
        needs_ref = any(f.team is None for f in self.followed if f.league is league)
        if league.key in self.teams and fetched and now - fetched < TEAMS_TTL and not needs_ref:
            return
        if league.key in self.teams and fetched and now - fetched < dt.timedelta(hours=1):
            return  # just fetched — an unknown name won't appear by retrying
        data = espn.fetch_teams(league)
        if data:
            self.teams[league.key] = data
            self.teams_fetched[league.key] = now
            write_cache(f"espn_{league.key}_teams", {
                "fetched": now.isoformat(),
                "data": {"sports": [{"leagues": [{"teams": [
                    {"team": {
                        "id": t.id, "abbreviation": t.abbr, "displayName": t.name,
                        "shortDisplayName": t.short_name, "location": t.location,
                        "name": t.nickname,
                    }} for t in data
                ]}]}]},
            })

    def _resolve_all(self) -> None:
        for f in self.followed:
            teams = self.teams.get(f.league.key)
            if f.team is None and teams:
                f.team = espn.resolve_team(teams, f.ref)
                f.unresolved = f.team is None
                if f.unresolved:
                    logging.warning("No %s team matches favorite %r", f.league.name, f.ref)

    def _update_game(self, f: Followed, notify: bool) -> List[Tuple[str, str, str]]:
        """Pick the featured game and diff it against what we saw last."""
        now = self.now()
        game = espn.current_game(self.scoreboards.get(f.league.key, []), f.schedule, f.team.id, now) \
            if f.team else None
        f.game = game
        alerts: List[Tuple[str, str, str]] = []
        if game is None:
            return alerts
        me, them = game.side_of(f.team.id), game.opponent_of(f.team.id)
        same_game = game.id == f.seen_game_id
        name = f.team.short_name

        if notify and same_game:
            if f.seen_state == PRE and game.state == LIVE:
                alerts.append(("game_starting", "Game Starting",
                               f"{name} game is underway! {espn.score_line(game)}"))
            if f.seen_state == LIVE and game.state == FINAL:
                f.final_until = now + FINAL_HOLD
                result = espn.result_for(game, f.team.id)
                alerts.append(("final_score", "Final Score",
                               f"{name} {me.score}, {them.team.short_name} {them.score}"
                               + (f" — {result}" if result else "")))
            if (f.league.score_alerts and game.state == LIVE and f.seen_score is not None
                    and me.score is not None and me.score > f.seen_score):
                alerts.append(("scoring_plays", f"{name} Score!",
                               f"{espn.score_line(game)}   {espn.period_label(game, f.league)}"))
        # Basketball: one "close game late" alert instead of every basket
        if (notify and not f.league.score_alerts and f.crunch_notified != game.id
                and espn.is_crunch_time(game, f.league)):
            f.crunch_notified = game.id
            alerts.append(("scoring_plays", "Crunch Time",
                           f"{espn.score_line(game)}   {espn.period_label(game, f.league)}"))
        if (notify and game.state == PRE and game.start and f.soon_notified != game.id
                and dt.timedelta(0) < game.start - now <= dt.timedelta(minutes=15)):
            f.soon_notified = game.id
            minutes = int((game.start - now).total_seconds() // 60)
            alerts.append(("game_starting", "Game Starting Soon",
                           f"{name} {f.league.start_verb} in ~{minutes} min!"))

        if not same_game:
            f.final_until = None
        f.seen_game_id, f.seen_state = game.id, game.state
        f.seen_score = me.score if game.state == LIVE else None
        return alerts

    # -- what the app shows ------------------------------------------------------------

    def desired_interval(self) -> int:
        """Seconds until the next primary refresh, given our teams' games."""
        now = self.now()
        interval = 1800
        for f in self.followed:
            g = f.game
            if g is None:
                continue
            if g.state == LIVE:
                return 60
            if g.state == PRE and g.start:
                until = g.start - now
                if until <= dt.timedelta(minutes=30):
                    interval = min(interval, 60)
                elif until <= dt.timedelta(hours=6):
                    interval = min(interval, 900)
        return interval

    def find(self, league_key: str, ref: str) -> Optional[Followed]:
        return next(
            (f for f in self.followed if f.league.key == league_key and f.ref.lower() == ref.lower()),
            None,
        )

    def title_candidate(self, f: Followed) -> Optional[TitleCandidate]:
        g = f.game
        if g is None or f.team is None:
            return None
        me, them = g.side_of(f.team.id), g.opponent_of(f.team.id)
        if me is None or them is None or me.score is None or them.score is None:
            return None
        color = "green" if me.score > them.score else ("red" if me.score < them.score else "yellow")
        score = f"{g.away.score}-{g.home.score}"
        if g.state == LIVE:
            label = espn.short_period(g, f.league)  # "Q3", "P2", "Half", "OT"
            return TitleCandidate(0, f"{f.league.emoji} {score} {label}", color)
        if g.state == FINAL and f.final_until and self.now() < f.final_until:
            return TitleCandidate(1, f"{f.league.emoji} {score} F", color)
        return None

    def links(self) -> List[dict]:
        return [
            {"name": f"{f.team.short_name} on ESPN", "url": f.league.team_url(f.team.id)}
            for f in self.followed if f.team
        ]
