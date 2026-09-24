"""End-to-end smoke tests for the menu bar app, runnable on any OS.

rumps, AppKit, and PyObjCTools are replaced with small stand-ins so the
real AstrosMenuBarApp can be driven headlessly: timers are ticked by hand,
and "main thread" callbacks queued with AppHelper.callAfter run only when
the test pumps them — exactly like the AppKit run loop would.
"""

from __future__ import annotations

import copy
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

    for mod in (sportsbar.config, sportsbar.mlb, sportsbar.weather, app_module):
        monkeypatch.setattr(mod, "now_local", lambda: FROZEN_NOW)
    monkeypatch.setattr(app_module, "CONFIG_PATH", config_dir / "config.yaml")

    apps = []

    def make_app(**config_overrides):
        if config_overrides:
            (config_dir / "config.yaml").write_text(yaml.safe_dump(config_overrides))
        app = app_module.AstrosMenuBarApp()
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
