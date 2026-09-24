"""App identity, config file, logging, and the on-disk JSON cache."""

from __future__ import annotations

import copy
import datetime as dt
import json
import logging
from pathlib import Path

import yaml


APP_NAME = "Astros Menu Bar"
APP_VERSION = "1.4.0"
GITHUB_REPO = "gyndok/astros-menubar"
CONFIG_DIR = Path.home() / ".config" / "astros-menubar"
CONFIG_PATH = CONFIG_DIR / "config.yaml"
CACHE_DIR = CONFIG_DIR / "cache"
LOG_PATH = CONFIG_DIR / "app.log"

DEFAULT_CONFIG = {
    "odds_api_key": "",
    "notifications": {
        "game_starting": True,
        "final_score": True,
        "scoring_plays": False,
        "lineup_posted": False,
    },
    "show_odds": True,
    "show_weather": True,
    "quick_links": [
        {"name": "User's Guide", "url": f"https://github.com/{GITHUB_REPO}/blob/main/docs/USER_GUIDE.md"},
        {"name": "Astros.com", "url": "https://www.mlb.com/astros"},
        {"name": "MLB.tv", "url": "https://www.mlb.com/tv"},
        {"name": "Space City Home Network", "url": "https://www.spacecityhomenetwork.com"},
        {"name": "r/Astros", "url": "https://www.reddit.com/r/Astros/"},
        {"name": "Astros on X", "url": "https://x.com/astros"},
    ],
}


def ensure_paths() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_paths()
    if not CONFIG_PATH.exists():
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            yaml.safe_dump(DEFAULT_CONFIG, f, sort_keys=False)
        return copy.deepcopy(DEFAULT_CONFIG)
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    # Deep copy so callers mutating the config (e.g. toggling a
    # notification) never write through to DEFAULT_CONFIG.
    merged = copy.deepcopy(DEFAULT_CONFIG)
    merged.update(loaded)
    if not isinstance(merged.get("notifications"), dict):
        merged["notifications"] = copy.deepcopy(DEFAULT_CONFIG["notifications"])
    if not isinstance(merged.get("quick_links"), list):
        merged["quick_links"] = copy.deepcopy(DEFAULT_CONFIG["quick_links"])
    # Configs saved before the User's Guide existed won't have its link —
    # make sure it's always present at the top.
    guide = dict(DEFAULT_CONFIG["quick_links"][0])
    if not any(
        isinstance(link, dict) and link.get("url") == guide["url"]
        for link in merged["quick_links"]
    ):
        merged["quick_links"].insert(0, guide)
    return merged


def setup_logging() -> None:
    ensure_paths()
    logging.basicConfig(
        filename=str(LOG_PATH),
        filemode="a",
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def now_local() -> dt.datetime:
    return dt.datetime.now()


def read_cache(name: str) -> dict:
    path = CACHE_DIR / f"{name}.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logging.exception("Failed reading cache %s: %s", name, exc)
        return {}


def write_cache(name: str, payload: dict) -> None:
    ensure_paths()
    path = CACHE_DIR / f"{name}.json"
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception as exc:
        logging.exception("Failed writing cache %s: %s", name, exc)
