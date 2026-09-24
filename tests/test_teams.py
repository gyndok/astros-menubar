import pytest

from sportsbar import teams
from sportsbar.teams import MLB_TEAMS, find_team, favorite_teams, primary_team, set_primary_team


def test_thirty_mlb_teams_five_per_division():
    assert len(MLB_TEAMS) == 30
    assert len({t.id for t in MLB_TEAMS}) == 30
    assert len({t.abbr for t in MLB_TEAMS}) == 30
    for div_id in teams.DIVISION_NAMES:
        assert len([t for t in MLB_TEAMS if t.division_id == div_id]) == 5


@pytest.mark.parametrize("team_id, abbr, venue", [
    # Ids the old ballpark-weather table had mapped to the wrong park
    (108, "LAA", "Angel Stadium"),
    (109, "AZ", "Chase Field"),
    (113, "CIN", "Great American Ball Park"),
    (114, "CLE", "Progressive Field"),
    (115, "COL", "Coors Field"),
    (116, "DET", "Comerica Park"),
    (120, "WSH", "Nationals Park"),
    (121, "NYM", "Citi Field"),
    (143, "PHI", "Citizens Bank Park"),
    (144, "ATL", "Truist Park"),
    (145, "CWS", "Rate Field"),
    (146, "MIA", "loanDepot park"),
    (158, "MIL", "American Family Field"),
    (117, "HOU", "Daikin Park"),
])
def test_team_ids_match_mlb_stats_api(team_id, abbr, venue):
    team = teams.MLB_BY_ID[team_id]
    assert (team.abbr, team.venue) == (abbr, venue)


def test_leagues_follow_divisions():
    hou = find_team("mlb", "HOU")
    assert (hou.league_id, hou.league_abbr, hou.division) == (teams.AL_ID, "AL", "AL West")
    lad = find_team("mlb", "LAD")
    assert (lad.league_abbr, lad.division) == ("NL", "NL West")


@pytest.mark.parametrize("ref", ["HOU", "hou", 117, "117", "Houston Astros", "astros", " Astros "])
def test_find_team_accepts_many_forms(ref):
    assert find_team("mlb", ref).id == 117


@pytest.mark.parametrize("ref, abbr", [("ARI", "AZ"), ("OAK", "ATH"), ("CHW", "CWS"), ("Diamondbacks", "AZ")])
def test_find_team_aliases(ref, abbr):
    assert find_team("mlb", ref).abbr == abbr


def test_find_team_unknown():
    assert find_team("mlb", "Springfield Isotopes") is None
    assert find_team("nfl", "HOU") is None  # league not supported yet
    assert find_team("mlb", 999) is None


def test_urls():
    team = find_team("mlb", "BOS")
    assert team.site_url == "https://www.mlb.com/redsox"
    assert team.schedule_url == "https://www.mlb.com/redsox/schedule"
    assert team.key == "mlb/BOS"


def test_favorites_default_to_astros():
    assert [t.abbr for t in favorite_teams({})] == ["HOU"]
    assert primary_team({}).abbr == "HOU"
    assert primary_team({"favorites": "garbage"}).abbr == "HOU"


def test_favorites_keep_order_and_skip_bad_entries(caplog):
    config = {"favorites": [
        {"league": "nfl", "team": "HOU"},       # future league: ignored quietly
        {"league": "mlb", "team": "Isotopes"},  # unknown: warned
        "HOU",                                  # malformed: warned
        {"league": "mlb", "team": "SEA"},
        {"team": "LAD"},                        # league defaults to mlb
        {"league": "mlb", "team": "seattle mariners"},  # duplicate
    ]}
    assert [t.abbr for t in favorite_teams(config)] == ["SEA", "LAD"]
    assert primary_team(config).abbr == "SEA"
    assert "Isotopes" in caplog.text


def test_primary_team_falls_back_when_no_mlb_favorite():
    assert primary_team({"favorites": [{"league": "nfl", "team": "HOU"}]}).abbr == "HOU"


def test_set_primary_team_replaces_old_primary_keeps_others():
    config = {"favorites": [
        {"league": "nfl", "team": "HOU"},
        {"league": "mlb", "team": "HOU"},
        {"league": "mlb", "team": "LAD"},
    ]}
    set_primary_team(config, find_team("mlb", "SEA"))
    assert config["favorites"] == [
        {"league": "nfl", "team": "HOU"},
        {"league": "mlb", "team": "SEA"},
        {"league": "mlb", "team": "LAD"},
    ]
    # Promoting an existing extra favorite doesn't duplicate it
    set_primary_team(config, find_team("mlb", "LAD"))
    assert [f["team"] for f in config["favorites"]] == ["HOU", "LAD"]
    assert primary_team(config).abbr == "LAD"


def test_set_primary_team_on_empty_config():
    config = {}
    set_primary_team(config, find_team("mlb", "NYY"))
    assert config["favorites"] == [{"league": "mlb", "team": "NYY"}]
