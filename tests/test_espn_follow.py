import datetime as dt

import pytest

from sportsbar.espn_follow import ESPNFollower
from tests.conftest import load_fixture

# Thu 2026-09-24, 7:30 PM CT — Texans @ Jaguars is live (Q3)
NOW = dt.datetime(2026, 9, 25, 0, 30, tzinfo=dt.timezone.utc)
PREFS = {"game_starting": True, "final_score": True, "scoring_plays": True}


@pytest.fixture
def follower(fake_api, config_dir):
    clock = {"now": NOW}
    f = ESPNFollower(now=lambda: clock["now"])
    f.clock = clock
    return f


def set_live_score(api, away, home, state="in", name="STATUS_IN_PROGRESS", period=3):
    board = load_fixture("espn_nfl_scoreboard.json")
    comp = board["events"][0]["competitions"][0]
    away_c = next(c for c in comp["competitors"] if c["homeAway"] == "away")
    home_c = next(c for c in comp["competitors"] if c["homeAway"] == "home")
    away_c["score"], home_c["score"] = str(away), str(home)
    comp["status"]["type"].update({"state": state, "name": name})
    comp["status"]["period"] = period
    api.overrides["/football/nfl/scoreboard"] = board


def test_resolves_and_features_current_games(follower, fake_api):
    follower.configure([("nfl", "HOU"), ("ncaaf", "Texas"), ("nfl", "Isotopes")])
    assert follower.refresh(PREFS, full=True) == []  # first look: no alerts
    hou, tex, bad = follower.followed
    assert hou.team.name == "Houston Texans" and hou.game.id == "401800001"
    assert tex.team.name == "Texas Longhorns" and tex.game.id == "401900001"
    assert bad.team is None and bad.unresolved and bad.game is None
    assert len(hou.schedule) == 6
    urls = [u for u, _ in fake_api.calls]
    assert any(u.endswith("/nfl/teams/34/schedule") for u in urls)
    assert any("/college-football/teams/251/schedule" in u for u in urls)


def test_team_list_is_cached_not_refetched(follower, fake_api):
    follower.configure([("nfl", "HOU")])
    follower.refresh(PREFS)
    fake_api.calls.clear()
    follower.refresh(PREFS)
    urls = [u for u, _ in fake_api.calls]
    assert not any(u.endswith("/nfl/teams") for u in urls)       # team list: weekly
    assert not any(u.endswith("/schedule") for u in urls)        # schedule: 2-hourly
    assert any(u.endswith("/nfl/scoreboard") for u in urls)      # scoreboard: every tick
    follower.clock["now"] = NOW + dt.timedelta(hours=3)
    fake_api.calls.clear()
    follower.refresh(PREFS)
    assert any(u.endswith("/schedule") for u, _ in fake_api.calls)


def test_cache_restores_state_on_launch(follower, fake_api, config_dir):
    follower.configure([("nfl", "HOU")])
    follower.refresh(PREFS, full=True)
    fake_api.fail = True
    fresh = ESPNFollower(now=lambda: NOW)
    fresh.configure([("nfl", "HOU")])
    fresh.load_cache()
    assert fresh.followed[0].team.abbr == "HOU"
    assert fresh.followed[0].game.id == "401800001"
    assert len(fresh.followed[0].schedule) == 6


def test_configure_keeps_state_for_existing_favorites(follower):
    follower.configure([("nfl", "HOU")])
    follower.refresh(PREFS)
    before = follower.followed[0]
    follower.configure([("ncaaf", "TEX"), ("nfl", "hou"), ("mlb", "HOU")])
    assert [f.league.key for f in follower.followed] == ["ncaaf", "nfl"]
    assert follower.followed[1] is before


def test_score_start_and_final_notifications(follower, fake_api):
    follower.configure([("nfl", "HOU")])
    set_live_score(fake_api, 0, 0, state="pre", name="STATUS_SCHEDULED", period=0)
    follower.refresh(PREFS)

    set_live_score(fake_api, 0, 0, period=1)
    assert follower.refresh(PREFS) == [("Game Starting", "Texans game is underway! HOU 0 — JAX 0")]

    set_live_score(fake_api, 7, 0, period=1)
    assert follower.refresh(PREFS) == [("Texans Score!", "HOU 7 — JAX 0   Q1 4:12")]

    set_live_score(fake_api, 7, 3, period=2)  # the other team scoring: quiet
    assert follower.refresh(PREFS) == []

    set_live_score(fake_api, 24, 17, state="post", name="STATUS_FINAL", period=4)
    assert follower.refresh(PREFS) == [("Final Score", "Texans 24, Jaguars 17 — W")]
    assert follower.title_candidate(follower.followed[0]).text == "🏈 24-17 F"
    follower.clock["now"] = NOW + dt.timedelta(minutes=31)
    assert follower.title_candidate(follower.followed[0]) is None


def test_notification_preferences_respected(follower, fake_api):
    follower.configure([("nfl", "HOU")])
    set_live_score(fake_api, 0, 0, period=1)
    follower.refresh(PREFS)
    set_live_score(fake_api, 7, 0, period=1)
    assert follower.refresh({"scoring_plays": False}) == []
    set_live_score(fake_api, 14, 0, period=2)
    assert follower.refresh({}) == []  # scoring alerts are opt-in


def test_kickoff_soon_notification_once(follower, fake_api):
    follower.configure([("nfl", "DAL")])
    follower.refresh(PREFS)
    kickoff = follower.followed[0].game.start
    follower.clock["now"] = kickoff - dt.timedelta(minutes=10)
    assert follower.refresh(PREFS) == [("Game Starting Soon", "Cowboys kick off in ~10 min!")]
    assert follower.refresh(PREFS) == []


def test_desired_interval(follower, fake_api):
    follower.configure([("nfl", "DAL")])       # Sunday game
    follower.refresh(PREFS)
    assert follower.desired_interval() == 1800
    follower.clock["now"] = follower.followed[0].game.start - dt.timedelta(hours=2)
    assert follower.desired_interval() == 900
    follower.clock["now"] = follower.followed[0].game.start - dt.timedelta(minutes=20)
    assert follower.desired_interval() == 60
    follower.configure([("nfl", "DAL"), ("nfl", "HOU")])  # HOU is live
    follower.refresh(PREFS)
    assert follower.desired_interval() == 60


def test_title_candidate_live(follower):
    follower.configure([("nfl", "JAX"), ("nfl", "HOU")])
    follower.refresh(PREFS)
    jax, hou = follower.followed
    assert follower.title_candidate(hou) == (0, "🏈 21-17 Q3", "green")
    assert follower.title_candidate(jax) == (0, "🏈 21-17 Q3", "red")


def test_links(follower):
    follower.configure([("nfl", "HOU"), ("ncaaf", "TEX")])
    follower.refresh(PREFS)
    assert follower.links() == [
        {"name": "Texans on ESPN", "url": "https://www.espn.com/nfl/team/_/id/34"},
        {"name": "Texas on ESPN", "url": "https://www.espn.com/college-football/team/_/id/251"},
    ]


def test_network_down_keeps_last_data(follower, fake_api):
    follower.configure([("nfl", "HOU")])
    follower.refresh(PREFS)
    fake_api.fail = True
    follower.refresh(PREFS, full=True)
    assert follower.followed[0].game.id == "401800001"
    assert len(follower.followed[0].schedule) == 6
