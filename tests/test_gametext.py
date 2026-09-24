import copy

import pytest

from sportsbar import mlb
from sportsbar.gametext import GENERIC, TEAM_FLAVOR, generate_game_text
from sportsbar.teams import find_team
from tests.conftest import load_fixture

HOU = find_team("mlb", "HOU")
SEA = find_team("mlb", "SEA")


@pytest.fixture
def games(frozen_now):
    data = load_fixture("schedule_team.json")
    return [g for d in data["dates"] for g in d["games"]]


def finalize(game, away, home):
    g = copy.deepcopy(game)
    g["status"] = {"abstractGameState": "Final", "detailedState": "Final"}
    g["teams"]["away"]["score"] = away
    g["teams"]["home"]["score"] = home
    return g


def many(fn, n=60):
    """Messages are random — collect enough to see every template."""
    return {fn() for _ in range(n)}


def test_off_day_mentions_next_opponent(games):
    text = generate_game_text({"state": "off", "game": None}, {}, games[1:], HOU)
    assert text.endswith("Next up: Texas Rangers.")


def test_pregame_mentions_opponent(games):
    for text in many(lambda: generate_game_text({"state": "pre", "game": games[1]}, {}, games, HOU)):
        assert "Rangers" in text or "Hunter Brown" in text


@pytest.mark.parametrize("away, home", [(5, 2), (1, 4), (3, 3)])
def test_final_includes_score(games, away, home):
    game = finalize(games[0], away, home)
    for text in many(lambda: generate_game_text({"state": "final", "game": game}, {}, games, HOU)):
        assert str(away) in text and str(home) in text


def test_live_uses_live_score(games):
    live = mlb.parse_live_data(load_fixture("feed_live.json"))
    text = generate_game_text({"state": "live", "game": games[0]}, live, games, HOU)
    assert "3" in text and "2" in text


def test_live_before_feed_loads(games):
    text = generate_game_text({"state": "live", "game": games[0]}, {}, games, HOU)
    assert "still loading" in text


def test_other_team_gets_its_own_name_and_no_astros_lines(games):
    """Same HOU @ SEA game, from the Mariners' side: SEA won 5-2."""
    game = finalize(games[0], 2, 5)
    texts = many(lambda: generate_game_text({"state": "final", "game": game}, {}, games, SEA))
    expected = {
        t.format(team="Mariners", opp="Astros", us=5, them=2) for t in GENERIC["win"]
    }
    assert texts == expected  # every generic win line, and nothing else


def test_astros_flavor_lines_still_appear_for_houston(games):
    game = finalize(games[0], 5, 2)
    texts = many(lambda: generate_game_text({"state": "final", "game": game}, {}, games, HOU), n=200)
    assert any("SHOOT IT HOUSTON TEXAS" in t for t in texts)


def test_all_templates_format():
    fields = dict(team="Astros", opp="Rangers", time="7:10 PM", sp="Hunter Brown",
                  us=3, them=2, deficit=1, inning="7th", half="Bot", batter="Altuve")
    pools = list(GENERIC.values()) + [p for f in TEAM_FLAVOR.values() for p in f.values()]
    for pool in pools:
        for template in pool:
            template.format(**fields)  # raises on a typo'd placeholder
    for flavor in TEAM_FLAVOR.values():
        assert set(flavor) <= set(GENERIC)
