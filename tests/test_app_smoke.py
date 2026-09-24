"""End-to-end smoke tests for the menu bar app, runnable on any OS.

rumps, AppKit, and PyObjCTools are replaced with small stand-ins so the
real MenuBarApp can be driven headlessly: timers are ticked by hand,
and "main thread" callbacks queued with AppHelper.callAfter run only when
the test pumps them — exactly like the AppKit run loop would.
"""

from __future__ import annotations

import copy
import datetime as dt
import queue
import sys
import threading
import time
import types

import pytest
import yaml

from tests.conftest import FROZEN_NOW, load_fixture


# --- stand-ins for rumps / AppKit / PyObjCTools ------------------------------

class FakeNSMenuItem:
    def __init__(self) -> None:
        self.hidden = False
        self.attributed = None

    def setHidden_(self, hidden) -> None:
        self.hidden = bool(hidden)

    def setAttributedTitle_(self, astr) -> None:
        self.attributed = astr


class MenuItem:
    def __init__(self, title, callback=None, **_kw) -> None:
        self.title = title
        self.callback = callback
        self.state = 0
        self.children: list = []
        self._menuitem = FakeNSMenuItem()

    def update(self, items) -> None:
        self.children.extend(items)

    def clear(self) -> None:
        self.children = []

    def titles(self) -> list:
        return [c.title for c in self.children if c is not None]

    @property
    def hidden(self) -> bool:
        return self._menuitem.hidden


class Timer:
    def __init__(self, callback, interval) -> None:
        self.callback = callback
        self.interval = interval
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False


class StatusButton:
    def __init__(self) -> None:
        self.attributed = None

    def setAttributedTitle_(self, astr) -> None:
        self.attributed = astr


class App:
    def __init__(self, name, title=None, **_kw) -> None:
        self.name = name
        self.title = title
        self.menu = None
        button = StatusButton()
        self._nsapp = types.SimpleNamespace(
            nsstatusitem=types.SimpleNamespace(button=lambda: button)
        )
        self.status_button = button


class AttributedString:
    @classmethod
    def alloc(cls):
        return cls()

    def initWithString_attributes_(self, text, attrs):
        self.text, self.attrs = text, attrs
        return self


class MainLoop:
    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue()
        self.thread_names: list = []

    def call_after(self, fn, *args) -> None:
        self.q.put((fn, args))

    def pump(self, app, limit: float = 10.0) -> None:
        """Run main-thread callbacks until the worker is idle."""
        deadline = time.time() + limit
        while time.time() < deadline:
            try:
                fn, args = self.q.get(timeout=0.05)
            except queue.Empty:
                if app.worker.idle() and self.q.empty():
                    return
                continue
            fn(*args)
        raise AssertionError("app never went idle")


@pytest.fixture
def harness(monkeypatch, config_dir, fake_api, central_time):
    loop = MainLoop()
    notifications: list = []

    rumps = types.ModuleType("rumps")
    rumps.App = App
    rumps.MenuItem = MenuItem
    rumps.Timer = Timer
    rumps.timer = lambda _interval: (lambda fn: fn)
    rumps.notification = lambda title, subtitle, message: notifications.append((subtitle, message))
    rumps.quit_application = lambda: None

    appkit = types.ModuleType("AppKit")
    appkit.NSAttributedString = AttributedString
    appkit.NSColor = types.SimpleNamespace(
        systemGreenColor=lambda: "green",
        systemRedColor=lambda: "red",
        systemYellowColor=lambda: "yellow",
    )
    appkit.NSFont = types.SimpleNamespace(
        menuBarFontOfSize_=lambda size: "menubar-font",
        monospacedSystemFontOfSize_weight_=lambda size, weight: "mono-font",
    )
    appkit.NSFontAttributeName = "font"
    appkit.NSForegroundColorAttributeName = "color"

    pyobjctools = types.ModuleType("PyObjCTools")
    pyobjctools.AppHelper = types.SimpleNamespace(callAfter=loop.call_after)

    monkeypatch.setitem(sys.modules, "rumps", rumps)
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    monkeypatch.setitem(sys.modules, "PyObjCTools", pyobjctools)
    monkeypatch.delitem(sys.modules, "sportsbar.app", raising=False)

    import sportsbar.app as app_module
    import sportsbar.config
    import sportsbar.mlb
    import sportsbar.weather

    import sportsbar.espn_follow

    for mod in (sportsbar.config, sportsbar.mlb, sportsbar.weather, app_module):
        monkeypatch.setattr(mod, "now_local", lambda: FROZEN_NOW)
    monkeypatch.setattr(app_module, "CONFIG_PATH", config_dir / "config.yaml")
    # ESPN follower clock: the same moment, as an aware UTC time
    frozen_utc = FROZEN_NOW.astimezone(dt.timezone.utc)
    monkeypatch.setattr(sportsbar.espn_follow, "_now", lambda: frozen_utc)

    apps = []

    def make_app(**config_overrides):
        if config_overrides:
            (config_dir / "config.yaml").write_text(yaml.safe_dump(config_overrides))
        app = app_module.MenuBarApp()
        apps.append(app)
        return app

    def tick(app, timer: str = "primary"):
        """Fire a timer on the 'main thread', then let the work finish."""
        if timer == "primary":
            app.primary_timer.callback(app.primary_timer)
        else:
            app.refresh_slow(None)
        loop.pump(app)

    h = types.SimpleNamespace(
        make_app=make_app, tick=tick, loop=loop, api=fake_api,
        notifications=notifications, config_dir=config_dir,
    )
    yield h
    for app in apps:
        app.worker.stop(timeout=5)
    sys.modules.pop("sportsbar.app", None)


def final_schedule(astros_runs: int, opp_runs: int) -> dict:
    sched = copy.deepcopy(load_fixture("schedule_team.json"))
    game = sched["dates"][0]["games"][0]
    game["status"] = {"abstractGameState": "Final", "detailedState": "Final"}
    game["teams"]["away"]["score"] = astros_runs
    game["teams"]["home"]["score"] = opp_runs
    return sched


# --- tests ----------------------------------------------------------------------

def test_first_tick_does_full_refresh_off_main_thread(harness):
    app = harness.make_app()
    harness.tick(app)

    assert harness.api.calls, "expected network requests"
    assert {thread for _, thread in harness.api.calls} == {"sportsbar-worker"}

    # Menu bar title: live score, Astros (away) up 3-2 → green
    assert app.title == "3-2 ▼7"
    assert app.status_button.attributed.attrs["color"] == "green"

    assert app.top_line_1.title == "HOU 3 — SEA 2  |  Bot 7th"
    assert app.top_line_2.title == "Runners: 1st, 3rd  |  2-1, 1 out"
    assert app.top_line_4.title == "TV: Space City Home Network"
    assert app.top_line_5._menuitem.hidden  # unused placeholder row

    assert app.todays_game_menu.title == "⚾ Live Game"
    assert app.tg_box_2._menuitem.attributed.text.startswith("HOU   0  1")

    plays = app.plays_menu.titles()
    assert len(plays) == 4
    assert plays[0].startswith("⭐ ▲2  1-0  Yainer Diaz homers")

    assert app.lineup_menu.titles()[0] == "1. Jose Altuve (2B)"
    assert len(app.lineup_menu.titles()) == 9

    scores = app.scores_menu.titles()
    assert scores[0] == "🔴 Live"
    assert "   ⭐ HOU 3 — SEA 2   ▼7" in scores

    magic = app.magic_menu.titles()
    assert "🏆 Win AL West: 5" in magic

    assert app.weather_menu.titles()[0] == "📍 T-Mobile Park"
    assert app.stats_menu.titles()[0] == "Record: 88-67"
    assert app.rotation_menu.titles()[0] == "Framber Valdez — Next: 2026-09-24 (14-7, 3.12 ERA)"

    # Data was cached for an instant next launch
    for name in ("schedule", "league_scores", "standings", "lineup", "weather", "team_stats"):
        assert (harness.config_dir / "cache" / f"{name}.json").exists()


def test_live_tick_sets_fast_interval_and_notifies_astros_runs(harness):
    app = harness.make_app(notifications={"scoring_plays": True, "final_score": True})
    harness.tick(app)  # full refresh
    harness.tick(app)  # primary: baseline score
    assert app.primary_timer.interval == 60
    assert not any(t == "Astros Score!" for t, _ in harness.notifications)

    feed = load_fixture("feed_live.json")
    feed["liveData"]["linescore"]["teams"]["away"]["runs"] = 4
    harness.api.overrides["/feed/live"] = feed
    harness.tick(app)
    assert ("Astros Score!", "HOU 4 — SEA 2") in harness.notifications
    assert app.title == "4-2 ▼7"


def test_game_ending_sends_final_and_colors_title(harness):
    app = harness.make_app()
    harness.tick(app)  # full refresh → live
    harness.api.overrides["teamId="] = final_schedule(2, 5)
    harness.tick(app)
    assert ("Final Score", "Astros 2, Mariners 5 — L") in harness.notifications
    assert app.title == "2-5 F"
    assert app.status_button.attributed.attrs["color"] == "red"
    assert app.primary_timer.interval == 900


def test_network_down_leaves_app_usable(harness):
    harness.api.fail = True
    app = harness.make_app()
    harness.tick(app)
    assert app.title == "⚾"
    assert app.top_line_1.title == "No game today"
    assert app.standings_menu.titles() == ["Standings unavailable"]
    # Recovers on the next tick once the network is back
    harness.api.fail = False
    harness.tick(app)
    assert app.title == "3-2 ▼7"


def test_slow_refresh_runs_in_background(harness):
    app = harness.make_app()
    harness.tick(app)
    harness.api.calls.clear()
    harness.tick(app, timer="slow")
    urls = [u for u, _ in harness.api.calls]
    assert any("/standings" in u for u in urls)
    assert {thread for _, thread in harness.api.calls} == {"sportsbar-worker"}


def test_check_updates_runs_in_background(harness, monkeypatch):
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    harness.api.overrides["api.github.com"] = {
        "tag_name": "v99.0.0", "html_url": "https://example.com/release",
    }
    app = harness.make_app()
    app.check_updates(None)
    harness.loop.pump(app)
    assert harness.api.calls[-1][1] == "sportsbar-worker"
    assert harness.notifications[-1][0] == "Update Available"
    assert opened == ["https://example.com/release"]


def test_menus_are_labelled_for_the_favorite_team(harness):
    app = harness.make_app()
    harness.tick(app)
    assert app.team_menu.title == "⭐ Favorite MLB Team: Astros"
    assert app.notif_scoring_plays.title == "Astros Scoring Plays"
    assert app.team_items[117].state == 1
    assert sum(item.state for item in app.team_items.values()) == 1
    assert "Astros on MLB.com" in app.links_menu.titles()
    assert app.magic_menu.titles()[0].startswith("HOU 88-67")


def test_picking_a_team_switches_everything(harness):
    app = harness.make_app()
    harness.tick(app)
    harness.api.calls.clear()

    app.select_team(app.team_items[136])  # Seattle Mariners
    harness.loop.pump(app)

    # Saved to config
    saved = yaml.safe_load((harness.config_dir / "config.yaml").read_text())
    assert saved["favorites"] == [{"league": "mlb", "team": "SEA"}]
    # Refetched for the new team, off the main thread
    urls = [u for u, _ in harness.api.calls]
    assert any("teamId=136" in u for u in urls)
    assert any("/teams/136/stats" in u for u in urls)
    assert {thread for _, thread in harness.api.calls} == {"sportsbar-worker"}

    # Same HOU 3 @ SEA 2 game, now from Seattle's side: losing → red
    assert app.title == "3-2 ▼7"
    assert app.status_button.attributed.attrs["color"] == "red"
    assert app.top_line_4.title == "TV: ROOT Sports NW"
    assert app.plays_menu.titles()[1].startswith("⭐ ▼4")  # SEA's runs starred
    assert not app.plays_menu.titles()[0].startswith("⭐")
    assert app.team_menu.title == "⭐ Favorite MLB Team: Mariners"
    assert app.notif_scoring_plays.title == "Mariners Scoring Plays"
    assert app.team_items[136].state == 1 and app.team_items[117].state == 0
    assert "Mariners on MLB.com" in app.links_menu.titles()
    magic = app.magic_menu.titles()
    assert magic[0].startswith("SEA 86-69")
    assert "🏆 Win AL West: 10  (2.0 GB)" in magic
    # Game is at Seattle → home ballpark weather
    assert "latitude=47.5914" in next(u for u in urls if "open-meteo" in u)
    # Lineup is Seattle's (empty in the fixture), not Houston's
    assert app.lineup_menu.titles() == ["Lineup not yet announced"]


def test_picking_the_current_team_does_nothing(harness):
    app = harness.make_app()
    harness.tick(app)
    harness.api.calls.clear()
    app.select_team(app.team_items[117])
    harness.loop.pump(app)
    assert harness.api.calls == []


def test_refresh_now_picks_up_edited_favorites(harness):
    app = harness.make_app()
    harness.tick(app)
    (harness.config_dir / "config.yaml").write_text(
        yaml.safe_dump({"favorites": [{"league": "mlb", "team": "Mariners"}]})
    )
    app.manual_refresh(None)
    harness.loop.pump(app)
    assert app.team.abbr == "SEA"
    assert app.team_menu.title == "⭐ Favorite MLB Team: Mariners"


def test_extra_favorites_are_starred_on_scoreboard(harness):
    app = harness.make_app(favorites=[
        {"league": "mlb", "team": "HOU"}, {"league": "mlb", "team": "BOS"},
    ])
    harness.tick(app)
    scores = app.scores_menu.titles()
    assert "   ⭐ HOU 3 — SEA 2   ▼7" in scores
    assert "   ⭐ NYY 5 — BOS 4   F/10" in scores
    assert "   CHC 2 — STL 7   F" in scores


def test_cached_data_from_another_team_is_ignored(harness):
    from sportsbar import config
    config.write_cache("schedule", {"games": [{"gamePk": 1}], "team": "mlb/SEA"})
    config.write_cache("team_stats", {"hitting": {"wins": 1}, "team": "mlb/SEA"})
    app = harness.make_app()  # follows HOU
    assert app.schedule_data == [] and app.team_stats == {}


def test_legacy_cache_without_team_belongs_to_astros(harness):
    from sportsbar import config
    config.write_cache("schedule", {"games": [{"gamePk": 1}]})
    assert harness.make_app().schedule_data == [{"gamePk": 1}]
    config.write_cache("schedule", {"games": [{"gamePk": 1}]})
    assert harness.make_app(favorites=[{"league": "mlb", "team": "SEA"}]).schedule_data == []


def test_toggle_notification_persists(harness):
    app = harness.make_app()
    assert app.notif_scoring_plays.state == 0
    app.toggle_notification(app.notif_scoring_plays)
    saved = yaml.safe_load((harness.config_dir / "config.yaml").read_text())
    assert saved["notifications"]["scoring_plays"] is True


def test_duplicate_ticks_while_busy_are_dropped(harness):
    app = harness.make_app()
    harness.tick(app)
    gate = threading.Event()
    real_get = harness.api.get

    def slow_get(url, **kw):
        gate.wait(5)
        return real_get(url, **kw)

    import requests
    requests.get = slow_get  # restored by the fake_api fixture
    app.primary_timer.callback(app.primary_timer)
    app.primary_timer.callback(app.primary_timer)  # still busy → dropped
    gate.set()
    harness.loop.pump(app)
    schedule_calls = [u for u, _ in harness.api.calls if "teamId=" in u]
    assert len(schedule_calls) == 2  # full refresh + one primary tick


# --- other leagues (ESPN) ----------------------------------------------------------

NFL_ONLY = [{"league": "nfl", "team": "HOU"}]


def mlb_calls(harness):
    return [u for u, _ in harness.api.calls if "statsapi.mlb.com" in u]


def test_football_only_hides_baseball(harness):
    app = harness.make_app(favorites=NFL_ONLY)
    harness.tick(app)

    assert mlb_calls(harness) == []  # nothing fetched for baseball
    assert {t for _, t in harness.api.calls} == {"sportsbar-worker"}
    for item in (app.top_line_1, app.todays_game_menu, app.lineup_menu, app.scores_menu,
                 app.magic_menu, app.game_text_item):
        assert item.hidden
    assert app.team_menu.title == "⭐ Favorite MLB Team: None"
    assert app.no_mlb_item.state == 1

    # Texans live at Jacksonville: title, headline row, team menu
    assert app.title == "🏈 21-17 Q3"
    assert app.status_button.attributed.attrs["color"] == "green"
    assert app.espn_rows[0].title == "🏈 HOU 21 — JAX 17   Q3 4:12"
    assert not app.espn_rows[0].hidden and app.espn_rows[1].hidden
    menu = app.espn_menus[0]
    assert menu.title == "🏈 Texans  — Live" and not menu.hidden
    assert all(m.hidden for m in app.espn_menus[1:])
    titles = menu.titles()
    assert titles[:3] == ["HOU 21 — JAX 17   Q3 4:12", "JAX ball · 2nd & 7 at HOU 35", "TV: Prime Video"]
    assert "Last play: T.Etienne run for 4 yards" in titles
    assert "🔗 Texans on ESPN" in titles
    schedule = next(c for c in menu.children if c is not None and c.title == "📅 Schedule")
    assert schedule.titles()[:2] == ["L 9-14  @ LAR", "W 20-19  vs TB"]
    box = [c for c in menu.children if c is not None and c._menuitem.attributed]
    assert box[1]._menuitem.attributed.text == "HOU   7   7   7        21"

    # League scoreboards: NFL shown, college and MLB hidden
    nfl_scores = app.espn_score_menus["nfl"]
    assert not nfl_scores.hidden and app.espn_score_menus["ncaaf"].hidden
    assert "   ⭐ HOU 21 — JAX 17   Q3 4:12" in nfl_scores.titles()
    assert app.primary_timer.interval == 60  # a favorite is live
    assert "Texans on ESPN" in app.links_menu.titles()
    assert "Astros on MLB.com" not in app.links_menu.titles()


def test_first_favorite_wins_the_title(harness):
    both = [{"league": "mlb", "team": "HOU"}, {"league": "nfl", "team": "HOU"}]
    app = harness.make_app(favorites=both)
    harness.tick(app)
    assert app.title == "3-2 ▼7"  # Astros listed first (both live)
    assert app.espn_rows[0].title == "🏈 HOU 21 — JAX 17   Q3 4:12"
    assert not app.todays_game_menu.hidden

    app = harness.make_app(favorites=list(reversed(both)))
    harness.tick(app)
    assert app.title == "🏈 21-17 Q3"


def test_live_favorite_beats_an_idle_one(harness):
    app = harness.make_app(favorites=[{"league": "nfl", "team": "DAL"}, {"league": "mlb", "team": "HOU"}])
    harness.tick(app)
    assert app.title == "3-2 ▼7"  # Cowboys don't play until Sunday


def test_idle_icon_follows_first_favorite(harness):
    harness.api.overrides["/football/nfl/scoreboard"] = {"events": []}
    app = harness.make_app(favorites=[{"league": "nfl", "team": "DAL"}])
    harness.tick(app)
    assert app.title == "🏈"


def test_football_scoring_notification(harness):
    app = harness.make_app(favorites=NFL_ONLY, notifications={"scoring_plays": True})
    harness.tick(app)
    board = load_fixture("espn_nfl_scoreboard.json")
    comp = board["events"][0]["competitions"][0]
    next(c for c in comp["competitors"] if c["homeAway"] == "away")["score"] = "28"
    harness.api.overrides["/football/nfl/scoreboard"] = board
    harness.tick(app)
    assert ("Texans Score!", "HOU 28 — JAX 17   Q3 4:12") in harness.notifications
    assert app.title == "🏈 28-17 Q3"


def test_college_scoreboard_shows_ranked_games_by_default(harness):
    app = harness.make_app(favorites=[{"league": "ncaaf", "team": "Texas"}])
    harness.tick(app)
    scores = app.espn_score_menus["ncaaf"].titles()
    assert "   #12 UGA @ #7 TEX   Sat 7:30 PM" in [s.replace("⭐ ", "") for s in scores]
    assert "   ⭐ #12 UGA @ #7 TEX   Sat 7:30 PM" in scores
    assert "   RUTG 10 — #1 OSU 38   F" in scores
    assert not any("ARMY" in s or "TTU" in s for s in scores)  # unranked
    assert scores[-1] == "Showing ranked teams and your favorites"
    # Texas plays Saturday: not a "today" headline, but its menu is ready
    assert all(r.hidden for r in app.espn_rows)
    assert app.espn_menus[0].titles()[0] == "Texas vs #12 UGA  |  Sat 7:30 PM"


def test_college_scoreboard_all_games_option(harness):
    app = harness.make_app(
        favorites=[{"league": "ncaaf", "team": "TEX"}],
        leagues={"ncaaf": {"scoreboard": "all"}},
    )
    harness.tick(app)
    scores = app.espn_score_menus["ncaaf"].titles()
    assert any("ARMY @ NAVY" in s for s in scores)
    assert any("HOU 10 — TTU 14   Half" in s for s in scores)


def test_unknown_football_team_is_flagged(harness):
    app = harness.make_app(favorites=[{"league": "ncaaf", "team": "Tigers"}])
    harness.tick(app)
    assert app.espn_menus[0].titles() == [
        "⚠️ No College Football team matches “Tigers” — check favorites in the config"
    ]


def test_unfollow_mlb_from_the_picker(harness):
    app = harness.make_app(favorites=[{"league": "mlb", "team": "HOU"}, *NFL_ONLY])
    harness.tick(app)
    assert not app.todays_game_menu.hidden
    app.unfollow_mlb(None)
    harness.loop.pump(app)
    saved = yaml.safe_load((harness.config_dir / "config.yaml").read_text())
    assert saved["favorites"] == NFL_ONLY
    assert app.todays_game_menu.hidden and app.title == "🏈 21-17 Q3"
    # Picking a team turns baseball back on
    app.select_team(app.team_items[117])
    harness.loop.pump(app)
    assert not app.todays_game_menu.hidden
    assert app.title == "🏈 21-17 Q3"  # NFL is still listed first


def test_espn_cache_fills_menus_before_first_refresh(harness):
    app = harness.make_app(favorites=NFL_ONLY)
    harness.tick(app)
    harness.api.fail = True
    relaunched = harness.make_app(favorites=NFL_ONLY)
    relaunched.update_espn_menus()
    assert relaunched.espn_menus[0].titles()[0] == "HOU 21 — JAX 17   Q3 4:12"
