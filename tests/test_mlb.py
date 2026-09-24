import copy

import pytest

from sportsbar import mlb
from sportsbar.teams import AL_ID, NL_ID
from tests.conftest import load_fixture

HOU, SEA, TEX, LAD = 117, 136, 140, 119


def team_games():
    data = load_fixture("schedule_team.json")
    return [g for d in data["dates"] for g in d["games"]]


def league_games():
    data = load_fixture("schedule_league.json")
    return [g for d in data["dates"] for g in d["games"]]


def with_status(game, abstract, detailed):
    g = copy.deepcopy(game)
    g["status"] = {"abstractGameState": abstract, "detailedState": detailed}
    return g


# --- fetching ---------------------------------------------------------------

def test_fetch_schedule_flattens_dates(fake_api):
    games = mlb.fetch_schedule("2026-09-24", "2026-10-08", HOU)
    assert [g["gamePk"] for g in games] == [800001, 800002, 800003]
    url = fake_api.calls[0][0]
    assert "teamId=117" in url and "hydrate=probablePitcher,broadcasts" in url


def test_fetch_schedule_for_another_team(fake_api):
    mlb.fetch_schedule("2026-09-24", "2026-10-08", LAD)
    assert "teamId=119" in fake_api.calls[0][0]


def test_fetchers_swallow_network_errors(fake_api):
    fake_api.fail = True
    assert mlb.fetch_schedule("2026-09-24", "2026-10-08", HOU) == []
    assert mlb.fetch_live_game(800001) == {}
    assert mlb.fetch_boxscore(800001) == {}
    assert mlb.fetch_standings() == []
    assert mlb.fetch_team_stats(HOU) == {}
    assert mlb.fetch_pitcher_stats(1) == {}


def test_fetch_league_scores_uses_today(fake_api, frozen_now):
    games = mlb.fetch_league_scores()
    assert len(games) == 5
    assert "date=2026-09-24" in fake_api.calls[0][0]


def test_fetch_team_and_pitcher_stats(fake_api, frozen_now):
    stats = mlb.fetch_team_stats(HOU)
    assert "/teams/117/stats" in fake_api.calls[0][0]
    assert stats["hitting"]["homeRuns"] == 190
    assert stats["pitching"]["era"] == "3.71"
    assert mlb.fetch_pitcher_stats(664285)["era"] == "3.12"


# --- game state ---------------------------------------------------------------

def test_game_status_classification():
    game = team_games()[0]
    assert mlb._game_status(game) == "live"
    assert mlb._game_status(with_status(game, "Final", "Final")) == "final"
    assert mlb._game_status(with_status(game, "Preview", "Scheduled")) == "pre"
    assert mlb._game_status(with_status(game, "Live", "Warmup")) == "live"


def test_detect_game_state_live(frozen_now):
    state = mlb.detect_game_state(team_games())
    assert state["state"] == "live"
    assert state["game_pk"] == 800001


def test_detect_game_state_off_day(frozen_now):
    state = mlb.detect_game_state(team_games()[1:])  # nothing on 2026-09-24
    assert state == {"state": "off", "game": None, "game_pk": None}


def test_detect_game_state_ignores_postponed(frozen_now):
    ppd = with_status(team_games()[0], "Final", "Postponed")
    assert mlb.detect_game_state([ppd])["state"] == "off"


def test_detect_game_state_doubleheader_prefers_next_game(frozen_now):
    game1 = with_status(team_games()[0], "Final", "Final")
    game2 = with_status(team_games()[0], "Preview", "Scheduled")
    game2["gamePk"] = 800099
    state = mlb.detect_game_state([game1, game2])
    assert (state["state"], state["game_pk"]) == ("pre", 800099)
    # Both done → the last final
    game2 = with_status(game2, "Final", "Final")
    state = mlb.detect_game_state([game1, game2])
    assert (state["state"], state["game_pk"]) == ("final", 800099)


def test_sides_and_opponent():
    away_game, home_game = team_games()[0], team_games()[1]
    assert mlb.team_side(away_game, HOU) == "away"
    assert mlb.team_side(home_game, HOU) == "home"
    assert mlb.team_side(away_game, SEA) == "home"  # from Seattle's view
    assert mlb.other_side("away") == "home"
    assert mlb.opponent_team_id(away_game, HOU) == SEA
    assert mlb.opponent_team_id(home_game, HOU) == TEX
    assert mlb.opponent_team_id(away_game, SEA) == HOU


def test_nickname():
    assert mlb.nickname({"id": 111, "name": "Boston Red Sox"}) == "Red Sox"
    assert mlb.nickname({"id": 999, "name": "Some Team", "teamName": "Visitors"}) == "Visitors"
    assert mlb.nickname({"name": "Springfield Isotopes"}) == "Isotopes"


# --- display helpers ----------------------------------------------------------

def test_format_game_time_is_local(central_time):
    assert mlb.format_game_time(team_games()[0]) == "6:10 PM"
    assert mlb.format_game_time({}) == "TBD"
    assert mlb.format_game_time({"gameDate": "garbage"}) == "TBD"


def test_format_record_and_probables():
    game = team_games()[0]
    assert mlb.format_record(game, "away") == "88-67"
    assert mlb.get_probable_pitcher(game, "away") == {"name": "Framber Valdez", "id": 664285}
    assert mlb.get_probable_pitcher(team_games()[2], "away") == {"name": "TBD", "id": None}


def test_tv_broadcast_prefers_the_teams_own_network():
    games = team_games()
    # HOU @ SEA: each team sees its own network
    assert mlb.get_tv_broadcast(games[0], HOU) == "Space City Home Network"
    assert mlb.get_tv_broadcast(games[0], SEA) == "ROOT Sports NW"
    # No network of its own listed → national broadcast
    assert mlb.get_tv_broadcast(games[1], TEX) == "FS1"
    # Nothing specific → any TV; no TV at all → TBD
    only_root = copy.deepcopy(games[0])
    only_root["broadcasts"] = only_root["broadcasts"][:1]
    assert mlb.get_tv_broadcast(only_root, HOU) == "ROOT Sports NW"
    assert mlb.get_tv_broadcast(games[2], HOU) == "TBD"


def test_format_league_game_rows(central_time):
    live, final_extra, final_nine, upcoming, postponed = league_games()
    assert mlb.format_league_game(live, {HOU}) == "⭐ HOU 3 — SEA 2   ▼7"
    assert mlb.format_league_game(live) == "HOU 3 — SEA 2   ▼7"
    assert mlb.format_league_game(final_extra, {HOU, 111}) == "⭐ NYY 5 — BOS 4   F/10"
    assert mlb.format_league_game(final_extra, {HOU}) == "NYY 5 — BOS 4   F/10"
    assert mlb.format_league_game(final_nine) == "CHC 2 — STL 7   F"
    assert mlb.format_league_game(upcoming) == "SD @ LAD   9:10 PM"
    assert mlb.format_league_game(postponed) == "TEX @ LAA   PPD"


# --- live feed parsing --------------------------------------------------------

def test_parse_live_data():
    ld = mlb.parse_live_data(load_fixture("feed_live.json"))
    assert ld == {
        "away_abbr": "HOU", "home_abbr": "SEA",
        "away_runs": 3, "home_runs": 2,
        "inning": 7, "inning_ordinal": "7th", "half": "Bot",
        "balls": 2, "strikes": 1, "outs": 1,
        "pitcher": "Bryan Abreu", "batter": "Cal Raleigh",
        "runners": ["1st", "3rd"],
    }


def test_parse_live_data_empty_feed():
    ld = mlb.parse_live_data({})
    assert ld["away_runs"] == 0 and ld["runners"] == []


def test_parse_scoring_plays_marks_my_side():
    plays = mlb.parse_scoring_plays(load_fixture("feed_live.json"), "away")
    assert [(p["inning"], p["top"], p["mine"]) for p in plays] == [
        (2, True, True), (4, False, False), (5, False, False), (6, True, True),
    ]
    assert plays[-1]["away_score"] == 3 and plays[-1]["home_score"] == 2
    assert plays[0]["description"].startswith("Yainer Diaz homers")


def test_parse_scoring_plays_skips_bad_indexes():
    feed = load_fixture("feed_live.json")
    feed["liveData"]["plays"]["scoringPlays"] = [1, 99]
    assert len(mlb.parse_scoring_plays(feed, "away")) == 1


def test_line_score_live():
    ls = mlb.parse_line_score(load_fixture("feed_live.json"))
    assert ls["away"] == {"runs": 3, "hits": 7, "errors": 0}
    rows = mlb.format_line_score(ls, is_final=False)
    assert rows == [
        "      1  2  3  4  5  6  7  8  9    R  H  E",
        "HOU   0  1  0  0  0  2  0          3  7  0",
        "SEA   0  0  0  1  1  0             2  5  1",
    ]
    assert len({len(r) for r in rows}) == 1  # columns line up


def test_line_score_final_home_x():
    ls = mlb.parse_line_score(load_fixture("feed_final.json"))
    rows = mlb.format_line_score(ls, is_final=True)
    assert rows[2] == "HOU   0  0  0  0  2  0  1  0  X    3  7  0"


def test_line_score_empty_feed():
    assert mlb.parse_line_score({}) == {}


def test_parse_lineup():
    lineup = mlb.parse_lineup(load_fixture("boxscore.json"), HOU)
    assert len(lineup) == 9
    assert lineup[0] == {"name": "Jose Altuve", "position": "2B"}
    assert lineup[2] == {"name": "Yordan Alvarez", "position": "DH"}
    assert mlb.parse_lineup(load_fixture("boxscore.json"), 136) == []
    assert mlb.parse_lineup({}, HOU) == []


# --- standings / magic numbers ------------------------------------------------

@pytest.mark.parametrize("wins, rival_losses, expected", [
    (88, 69, 6), (100, 70, 0), (0, 0, 163),
])
def test_magic_number_vs(wins, rival_losses, expected):
    assert mlb.magic_number_vs(wins, rival_losses) == expected


def test_flatten_league_teams_only_al():
    teams = mlb.flatten_league_teams(load_fixture("standings.json")["records"], {200, 201, 202})
    assert len(teams) == 15
    hou = next(t for t in teams if t["id"] == 117)
    assert (hou["wins"], hou["losses"], hou["division_leader"]) == (88, 67, True)


def test_compute_magic_numbers():
    mn = mlb.compute_magic_numbers(load_fixture("standings.json")["records"], HOU, AL_ID)
    assert mn["wins"] == 88 and mn["losses"] == 67 and mn["remaining"] == 7
    assert mn["division"] == 5        # MLB's published number wins over our 6
    assert mn["playoffs"] == 3        # 6th-fewest losses among others: CLE (72)
    assert mn["wild_card"] == 3       # 4th-fewest among non-leaders: CLE (72)
    assert mn["top_seed"] == 10       # fewest losses: NYY (65)
    assert mn["league_rank"] == "3"
    assert not mn["division_eliminated"] and not mn["wc_eliminated"]


def test_compute_magic_numbers_falls_back_to_formula():
    records = load_fixture("standings.json")["records"]
    del records[0]["teamRecords"][0]["magicNumber"]
    assert mlb.compute_magic_numbers(records, HOU, AL_ID)["division"] == 6  # vs SEA (69 L)


def test_compute_magic_numbers_for_another_al_team():
    mn = mlb.compute_magic_numbers(load_fixture("standings.json")["records"], SEA, AL_ID)
    # SEA 86-69: division rival HOU (67 L) → 163-86-67 = 10
    assert mn["division"] == 10 and not mn["division_leader"]
    assert mn["games_back"] == "2.0"
    # Others' losses: NYY 65, TOR 66, HOU 67, DET 68, BOS 70, CLE 72 ...
    assert mn["playoffs"] == 163 - 86 - 72
    assert mn["top_seed"] == 163 - 86 - 65


def test_compute_magic_numbers_nl_team_uses_nl_standings():
    mn = mlb.compute_magic_numbers(load_fixture("standings.json")["records"], LAD, NL_ID)
    assert (mn["wins"], mn["losses"]) == (91, 64)
    assert mn["division"] == 163 - 91 - 69  # vs SD (69 L)
    # An AL team isn't in the NL race at all
    assert mlb.compute_magic_numbers(load_fixture("standings.json")["records"], HOU, NL_ID) == {}


def test_compute_magic_numbers_without_team():
    assert mlb.compute_magic_numbers([], HOU, AL_ID) == {}
