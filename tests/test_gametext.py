import copy

import pytest

from sportsbar import mlb
from sportsbar.gametext import generate_game_text
from tests.conftest import load_fixture


@pytest.fixture
def games(frozen_now):
    data = load_fixture("schedule_team.json")
    return [g for d in data["dates"] for g in d["games"]]


def finalize(game, astros, opp):
    g = copy.deepcopy(game)
    g["status"] = {"abstractGameState": "Final", "detailedState": "Final"}
    g["teams"]["away"]["score"] = astros  # Astros are away in game 0
    g["teams"]["home"]["score"] = opp
    return g


def test_off_day_mentions_next_opponent(games):
    text = generate_game_text({"state": "off", "game": None}, {}, games[1:])
    assert text.endswith("Next up: Texas Rangers.")


def test_pregame_mentions_opponent(games):
    text = generate_game_text({"state": "pre", "game": games[1]}, {}, games)
    assert "Rangers" in text


@pytest.mark.parametrize("astros, opp", [(5, 2), (1, 4), (3, 3)])
def test_final_includes_score(games, astros, opp):
    # Messages are picked at random — run enough to hit every template
    for _ in range(50):
        text = generate_game_text({"state": "final", "game": finalize(games[0], astros, opp)}, {}, games)
        assert str(astros) in text and str(opp) in text


def test_live_uses_live_score(games):
    live = mlb.parse_live_data(load_fixture("feed_live.json"))
    text = generate_game_text({"state": "live", "game": games[0]}, live, games)
    assert "3" in text and "2" in text


def test_live_before_feed_loads(games):
    text = generate_game_text({"state": "live", "game": games[0]}, {}, games)
    assert "still loading" in text
