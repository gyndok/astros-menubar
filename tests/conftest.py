"""Shared fixtures.

The JSON files in tests/fixtures/ are hand-built to match the shape of the
MLB Stats API, The Odds API, and Open-Meteo responses, trimmed to the
fields the app actually reads. "Today" is frozen at 2026-09-24, when the
Astros are live at Seattle (HOU 3, SEA 2, bottom 7th).
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import sys
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import urlencode

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures"
FROZEN_NOW = dt.datetime(2026, 9, 24, 19, 30)  # local (Central) time


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, payload, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeAPI:
    """Stands in for requests.get, routing URLs to fixture files.

    Records every URL and the thread it was requested from, so tests can
    assert network I/O never happens on the main thread.
    """

    def __init__(self) -> None:
        self.routes: List[tuple] = [
            # ESPN (most specific first)
            ("/football/nfl/teams/", "espn_nfl_schedule_hou.json"),
            ("/football/nfl/teams", "espn_nfl_teams.json"),
            ("/football/nfl/scoreboard", "espn_nfl_scoreboard.json"),
            ("/football/college-football/teams/", {"events": []}),
            ("/football/college-football/teams", "espn_ncaaf_teams.json"),
            ("/football/college-football/scoreboard", "espn_ncaaf_scoreboard.json"),
            ("/basketball/nba/teams/", {"events": []}),
            ("/basketball/nba/teams", "espn_nba_teams.json"),
            ("/basketball/nba/scoreboard", "espn_nba_scoreboard.json"),
            ("/hockey/nhl/teams/", {"events": []}),
            ("/hockey/nhl/teams", "espn_nhl_teams.json"),
            ("/hockey/nhl/scoreboard", "espn_nhl_scoreboard.json"),
            # MLB and friends
            ("/feed/live", "feed_live.json"),
            ("/boxscore", "boxscore.json"),
            ("/standings", "standings.json"),
            ("group=hitting", "team_stats_hitting.json"),
            ("group=pitching&season", None),  # resolved below (team vs person)
            ("the-odds-api.com", "odds.json"),
            ("open-meteo.com", "weather.json"),
            ("schedule?sportId=1&teamId=", "schedule_team.json"),
            ("schedule?sportId=1&date=", "schedule_league.json"),
        ]
        self.overrides: dict = {}
        self.calls: List[tuple] = []  # (url, thread_name)
        self.fail: bool = False

    def resolve(self, url: str) -> Optional[str]:
        for needle, name in self.overrides.items():
            if needle in url:
                return name
        if "group=pitching" in url:
            return "pitcher_stats.json" if "/people/" in url else "team_stats_pitching.json"
        for needle, name in self.routes:
            if name and needle in url:
                return name
        return None

    def get(self, url: str, params: Optional[dict] = None,
            timeout: Optional[float] = None, **_kw):
        if params:
            url = f"{url}?{urlencode(params)}"
        self.calls.append((url, threading.current_thread().name))
        if self.fail:
            raise ConnectionError("network down")
        name = self.resolve(url)
        if name is None:
            return FakeResponse({}, 404)
        payload = load_fixture(name) if isinstance(name, str) else copy.deepcopy(name)
        return FakeResponse(payload)


@pytest.fixture
def fake_api(monkeypatch) -> FakeAPI:
    api = FakeAPI()
    import requests
    monkeypatch.setattr(requests, "get", api.get)
    return api


@pytest.fixture
def central_time(monkeypatch):
    """Run in US Central time so local-time formatting is deterministic."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset unavailable on this platform")
    monkeypatch.setenv("TZ", "America/Chicago")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture
def frozen_now(monkeypatch, central_time) -> Callable[[], dt.datetime]:
    """Freeze now_local() everywhere it's been imported."""
    now = lambda: FROZEN_NOW  # noqa: E731
    import sportsbar.config
    import sportsbar.mlb
    import sportsbar.weather
    for mod in (sportsbar.config, sportsbar.mlb, sportsbar.weather):
        monkeypatch.setattr(mod, "now_local", now)
    if "sportsbar.app" in sys.modules:
        monkeypatch.setattr(sys.modules["sportsbar.app"], "now_local", now)
    return now


@pytest.fixture
def config_dir(monkeypatch, tmp_path) -> Path:
    """Point config, cache, and log paths at a temp directory."""
    import sportsbar.config as config
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.yaml")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "LOG_PATH", tmp_path / "app.log")
    return tmp_path
