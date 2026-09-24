import datetime as dt

import pytest

from sportsbar import espn
from sportsbar.models import CANCELED, FINAL, LIVE, POSTPONED, PRE
from tests.conftest import load_fixture

NFL = espn.LEAGUES["nfl"]
NCAAF = espn.LEAGUES["ncaaf"]
NOW = dt.datetime(2026, 9, 25, 0, 30, tzinfo=dt.timezone.utc)  # Thu 7:30 PM CT


def nfl_games():
    return espn.parse_games(load_fixture("espn_nfl_scoreboard.json"), "nfl")


def nfl_teams():
    return espn.parse_teams(load_fixture("espn_nfl_teams.json"), "nfl")


def ncaaf_teams():
    return espn.parse_teams(load_fixture("espn_ncaaf_teams.json"), "ncaaf")


def hou_schedule():
    return espn.parse_games(load_fixture("espn_nfl_schedule_hou.json"), "nfl")


def by_id(games, game_id):
    return next(g for g in games if g.id == game_id)


# --- fetching ---------------------------------------------------------------------

def test_fetch_urls(fake_api):
    espn.fetch_scoreboard(NFL)
    espn.fetch_teams(NCAAF)
    espn.fetch_scoreboard(NCAAF)
    espn.fetch_team_schedule(NFL, "34")
    urls = [u for u, _ in fake_api.calls]
    assert urls == [
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
        "https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams?limit=1000",
        "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=80&limit=300",
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/34/schedule",
    ]


def test_fetchers_swallow_errors(fake_api):
    fake_api.fail = True
    assert espn.fetch_teams(NFL) == []
    assert espn.fetch_scoreboard(NFL) == {}
    assert espn.fetch_team_schedule(NFL, "34") == {}


# --- teams --------------------------------------------------------------------------

def test_parse_teams():
    teams = nfl_teams()
    hou = next(t for t in teams if t.abbr == "HOU")
    assert (hou.id, hou.name, hou.short_name, hou.key) == ("34", "Houston Texans", "Texans", "nfl/HOU")


@pytest.mark.parametrize("ref", ["HOU", "hou", "34", "Houston Texans", "Texans", "Houston"])
def test_resolve_nfl_team(ref):
    assert espn.resolve_team(nfl_teams(), ref).id == "34"


@pytest.mark.parametrize("ref, team_id", [
    ("Texas", "251"),          # school name beats "Texas A&M"/"Texas Tech"
    ("TEX", "251"),
    ("Longhorns", "251"),
    ("Texas A&M", "245"),
    ("Houston", "248"),        # college Houston, not the Texans
])
def test_resolve_college_team(ref, team_id):
    assert espn.resolve_team(ncaaf_teams(), ref).id == team_id


def test_resolve_ambiguous_or_unknown(caplog):
    assert espn.resolve_team(ncaaf_teams(), "Tigers") is None  # LSU or Missouri?
    assert "ambiguous" in caplog.text
    assert espn.resolve_team(nfl_teams(), "New York") is None  # Giants or Jets?
    assert espn.resolve_team(nfl_teams(), "Isotopes") is None


# --- games ---------------------------------------------------------------------------

def test_parse_live_game():
    g = by_id(nfl_games(), "401800001")
    assert g.state == LIVE and g.period == 3 and g.clock == "4:12"
    assert (g.away.team.abbr, g.away.score, g.home.team.abbr, g.home.score) == ("HOU", 21, "JAX", 17)
    assert g.away.periods == [7, 7, 7] and g.home.periods == [3, 14, 0]
    assert g.away.record == "2-1"
    assert g.down_distance == "2nd & 7 at HOU 35" and g.possession_id == "30"
    assert g.broadcast == "Prime Video" and g.venue == "EverBank Stadium" and g.city == "Jacksonville"
    assert g.start == dt.datetime(2026, 9, 25, 0, 15, tzinfo=dt.timezone.utc)
    assert g.week == 4
    assert g.side_of("34") is g.away and g.opponent_of("34") is g.home
    assert g.involves("30") and not g.involves("12")


def test_parse_states():
    games = nfl_games()
    assert by_id(games, "401800002").state == FINAL
    assert by_id(games, "401800003").state == PRE
    assert by_id(games, "401800004").state == POSTPONED


def test_games_sorted_by_start():
    starts = [g.start for g in nfl_games()]
    assert starts == sorted(starts)


def test_schedule_scores_are_objects():
    games = hou_schedule()
    assert [(g.week, g.state) for g in games] == [
        (1, FINAL), (2, FINAL), (3, FINAL), (4, LIVE), (5, PRE), (7, PRE),
    ]
    assert (games[0].away.score, games[0].home.score) == (9, 14)


def test_parse_skips_malformed_events():
    data = {"events": [{"id": "1"}, {"id": "2", "competitions": [{"competitors": []}]}]}
    assert espn.parse_games(data, "nfl") == []


def test_ranks_only_top_25():
    games = espn.parse_games(load_fixture("espn_ncaaf_scoreboard.json"), "ncaaf")
    big = by_id(games, "401900001")
    assert (big.away.rank, big.home.rank) == (12, 7)
    assert big.away.label == "#12 UGA"
    assert by_id(games, "401900002").away.rank is None  # 99 = unranked


def test_canceled_status():
    data = load_fixture("espn_nfl_scoreboard.json")
    dal_nyg = next(e for e in data["events"] if e["id"] == "401800003")
    dal_nyg["competitions"][0]["status"]["type"]["name"] = "STATUS_CANCELED"
    assert by_id(espn.parse_games(data, "nfl"), "401800003").state == CANCELED


# --- featured game --------------------------------------------------------------------

def test_current_game_prefers_this_weeks_game():
    g = espn.current_game(nfl_games(), hou_schedule(), "34", NOW)
    assert g.id == "401800001" and g.state == LIVE


def test_current_game_bye_week_falls_back_to_schedule():
    week_without_hou = [g for g in nfl_games() if not g.involves("34")]
    g = espn.current_game(week_without_hou, hou_schedule(), "34", NOW)
    assert g.week == 5 and g.state == PRE


def test_current_game_none_when_season_over():
    past = [g for g in hou_schedule() if g.state == FINAL]
    assert espn.current_game([], past, "34", NOW) is None


# --- display ---------------------------------------------------------------------------

def test_period_labels(central_time):
    games = nfl_games()
    assert espn.period_label(by_id(games, "401800001"), NFL) == "Q3 4:12"
    assert espn.period_label(by_id(games, "401800002"), NFL) == "F/OT"
    assert espn.period_label(by_id(games, "401800003"), NFL) == "Sun 12:00 PM"
    assert espn.period_label(by_id(games, "401800004"), NFL) == "PPD"
    half = by_id(espn.parse_games(load_fixture("espn_ncaaf_scoreboard.json"), "ncaaf"), "401900002")
    assert espn.period_label(half, NCAAF) == "Half"


def test_period_labels_overtime_and_end_of_period():
    g = by_id(nfl_games(), "401800001")
    g.status_name, g.period = "STATUS_END_PERIOD", 2
    assert espn.period_label(g, NFL) == "End Q2"
    g.status_name, g.period, g.clock = "STATUS_IN_PROGRESS", 7, "0:00"
    assert espn.period_label(g, NCAAF) == "3OT 0:00"
    g.state = FINAL
    assert espn.period_label(g, NCAAF) == "F/3OT"


def test_scoreboard_rows(central_time):
    rows = [espn.scoreboard_row(g, NFL, {"34"}) for g in nfl_games()]
    assert rows == [
        "KC 27 — LV 24   F/OT",
        "⭐ HOU 21 — JAX 17   Q3 4:12",
        "DAL @ NYG   Sun 12:00 PM",
        "MIA @ BUF   PPD",
        "SF @ LAR   Mon 7:15 PM",
    ]


def test_college_rows_show_ranks(central_time):
    games = espn.parse_games(load_fixture("espn_ncaaf_scoreboard.json"), "ncaaf")
    assert espn.scoreboard_row(by_id(games, "401900001"), NCAAF) == "#12 UGA @ #7 TEX   Sat 7:30 PM"
    assert espn.scoreboard_row(by_id(games, "401900003"), NCAAF) == "RUTG 10 — #1 OSU 38   F"


def test_status_lines_live():
    team = next(t for t in nfl_teams() if t.abbr == "HOU")
    lines = espn.status_lines(by_id(nfl_games(), "401800001"), team, NFL)
    assert lines == [
        "HOU 21 — JAX 17   Q3 4:12",
        "JAX ball · 2nd & 7 at HOU 35",
        "TV: Prime Video",
    ]


def test_status_lines_pre_and_final(central_time):
    teams = {t.abbr: t for t in nfl_teams()}
    pre = espn.status_lines(by_id(nfl_games(), "401800003"), teams["NYG"], NFL)
    assert pre == [
        "Giants vs Cowboys  |  Sun 12:00 PM",
        "DAL 2-1 · NYG 0-3",
        "TV: FOX",
        "📍 MetLife Stadium, East Rutherford",
    ]
    final = espn.status_lines(by_id(nfl_games(), "401800002"), teams["LV"], NFL)
    assert final == ["Final: KC 27 — LV 24   (L)", "Record: 1-2"]
    assert espn.status_lines(None, teams["HOU"], NFL) == ["No Texans game scheduled"]


def test_headlines(central_time):
    teams = {t.abbr: t for t in nfl_teams()}
    games = nfl_games()
    assert espn.headline(by_id(games, "401800001"), teams["HOU"], NFL) == "🏈 HOU 21 — JAX 17   Q3 4:12"
    assert espn.headline(by_id(games, "401800002"), teams["KC"], NFL) == "🏈 Final: KC 27 — LV 24  (W)"
    assert espn.headline(by_id(games, "401800003"), teams["DAL"], NFL) == "🏈 Cowboys @ Giants  |  Sun 12:00 PM"
    assert espn.headline(None, teams["HOU"], NFL) == ""


def test_schedule_rows(central_time):
    rows = [espn.schedule_row(g, "34", NFL) for g in hou_schedule()]
    assert rows == [
        "L 9-14  @ LAR",
        "W 20-19  vs TB",
        "W 27-13  vs IND",
        "Thu 9/24  @ JAX  7:15 PM",
        "Sun 10/4  vs BAL  12:00 PM",
        "Sun 10/18  @ SEA  7:20 PM",
    ]


def test_line_score_rows():
    rows = espn.line_score_rows(by_id(nfl_games(), "401800002"), NFL)
    assert rows == [
        "      1   2   3   4  OT     T",
        "KC    7   3   7   7   3    27",
        "LV    0  14   3   7   0    24",
    ]
    assert len({len(r) for r in rows}) == 1
    live = espn.line_score_rows(by_id(nfl_games(), "401800001"), NFL)
    assert live[1] == "HOU   7   7   7        21"
    assert espn.line_score_rows(by_id(nfl_games(), "401800003"), NFL) == []


def test_ordinal():
    assert [espn.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]
