import logging

from sportsbar import odds, weather
from tests.conftest import load_fixture


def astros_event():
    return next(e for e in load_fixture("odds.json") if "Houston Astros" in e["away_team"])


def test_fetch_odds_finds_astros_game(fake_api):
    event = odds.fetch_odds("secret-key")
    assert event["id"] == "def"
    assert "apiKey=secret-key" in fake_api.calls[0][0]


def test_fetch_odds_without_key_makes_no_request(fake_api):
    assert odds.fetch_odds("") == {}
    assert fake_api.calls == []


def test_fetch_odds_never_logs_api_key(fake_api, caplog):
    def boom(url, **_kw):
        raise ConnectionError(f"failed: {url}")
    fake_api.get = boom
    import requests
    requests.get = boom  # fake_api fixture's monkeypatch restores it
    with caplog.at_level(logging.ERROR):
        assert odds.fetch_odds("secret-key") == {}
    assert "secret-key" not in caplog.text
    assert "***" in caplog.text


def test_parse_odds():
    parsed = odds.parse_odds(astros_event())
    assert parsed["matchup"] == "Houston Astros @ Seattle Mariners"
    assert parsed["moneyline"]["away"] == {"name": "Houston Astros", "price": 120}
    assert parsed["moneyline"]["home"]["price"] == -142
    assert parsed["spread"]["away"]["point"] == 1.5
    assert parsed["total"]["over"] == {"price": -110, "point": 7.5}


def test_parse_odds_empty():
    assert odds.parse_odds({})["moneyline"] == {}


def test_format_odds_price():
    assert odds.format_odds_price(120) == "+120"
    assert odds.format_odds_price(0) == "+0"
    assert odds.format_odds_price(-142) == "-142"


def test_fetch_weather(fake_api, frozen_now):
    w = weather.fetch_weather(136)
    assert "latitude=47.5914" in fake_api.calls[0][0]
    assert w["temp_f"] == 68.0
    assert w["max_f"] == 77.0 and w["min_f"] == 59.0
    assert round(w["wind_mph"]) == 10
    assert w["condition"] == "Partly cloudy"
    assert w["updated"] == "2026-09-24T19:30"


def test_fetch_weather_unknown_team_or_error(fake_api):
    assert weather.fetch_weather(999) == {}
    assert fake_api.calls == []
    fake_api.fail = True
    assert weather.fetch_weather(117) == {}
