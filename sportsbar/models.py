"""League-neutral game model.

MLB keeps its own richer data (lineups, pitchers, magic numbers); the
leagues served by ESPN (NFL, college football — NBA and NHL next) are
parsed into these types so one set of menus, titles, and notifications
works for all of them.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import List, Optional

# Game.state values
PRE, LIVE, FINAL, POSTPONED, CANCELED = "pre", "live", "final", "postponed", "canceled"


@dataclass(frozen=True)
class TeamRef:
    """A team as a league's API identifies it."""
    league: str          # "nfl"
    id: str              # ESPN team id ("34")
    abbr: str            # "HOU"
    name: str            # "Houston Texans"
    short_name: str      # "Texans" (college: "Texas")
    location: str = ""   # "Houston"
    nickname: str = ""   # "Texans" (college: "Longhorns")

    @property
    def key(self) -> str:
        return f"{self.league}/{self.abbr}"


@dataclass
class Side:
    team: TeamRef
    home: bool
    score: Optional[int] = None
    record: str = ""                  # "2-1"
    rank: Optional[int] = None        # college poll rank, 1–25
    winner: Optional[bool] = None
    periods: List[Optional[int]] = field(default_factory=list)  # points by period

    @property
    def label(self) -> str:
        """Abbreviation with poll rank: "#7 TEX"."""
        return f"#{self.rank} {self.team.abbr}" if self.rank else self.team.abbr


@dataclass
class Game:
    league: str
    id: str
    start: Optional[dt.datetime]      # aware, UTC
    state: str                        # PRE / LIVE / FINAL / POSTPONED / CANCELED
    status_name: str                  # ESPN status, e.g. "STATUS_HALFTIME"
    detail: str                       # ESPN short detail, e.g. "4:12 - 3rd"
    period: int
    clock: str                        # "4:12"
    away: Side
    home: Side
    venue: str = ""
    city: str = ""
    indoor: Optional[bool] = None
    broadcast: str = ""
    week: Optional[int] = None
    season_type: Optional[int] = None  # 1 pre, 2 regular, 3 post
    down_distance: str = ""            # "2nd & 7 at HOU 35"
    possession_id: str = ""            # team id with the ball
    red_zone: bool = False
    last_play: str = ""

    def side_of(self, team_id: str) -> Optional[Side]:
        if self.away.team.id == team_id:
            return self.away
        if self.home.team.id == team_id:
            return self.home
        return None

    def opponent_of(self, team_id: str) -> Optional[Side]:
        if self.away.team.id == team_id:
            return self.home
        if self.home.team.id == team_id:
            return self.away
        return None

    def involves(self, team_id: str) -> bool:
        return self.side_of(team_id) is not None
