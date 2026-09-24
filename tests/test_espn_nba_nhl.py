"""NBA and NHL: the same ESPN parsing, with each sport's own rules."""

import dataclasses
import datetime as dt

import pytest

from sportsbar import espn
from sportsbar.espn_follow import ESPNFollower
from sportsbar.models import FINAL, LIVE, PRE
from tests.conftest import load_fixture

NBA = espn.LEAGUES["nba"]
NHL = espn.LEAGUES["nhl"]
NOW = dt.datetime(2026, 9, 25, 0, 30, tzinfo=dt.timezone.utc)  # Thu 7:30 PM CT
PREFS = {"game_starting": True, "final_score": True, "scoring_plays": True}


def games(league):
    return espn.parse_games(load_fixture(f"espn_{league}_scoreboard.json"), league)


def by_id(gs, game_id):
    return next(g for g in gs if g.id == game_id)


def test_fetch_urls(fake_api):
    espn.fetch_scoreboard(NBA)
    espn.fetch_scoreboard(NHL)
    assert [u for u, _ in fake_api.calls] == [
        "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
        "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    ]
    assert NHL.team_url("25") == "https://www.espn.com/nhl/team/_/id/25"


def test_nba_labels(central_time):
    gs = games("nba")
    live = by_id(gs, "401810001")
    assert (live.state, espn.period_label(live, NBA), espn.short_period(live, NBA)) == (LIVE, "Q4 4:32", "Q4")
    assert espn.period_label(by_id(gs, "401810002"), NBA) == "F/OT"
    assert espn.period_label(by_id(gs, "401810003"), NBA) == "Thu 8:30 PM"


def test_nhl_labels():
    gs = games("nhl")
    live = by_id(gs, "401820001")
    assert espn.period_label(live, NHL) == "P2 8:31"
    assert espn.short_period(live, NHL) == "P2"
    end_of_first = by_id(gs, "401820003")
    assert espn.period_label(end_of_first, NHL) == "End P1"
    assert espn.short_period(end_of_first, NHL) == "End P1"
    assert espn.period_label(by_id(gs, "401820002"), NHL) == "F/SO"


def test_nhl_overtime_vs_shootout():
    game = by_id(games("nhl"), "401820001")
    ot = dataclasses.replace(game, period=4, clock="3:10")
    assert espn.period_label(ot, NHL) == "OT 3:10"
    shootout = dataclasses.replace(game, period=5, clock="0:00")
    assert espn.period_label(shootout, NHL) == "SO"
    playoffs = dataclasses.replace(game, period=5, clock="12:00", season_type=3)
    assert espn.period_label(playoffs, NHL) == "2OT 12:00"  # no shootouts in the playoffs
    final_2ot = dataclasses.replace(playoffs, state=FINAL)
    assert espn.period_label(final_2ot, NHL) == "F/2OT"


def test_nhl_line_score_labels():
    rows = espn.line_score_rows(by_id(games("nhl"), "401820002"), NHL)
    assert rows[0] == "      1   2   3  OT  SO     T"
    assert rows[1] == "EDM   1   0   1   0   1     3"


def test_nba_line_score_with_overtime():
    rows = espn.line_score_rows(by_id(games("nba"), "401810002"), NBA)
    assert rows[0] == "      1   2   3   4  OT     T"
    assert rows[1] == "BOS  30  28  25  27  10   120"


@pytest.mark.parametrize("period, clock, away, home, expected", [
    (4, "4:32", 98, 96, True),     # the fixture: 2-point game, 4:32 left
    (4, "5:01", 98, 96, False),    # not quite late enough
    (4, "38.5", 98, 93, True),     # sub-minute clock, 5-point game
    (4, "38.5", 98, 92, False),    # 6-point game
    (4, "2:00", 110, 96, False),   # blowout
    (3, "2:00", 98, 96, False),    # too early
    (5, "3:00", 104, 104, True),   # overtime counts
])
def test_crunch_time(period, clock, away, home, expected):
    game = by_id(games("nba"), "401810001")
    game = dataclasses.replace(
        game, period=period, clock=clock,
        away=dataclasses.replace(game.away, score=away),
        home=dataclasses.replace(game.home, score=home),
    )
    assert espn.is_crunch_time(game, NBA) is expected


def test_crunch_time_not_between_periods():
    game = dataclasses.replace(by_id(games("nba"), "401810001"), status_name="STATUS_END_PERIOD")
    assert not espn.is_crunch_time(game, NBA)


# --- follower -----------------------------------------------------------------------

@pytest.fixture
def follower(fake_api, config_dir):
    clock = {"now": NOW}
    f = ESPNFollower(now=lambda: clock["now"])
    f.clock = clock
    return f


def set_nba_score(api, away, home, clock="4:32", period=4):
    board = load_fixture("espn_nba_scoreboard.json")
    comp = board["events"][0]["competitions"][0]
    next(c for c in comp["competitors"] if c["homeAway"] == "away")["score"] = str(away)
    next(c for c in comp["competitors"] if c["homeAway"] == "home")["score"] = str(home)
    comp["status"]["displayClock"], comp["status"]["period"] = clock, period
    api.overrides["/basketball/nba/scoreboard"] = board


def test_basketball_alerts_crunch_time_once_not_every_basket(follower, fake_api):
    follower.configure([("nba", "Rockets")])
    set_nba_score(fake_api, 90, 80, clock="8:00")
    follower.refresh(PREFS)
    set_nba_score(fake_api, 92, 88, clock="6:10")  # Rockets score: no alert
    assert follower.refresh(PREFS) == []
    set_nba_score(fake_api, 94, 92, clock="4:32")  # close and late
    assert follower.refresh(PREFS) == [("Crunch Time", "HOU 94 — LAL 92   Q4 4:32")]
    set_nba_score(fake_api, 96, 95, clock="2:00")
    assert follower.refresh(PREFS) == []  # once per game


def test_crunch_time_respects_the_scoring_toggle(follower, fake_api):
    follower.configure([("nba", "HOU")])
    set_nba_score(fake_api, 90, 80, clock="8:00")
    follower.refresh(PREFS)
    set_nba_score(fake_api, 94, 92, clock="4:32")
    assert follower.refresh({"scoring_plays": False}) == []


def test_hockey_goal_alert(follower, fake_api):
    follower.configure([("nhl", "Stars")])
    follower.refresh(PREFS)
    board = load_fixture("espn_nhl_scoreboard.json")
    comp = board["events"][0]["competitions"][0]
    next(c for c in comp["competitors"] if c["homeAway"] == "away")["score"] = "3"
    fake_api.overrides["/hockey/nhl/scoreboard"] = board
    assert follower.refresh(PREFS) == [("Stars Score!", "DAL 3 — CHI 1   P2 8:31")]
    assert follower.title_candidate(follower.followed[0]).text == "🏒 3-1 P2"


def test_start_verbs(follower, fake_api):
    follower.configure([("nba", "Mavericks")])
    follower.refresh(PREFS)
    game = follower.followed[0].game
    assert game.state == PRE
    follower.clock["now"] = game.start - dt.timedelta(minutes=12)
    assert follower.refresh(PREFS) == [("Game Starting Soon", "Mavericks tip off in ~12 min!")]
    assert espn.LEAGUES["nhl"].start_verb == "drop the puck"


def test_resolve_by_nickname_across_leagues(follower):
    follower.configure([("nba", "Rockets"), ("nhl", "Golden Knights"), ("nba", "LA")])
    follower.refresh(PREFS)
    rockets, knights, clippers = follower.followed
    assert rockets.team.name == "Houston Rockets"
    assert knights.team.abbr == "VGK"
    assert clippers.team.abbr == "LAC"
