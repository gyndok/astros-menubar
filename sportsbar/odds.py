"""Betting lines from The Odds API (optional, needs a free API key)."""

from __future__ import annotations

import logging

import requests


ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports/baseball_mlb"


def fetch_odds(api_key: str) -> dict:
    """Fetch Astros game odds from The Odds API."""
    if not api_key:
        return {}
    try:
        url = (
            f"{ODDS_API_BASE}/odds/"
            f"?apiKey={api_key}&regions=us&markets=h2h,spreads,totals"
            f"&oddsFormat=american&bookmakers=draftkings"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        events = resp.json()
        for event in events:
            if "Houston Astros" in (event.get("home_team", ""), event.get("away_team", "")):
                return event
        return {}
    except Exception as exc:
        # Don't log the raw exception — request URLs embed the API key.
        logging.error("fetch_odds failed: %s", str(exc).replace(api_key, "***"))
        return {}


def parse_odds(event: dict) -> dict:
    """Parse odds event into a clean dict with moneyline, spread, total."""
    result = {"matchup": "", "moneyline": {}, "spread": {}, "total": {}, "updated": ""}
    if not event:
        return result

    home = event.get("home_team", "")
    away = event.get("away_team", "")
    result["matchup"] = f"{away} @ {home}"
    result["updated"] = event.get("commence_time", "")

    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            key = market.get("key")
            outcomes = market.get("outcomes", [])
            if key == "h2h":
                for o in outcomes:
                    side = "home" if o["name"] == home else "away"
                    result["moneyline"][side] = {"name": o["name"], "price": o["price"]}
            elif key == "spreads":
                for o in outcomes:
                    side = "home" if o["name"] == home else "away"
                    result["spread"][side] = {"name": o["name"], "price": o["price"], "point": o.get("point", 0)}
            elif key == "totals":
                for o in outcomes:
                    direction = o["name"].lower()
                    result["total"][direction] = {"price": o["price"], "point": o.get("point", 0)}
        break
    return result


def format_odds_price(price: int) -> str:
    """Format American odds with +/- prefix."""
    if price >= 0:
        return f"+{price}"
    return str(price)
