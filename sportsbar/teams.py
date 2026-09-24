"""Team directory and favorite-team config.

Every league the app supports lists its teams here. Favorites in the
config file refer to teams by league plus any of: abbreviation, MLB team
id, full name, or nickname — e.g. ``{league: mlb, team: HOU}``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# MLB league / division ids (MLB Stats API)
AL_ID, NL_ID = 103, 104
DIVISION_NAMES: Dict[int, str] = {
    201: "AL East", 202: "AL Central", 200: "AL West",
    204: "NL East", 205: "NL Central", 203: "NL West",
}
LEAGUE_DIVISIONS: Dict[int, Tuple[int, ...]] = {
    AL_ID: (201, 202, 200),
    NL_ID: (204, 205, 203),
}
LEAGUE_ABBR: Dict[int, str] = {AL_ID: "AL", NL_ID: "NL"}

DEFAULT_FAVORITES = [{"league": "mlb", "team": "HOU"}]

# Leagues favorites can name. MLB teams are listed below; ESPN leagues'
# teams are looked up from ESPN at runtime (see espn.py).
ESPN_LEAGUES = ("nfl", "ncaaf", "nba", "nhl")
SUPPORTED_LEAGUES = ("mlb",) + ESPN_LEAGUES
LEAGUE_ALIASES = {
    "baseball": "mlb",
    "football": "nfl",
    "college-football": "ncaaf", "college football": "ncaaf",
    "cfb": "ncaaf", "ncaa": "ncaaf", "ncaafb": "ncaaf",
    "basketball": "nba",
    "hockey": "nhl",
}


def league_key(value) -> str:
    """Normalize a config league name ("NFL", "college-football") → key."""
    name = str(value if value is not None else "mlb").strip().lower()
    return LEAGUE_ALIASES.get(name, name)


@dataclass(frozen=True)
class Team:
    league: str          # "mlb"
    id: int              # MLB Stats API team id
    abbr: str            # "HOU"
    name: str            # "Houston Astros"
    nickname: str        # "Astros"
    league_id: int       # 103 (AL) / 104 (NL)
    division_id: int     # 200 (AL West) ...
    venue: str           # home ballpark
    lat: float
    lon: float
    slug: str            # mlb.com/<slug>
    aliases: Tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.league}/{self.abbr}"

    @property
    def division(self) -> str:
        return DIVISION_NAMES.get(self.division_id, "")

    @property
    def league_abbr(self) -> str:
        return LEAGUE_ABBR.get(self.league_id, "")

    @property
    def site_url(self) -> str:
        return f"https://www.mlb.com/{self.slug}"

    @property
    def schedule_url(self) -> str:
        return f"https://www.mlb.com/{self.slug}/schedule"


def _mlb(id_, abbr, name, nickname, div, venue, lat, lon, slug, aliases=()):
    league_id = AL_ID if div in LEAGUE_DIVISIONS[AL_ID] else NL_ID
    return Team("mlb", id_, abbr, name, nickname, league_id, div, venue, lat, lon, slug, tuple(aliases))


MLB_TEAMS: List[Team] = [
    # AL East
    _mlb(110, "BAL", "Baltimore Orioles", "Orioles", 201, "Oriole Park at Camden Yards", 39.2838, -76.6218, "orioles"),
    _mlb(111, "BOS", "Boston Red Sox", "Red Sox", 201, "Fenway Park", 42.3467, -71.0972, "redsox"),
    _mlb(147, "NYY", "New York Yankees", "Yankees", 201, "Yankee Stadium", 40.8296, -73.9262, "yankees"),
    _mlb(139, "TB", "Tampa Bay Rays", "Rays", 201, "Tropicana Field", 27.7682, -82.6534, "rays", ["TBR"]),
    _mlb(141, "TOR", "Toronto Blue Jays", "Blue Jays", 201, "Rogers Centre", 43.6414, -79.3894, "bluejays"),
    # AL Central
    _mlb(145, "CWS", "Chicago White Sox", "White Sox", 202, "Rate Field", 41.8299, -87.6338, "whitesox", ["CHW"]),
    _mlb(114, "CLE", "Cleveland Guardians", "Guardians", 202, "Progressive Field", 41.4958, -81.6853, "guardians"),
    _mlb(116, "DET", "Detroit Tigers", "Tigers", 202, "Comerica Park", 42.3390, -83.0485, "tigers"),
    _mlb(118, "KC", "Kansas City Royals", "Royals", 202, "Kauffman Stadium", 39.0517, -94.4803, "royals", ["KCR"]),
    _mlb(142, "MIN", "Minnesota Twins", "Twins", 202, "Target Field", 44.9818, -93.2775, "twins"),
    # AL West
    _mlb(117, "HOU", "Houston Astros", "Astros", 200, "Daikin Park", 29.7573, -95.3555, "astros"),
    _mlb(108, "LAA", "Los Angeles Angels", "Angels", 200, "Angel Stadium", 33.8003, -117.8827, "angels", ["ANA"]),
    _mlb(133, "ATH", "Athletics", "Athletics", 200, "Sutter Health Park", 38.5806, -121.5083, "athletics", ["OAK", "A's"]),
    _mlb(136, "SEA", "Seattle Mariners", "Mariners", 200, "T-Mobile Park", 47.5914, -122.3325, "mariners"),
    _mlb(140, "TEX", "Texas Rangers", "Rangers", 200, "Globe Life Field", 32.7512, -97.0832, "rangers"),
    # NL East
    _mlb(144, "ATL", "Atlanta Braves", "Braves", 204, "Truist Park", 33.8908, -84.4678, "braves"),
    _mlb(146, "MIA", "Miami Marlins", "Marlins", 204, "loanDepot park", 25.7781, -80.2196, "marlins"),
    _mlb(121, "NYM", "New York Mets", "Mets", 204, "Citi Field", 40.7571, -73.8458, "mets"),
    _mlb(143, "PHI", "Philadelphia Phillies", "Phillies", 204, "Citizens Bank Park", 39.9061, -75.1665, "phillies"),
    _mlb(120, "WSH", "Washington Nationals", "Nationals", 204, "Nationals Park", 38.8730, -77.0074, "nationals", ["WAS", "WSN"]),
    # NL Central
    _mlb(112, "CHC", "Chicago Cubs", "Cubs", 205, "Wrigley Field", 41.9484, -87.6553, "cubs"),
    _mlb(113, "CIN", "Cincinnati Reds", "Reds", 205, "Great American Ball Park", 39.0974, -84.5082, "reds"),
    _mlb(158, "MIL", "Milwaukee Brewers", "Brewers", 205, "American Family Field", 43.0280, -87.9712, "brewers"),
    _mlb(134, "PIT", "Pittsburgh Pirates", "Pirates", 205, "PNC Park", 40.4469, -80.0057, "pirates"),
    _mlb(138, "STL", "St. Louis Cardinals", "Cardinals", 205, "Busch Stadium", 38.6226, -90.1928, "cardinals"),
    # NL West
    _mlb(109, "AZ", "Arizona Diamondbacks", "D-backs", 203, "Chase Field", 33.4455, -112.0667, "dbacks", ["ARI", "Diamondbacks"]),
    _mlb(115, "COL", "Colorado Rockies", "Rockies", 203, "Coors Field", 39.7561, -104.9942, "rockies"),
    _mlb(119, "LAD", "Los Angeles Dodgers", "Dodgers", 203, "Dodger Stadium", 34.0739, -118.2400, "dodgers"),
    _mlb(135, "SD", "San Diego Padres", "Padres", 203, "Petco Park", 32.7076, -117.1570, "padres", ["SDP"]),
    _mlb(137, "SF", "San Francisco Giants", "Giants", 203, "Oracle Park", 37.7786, -122.3893, "giants", ["SFG"]),
]

TEAMS: Dict[str, List[Team]] = {"mlb": MLB_TEAMS}
MLB_BY_ID: Dict[int, Team] = {t.id: t for t in MLB_TEAMS}


def find_team(league: str, ref) -> Optional[Team]:
    """Look up a team by abbreviation, id, alias, full name, or nickname."""
    teams = TEAMS.get(str(league).lower(), [])
    if isinstance(ref, int) or (isinstance(ref, str) and ref.strip().isdigit()):
        return next((t for t in teams if t.id == int(ref)), None)
    needle = str(ref).strip().lower()
    for t in teams:
        names = (t.abbr, t.name, t.nickname) + t.aliases
        if needle in (n.lower() for n in names):
            return t
    return None


def _raw_favorites(config: dict) -> list:
    raw = config.get("favorites")
    return raw if isinstance(raw, list) else DEFAULT_FAVORITES


def favorite_refs(config: dict) -> List[Tuple[str, str]]:
    """Every supported favorite as (league, team reference), in order.

    Leagues the app doesn't support yet are ignored (kept in the file) so a
    config written for a newer version doesn't break this one.
    """
    refs: List[Tuple[str, str]] = []
    for entry in _raw_favorites(config):
        if not isinstance(entry, dict) or "team" not in entry:
            continue
        league = league_key(entry.get("league"))
        if league not in SUPPORTED_LEAGUES:
            continue
        ref = (league, str(entry["team"]).strip())
        if ref not in refs:
            refs.append(ref)
    return refs


def follows_league(config: dict, league: str) -> bool:
    return any(lg == league for lg, _ in favorite_refs(config))


def remove_league_favorites(config: dict, league: str) -> None:
    """Stop following every team in `league`."""
    config["favorites"] = [
        f for f in _raw_favorites(config)
        if not (isinstance(f, dict) and league_key(f.get("league")) == league)
    ]


def favorite_teams(config: dict) -> List[Team]:
    """Resolve the config's MLB favorites, in order, skipping bad entries."""
    result: List[Team] = []
    for entry in _raw_favorites(config):
        if not isinstance(entry, dict) or "team" not in entry:
            logging.warning("Ignoring malformed favorite: %r", entry)
            continue
        league = league_key(entry.get("league"))
        if league not in TEAMS:
            continue
        team = find_team(league, entry["team"])
        if team is None:
            logging.warning("Unknown %s team in favorites: %r", league, entry["team"])
        elif team not in result:
            result.append(team)
    return result


def primary_team(config: dict, league: str = "mlb") -> Team:
    """The team the app follows for `league`: the first favorite in it."""
    for team in favorite_teams(config):
        if team.league == league:
            return team
    return find_team(DEFAULT_FAVORITES[0]["league"], DEFAULT_FAVORITES[0]["team"])


def set_primary_team(config: dict, team: Team) -> None:
    """Make `team` the first favorite in its league, keeping the others."""
    raw = config.get("favorites")
    favorites = [f for f in raw if isinstance(f, dict)] if isinstance(raw, list) else []
    favorites = [
        f for f in favorites
        if not (league_key(f.get("league")) == team.league
                and find_team(team.league, f.get("team", "")) == team)
    ]
    entry = {"league": team.league, "team": team.abbr}
    idx = next(
        (i for i, f in enumerate(favorites) if league_key(f.get("league")) == team.league),
        None,
    )
    if idx is None:
        favorites.append(entry)
    else:
        favorites[idx] = entry  # replaces the old primary team for that league
    config["favorites"] = favorites
