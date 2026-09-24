"""The rumps menu bar app: menus, timers, and notifications.

Network I/O never runs on the main thread — timer and menu callbacks
submit jobs to a BackgroundWorker, and menus are rebuilt on the main
thread once a job finishes.
"""

from __future__ import annotations

import datetime as dt
import logging
import subprocess
import webbrowser
from typing import Any, Dict, List, Optional

import requests
import rumps
from AppKit import (
    NSAttributedString,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
)
from PyObjCTools import AppHelper

from .config import (
    APP_NAME,
    APP_VERSION,
    CONFIG_PATH,
    GITHUB_REPO,
    load_config,
    now_local,
    quick_links,
    read_cache,
    save_config,
    write_cache,
)
from .gametext import generate_game_text
from .mlb import (
    DIVISIONS,
    LEAGUES,
    NON_GAME_STATES,
    _game_status,
    compute_magic_numbers,
    detect_game_state,
    fetch_boxscore,
    fetch_league_scores,
    fetch_live_game,
    fetch_pitcher_stats,
    fetch_schedule,
    fetch_standings,
    fetch_team_stats,
    format_game_time,
    format_league_game,
    format_line_score,
    format_record,
    nickname,
    get_probable_pitcher,
    get_tv_broadcast,
    opponent_team_id,
    parse_line_score,
    parse_lineup,
    parse_live_data,
    parse_scoring_plays,
    team_side,
)
from . import espn
from .espn_follow import ESPNFollower, Followed, TitleCandidate
from .models import FINAL, LIVE, POSTPONED, PRE
from .odds import fetch_odds, format_odds_price, parse_odds
from .teams import (
    DIVISION_NAMES,
    LEAGUE_DIVISIONS,
    MLB_TEAMS,
    ESPN_LEAGUES,
    Team,
    favorite_refs,
    favorite_teams,
    follows_league,
    primary_team,
    remove_league_favorites,
    set_primary_team,
)
from .weather import fetch_weather
from .worker import BackgroundWorker


# Caches written before favorites existed belong to the Astros.
LEGACY_CACHE_TEAM = "mlb/HOU"

# Fixed menu slots for teams in ESPN leagues (NFL, college football):
# a headline row at the top and a submenu each. Unused slots are hidden.
ESPN_SLOTS = 6


class MenuBarApp(rumps.App):
    """macOS menu bar app that follows your favorite team."""

    def __init__(self) -> None:
        super().__init__(APP_NAME, title="⚾")
        self.config = load_config()
        self.team: Team = primary_team(self.config)
        self.follow_mlb: bool = follows_league(self.config, "mlb")
        self.espn = ESPNFollower()
        self.espn.configure(favorite_refs(self.config))
        self.espn.load_cache()

        # Data caches
        self.schedule_data: list = []
        self.game_state: dict = {"state": "off", "game": None, "game_pk": None}
        self.live_data: dict = {}
        self.lineup_data: list = []
        self.scoring_plays: list = []
        self._plays_game_pk: Optional[int] = None
        self.line_score: dict = {}
        self.standings_data: list = []
        self.odds_data: dict = {}
        self.weather_data: dict = {}
        self.team_stats: dict = {}
        self.previous_my_score: Optional[int] = None
        self.final_revert_time: Optional[dt.datetime] = None
        self._did_initial_refresh: bool = False
        self._starting_soon_pk: Optional[int] = None  # dedup "starting soon" notification
        self._score_watch_pk: Optional[int] = None    # reset score tracking per game
        self._lineup_seen_pk: Optional[int] = None    # dedup "lineup posted" notification
        self.pitcher_stats_cache: Dict[int, dict] = {}

        # Load cached data from disk (team-specific caches only if they
        # belong to the current team)
        self.schedule_data = self._read_team_cache("schedule").get("games", [])
        self.league_scores: list = read_cache("league_scores").get("games", [])
        self.standings_data = read_cache("standings").get("records", [])
        odds_cache = self._read_team_cache("odds")
        if "event" in odds_cache:
            self.odds_data = odds_cache.get("event") or {}
            self._odds_fetched: str = odds_cache.get("fetched", "")
        else:  # legacy cache format: the raw event dict
            self.odds_data = odds_cache
            self._odds_fetched = ""
        self.weather_data = self._read_team_cache("weather")
        self.team_stats = self._read_team_cache("team_stats")

        self._build_menu()

        # All network I/O runs on this worker; results come back to the
        # main thread to update menus (see sportsbar/worker.py).
        self.worker = BackgroundWorker(AppHelper.callAfter)

        # Primary polling timer. Owned explicitly (rather than via the
        # @rumps.timer decorator) so refresh_primary can adapt its interval
        # to the game state.
        self.primary_timer = rumps.Timer(self.refresh_primary, 60)
        self.primary_timer.start()

    # ------------------------------------------------------------------
    # Menu construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        """Create all menu items."""
        # Headline rows for favorites in ESPN leagues (NFL, college...)
        self.espn_rows = [rumps.MenuItem("—", callback=self._noop) for _ in range(ESPN_SLOTS)]
        # Submenu per ESPN-league favorite
        self.espn_menus = [rumps.MenuItem(f"🏈 Team {n + 1}") for n in range(ESPN_SLOTS)]
        for menu in self.espn_menus:
            menu.update([rumps.MenuItem("Loading...")])
        # League-wide scoreboards for ESPN leagues
        self.espn_score_menus: Dict[str, rumps.MenuItem] = {}
        for key in ESPN_LEAGUES:
            league = espn.LEAGUES[key]
            menu = rumps.MenuItem(f"{league.emoji} {league.name} Scores")
            menu.update([rumps.MenuItem("Loading...")])
            self.espn_score_menus[key] = menu

        # Top context-aware lines
        self.top_line_1 = rumps.MenuItem("—", callback=self._noop)
        self.top_line_2 = rumps.MenuItem("—", callback=self._noop)
        self.top_line_3 = rumps.MenuItem("—", callback=self._noop)
        self.top_line_4 = rumps.MenuItem("—", callback=self._noop)
        self.top_line_5 = rumps.MenuItem("—", callback=self._noop)

        # Today's Game submenu
        self.todays_game_menu = rumps.MenuItem("⚾ Today's Game")
        self.tg_line_1 = rumps.MenuItem("—", callback=self._noop)
        self.tg_line_2 = rumps.MenuItem("—", callback=self._noop)
        self.tg_line_3 = rumps.MenuItem("—", callback=self._noop)
        self.tg_line_4 = rumps.MenuItem("—", callback=self._noop)
        self.tg_line_5 = rumps.MenuItem("—", callback=self._noop)
        self.tg_line_6 = rumps.MenuItem("—", callback=self._noop)
        # Line score rows (rendered in a monospaced font)
        self.tg_box_1 = rumps.MenuItem("—", callback=self._noop)
        self.tg_box_2 = rumps.MenuItem("—", callback=self._noop)
        self.tg_box_3 = rumps.MenuItem("—", callback=self._noop)
        self.todays_game_menu.update([
            self.tg_line_1, self.tg_line_2, self.tg_line_3,
            self.tg_line_4, self.tg_line_5, self.tg_line_6,
            self.tg_box_1, self.tg_box_2, self.tg_box_3,
        ])

        # Scoring Plays submenu
        self.plays_menu = rumps.MenuItem("📝 Scoring Plays")
        self.plays_menu.update([rumps.MenuItem("Loading...")])

        # Schedule submenu (placeholder seeds _menu so .clear() works later)
        self.schedule_menu = rumps.MenuItem("📅 Schedule")
        self.schedule_menu.update([rumps.MenuItem("Loading...")])

        # Lineup submenu
        self.lineup_menu = rumps.MenuItem("👥 Lineup")
        self.lineup_menu.update([rumps.MenuItem("Loading...")])

        # Rotation submenu
        self.rotation_menu = rumps.MenuItem("⚾ Starting Rotation")
        self.rotation_menu.update([rumps.MenuItem("Loading...")])

        # League-wide scores submenu
        self.scores_menu = rumps.MenuItem("🌎 MLB Scores")
        self.scores_menu.update([rumps.MenuItem("Loading...")])

        # Standings submenu
        self.standings_menu = rumps.MenuItem("📊 Standings")
        self.standings_menu.update([rumps.MenuItem("Loading...")])

        # Magic Numbers submenu
        self.magic_menu = rumps.MenuItem("🔮 Magic Numbers")
        self.magic_menu.update([rumps.MenuItem("Loading...")])

        # Odds submenu
        self.odds_menu = rumps.MenuItem("💰 Vegas Odds")
        self.odds_menu.update([rumps.MenuItem("Loading...")])

        # Weather submenu
        self.weather_menu = rumps.MenuItem("🌤 Ballpark Weather")
        self.weather_menu.update([rumps.MenuItem("Loading...")])

        # Quick Links submenu (filled by _update_team_items)
        self.links_menu = rumps.MenuItem("🔗 Quick Links")
        self.links_menu.update([rumps.MenuItem("Loading...")])

        # Team Stats submenu
        self.stats_menu = rumps.MenuItem("📊 Team Stats")
        self.stats_menu.update([rumps.MenuItem("Loading...")])

        # Game Text generator
        self.game_text_item = rumps.MenuItem("💬 Game Text", callback=self.copy_game_text)

        # Refresh item
        self.refresh_item = rumps.MenuItem("🔄 Refresh Now", callback=self.manual_refresh)

        # Settings submenu
        self.settings_menu = rumps.MenuItem("⚙️ Settings")

        notif_menu = rumps.MenuItem("Notifications")
        self.notif_game_starting = rumps.MenuItem(
            "Game Starting Soon", callback=self.toggle_notification
        )
        self.notif_final_score = rumps.MenuItem(
            "Final Score", callback=self.toggle_notification
        )
        self.notif_scoring_plays = rumps.MenuItem(
            "Scoring Plays", callback=self.toggle_notification
        )
        self.notif_lineup_posted = rumps.MenuItem(
            "Lineup Posted", callback=self.toggle_notification
        )
        for item, key in (
            (self.notif_game_starting, "game_starting"),
            (self.notif_final_score, "final_score"),
            (self.notif_scoring_plays, "scoring_plays"),
            (self.notif_lineup_posted, "lineup_posted"),
        ):
            item._config_key = key
            notif_menu.update([item])
        self._sync_notification_states()

        # Favorite team picker: League → Division → Team
        self.team_menu = rumps.MenuItem("⭐ Favorite Team")
        self.team_items: Dict[int, rumps.MenuItem] = {}
        for league_name, league_id in LEAGUES.items():
            league_item = rumps.MenuItem(league_name)
            for div_id in LEAGUE_DIVISIONS[league_id]:
                div_item = rumps.MenuItem(DIVISION_NAMES[div_id])
                for team in sorted(
                    (t for t in MLB_TEAMS if t.division_id == div_id),
                    key=lambda t: t.name,
                ):
                    team_item = rumps.MenuItem(team.name, callback=self.select_team)
                    team_item._team = team
                    self.team_items[team.id] = team_item
                    div_item.update([team_item])
                league_item.update([div_item])
            self.team_menu.update([league_item])
        self.no_mlb_item = rumps.MenuItem("None — don't follow MLB", callback=self.unfollow_mlb)
        self.team_menu.update([None, self.no_mlb_item])

        check_updates_item = rumps.MenuItem("Check for Updates…", callback=self.check_updates)
        edit_config_item = rumps.MenuItem("Edit Config", callback=self.edit_config)
        quit_item = rumps.MenuItem("Quit", callback=self.quit_app)

        self.settings_menu.update([
            self.team_menu, notif_menu, check_updates_item, edit_config_item, quit_item,
        ])
        self._update_team_items()

        self.menu = [
            *self.espn_rows,
            self.top_line_1,
            self.top_line_2,
            self.top_line_3,
            self.top_line_4,
            self.top_line_5,
            None,  # separator
            self.todays_game_menu,
            self.plays_menu,
            self.schedule_menu,
            self.lineup_menu,
            self.rotation_menu,
            *self.espn_menus,
            None,  # separator
            self.scores_menu,
            *self.espn_score_menus.values(),
            self.standings_menu,
            self.magic_menu,
            self.odds_menu,
            self.weather_menu,
            None,  # separator
            self.links_menu,
            self.stats_menu,
            self.game_text_item,
            self.refresh_item,
            None,  # separator
            self.settings_menu,
        ]

    # ------------------------------------------------------------------
    # Notification helpers
    # ------------------------------------------------------------------

    def _sync_notification_states(self) -> None:
        """Read config and set .state on each notification menu item."""
        notifs = self.config.get("notifications", {})
        self.notif_game_starting.state = int(notifs.get("game_starting", True))
        self.notif_final_score.state = int(notifs.get("final_score", True))
        self.notif_scoring_plays.state = int(notifs.get("scoring_plays", False))
        self.notif_lineup_posted.state = int(notifs.get("lineup_posted", False))

    def toggle_notification(self, sender: rumps.MenuItem) -> None:
        """Toggle a notification preference on/off."""
        sender.state = not sender.state
        config_key = getattr(sender, "_config_key", None)
        if config_key:
            if not isinstance(self.config.get("notifications"), dict):
                self.config["notifications"] = {}
            self.config["notifications"][config_key] = bool(sender.state)
            save_config(self.config)

    # ------------------------------------------------------------------
    # Favorite team
    # ------------------------------------------------------------------

    def select_team(self, sender: rumps.MenuItem) -> None:
        """Team picker callback: make the chosen team the favorite."""
        team = getattr(sender, "_team", None)
        if team is None or (team == self.team and self.follow_mlb):
            return
        set_primary_team(self.config, team)
        save_config(self.config)
        # Show the pick right away; the data follows from the refresh.
        for item in self.team_items.values():
            item.state = int(item._team == team)
        # Own job name, so it queues behind (not gets dropped by) a
        # refresh that's already running.
        self.worker.submit("switch_team", self._refresh_all_work, self._update_all_menus)

    def unfollow_mlb(self, _sender: Any) -> None:
        """Team picker: stop following MLB (hides the baseball menus)."""
        if not self.follow_mlb:
            return
        remove_league_favorites(self.config, "mlb")
        save_config(self.config)
        self.worker.submit("switch_team", self._refresh_all_work, self._update_all_menus)

    def _sync_team(self) -> None:
        """Adopt the config's favorite team, resetting per-team state if it
        changed. Runs on the worker thread at the start of a full refresh
        (team picker, Refresh Now after editing the config)."""
        self.follow_mlb = follows_league(self.config, "mlb")
        self.espn.configure(favorite_refs(self.config))
        team = primary_team(self.config)
        if team == self.team:
            return
        logging.info("Favorite team changed: %s -> %s", self.team.key, team.key)
        self.team = team
        self.schedule_data = []
        self.game_state = {"state": "off", "game": None, "game_pk": None}
        self.live_data = {}
        self.lineup_data = []
        self.scoring_plays = []
        self._plays_game_pk = None
        self.line_score = {}
        self.odds_data = {}
        self._odds_fetched = ""
        self.weather_data = {}
        self.team_stats = {}
        self.previous_my_score = None
        self.final_revert_time = None
        self._starting_soon_pk = None
        self._score_watch_pk = None
        self._lineup_seen_pk = None

    def _update_team_items(self) -> None:
        """Refresh menu items whose text depends on the favorite team."""
        for team_id, item in self.team_items.items():
            item.state = int(self.follow_mlb and team_id == self.team.id)
        self.no_mlb_item.state = int(not self.follow_mlb)
        self.team_menu.title = (
            f"⭐ Favorite MLB Team: {self.team.nickname}" if self.follow_mlb
            else "⭐ Favorite MLB Team: None"
        )
        self.notif_scoring_plays.title = (
            f"{self.team.nickname} Scoring Plays" if self.follow_mlb
            and not self.espn.followed else "Scoring Plays"
        )
        self.links_menu.clear()
        mlb_team = self.team if self.follow_mlb else None
        for link in quick_links(self.config, mlb_team, self.espn.links()):
            item = rumps.MenuItem(link.get("name", link["url"]), callback=self.open_link)
            item._url = link["url"]
            self.links_menu.update([item])

    def _favorite_ids(self) -> set:
        return {t.id for t in favorite_teams(self.config) if t.league == "mlb"} | {self.team.id}

    def _read_team_cache(self, name: str) -> dict:
        """Read a cache that belongs to one team — empty if it's another's."""
        data = read_cache(name)
        if data and data.get("team", LEGACY_CACHE_TEAM) != self.team.key:
            return {}
        return data

    def _write_team_cache(self, name: str, payload: dict) -> None:
        write_cache(name, {**payload, "team": self.team.key})

    # ------------------------------------------------------------------
    # Action callbacks
    # ------------------------------------------------------------------

    def open_link(self, sender: rumps.MenuItem) -> None:
        """Open sender._url in the default browser."""
        url = getattr(sender, "_url", None)
        if url:
            webbrowser.open(url)

    def check_updates(self, _sender: Any) -> None:
        """Menu callback: check GitHub for a newer release in the background."""
        self.worker.submit("check_updates", self._check_updates_work)

    def _check_updates_work(self) -> None:
        """Compare APP_VERSION with the latest GitHub release.

        Uses notifications instead of modal dialogs — modal alerts can't
        come to the front from a menu-bar-only (LSUIElement) app and would
        freeze the app in an invisible modal loop. If an update exists,
        the release page opens in the browser directly.
        """
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                timeout=10,
            )
            resp.raise_for_status()
            release = resp.json()
            latest = release.get("tag_name", "").lstrip("v")
            url = release.get(
                "html_url", f"https://github.com/{GITHUB_REPO}/releases/latest"
            )
        except Exception as exc:
            logging.exception("check_updates failed: %s", exc)
            self.send_notification(
                "Check for Updates", "Couldn't reach GitHub — try again later."
            )
            return

        def as_tuple(version: str) -> tuple:
            try:
                return tuple(int(p) for p in version.split("."))
            except ValueError:
                return (0,)

        if latest and as_tuple(latest) > as_tuple(APP_VERSION):
            self.send_notification(
                "Update Available",
                f"Version {latest} is out (you have {APP_VERSION}) — opening the download page…",
            )
            webbrowser.open(url)
        else:
            self.send_notification(
                "Up to Date", f"You're on the latest version ({APP_VERSION}). ⚾"
            )

    def edit_config(self, _sender: Any) -> None:
        """Open CONFIG_PATH with the default editor."""
        subprocess.Popen(["open", str(CONFIG_PATH)])

    def quit_app(self, _sender: Any) -> None:
        """Quit the application."""
        rumps.quit_application()

    @staticmethod
    def _noop(_sender: Any) -> None:
        """No-op callback so menu items render as enabled (not greyed out)."""
        pass

    def _item(self, title: str) -> rumps.MenuItem:
        """Create an info-only menu item that appears enabled."""
        return rumps.MenuItem(title, callback=self._noop)

    @staticmethod
    def _set_mono_title(item: rumps.MenuItem, text: str) -> None:
        """Set a menu row in a monospaced font so columns line up."""
        item.title = text
        try:
            font = NSFont.monospacedSystemFontOfSize_weight_(11.0, 0.0)
            astr = NSAttributedString.alloc().initWithString_attributes_(
                text, {NSFontAttributeName: font}
            )
            item._menuitem.setAttributedTitle_(astr)
        except Exception as exc:
            logging.debug("mono title unavailable: %s", exc)

    @staticmethod
    def _apply_lines(items: List[rumps.MenuItem], lines: List[str]) -> None:
        """Set titles on fixed menu rows, hiding unused '—' placeholders."""
        for item, text in zip(items, lines):
            item.title = text
            try:
                item._menuitem.setHidden_(text == "—")
            except Exception:
                pass

    def copy_game_text(self, _sender: Any) -> None:
        """Generate a witty game text and copy to clipboard."""
        text = generate_game_text(
            self.game_state, self.live_data, self.schedule_data, self.team
        )
        try:
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            rumps.notification(APP_NAME, "Game Text Copied! 📋", text)
        except Exception as exc:
            logging.exception("copy_game_text failed: %s", exc)

    def manual_refresh(self, _sender: Any) -> None:
        """Trigger a full refresh, reloading config from disk."""
        self.config = load_config()
        self.refresh_all(None)

    def send_notification(self, title: str, message: str) -> None:
        """Send a macOS notification (safe to call from the worker thread)."""
        AppHelper.callAfter(rumps.notification, APP_NAME, title, message)

    # ------------------------------------------------------------------
    # Title / top section updates
    # ------------------------------------------------------------------

    _TITLE_COLORS = {
        "green": NSColor.systemGreenColor,
        "red": NSColor.systemRedColor,
        "yellow": NSColor.systemYellowColor,
    }

    def _set_status_title(self, text: str, color: Optional[str] = None) -> None:
        """Set the menu bar title, optionally colored green/red/yellow.

        Always sets a real NSAttributedString — clearing the attributed
        title with nil makes AppKit render emoji in monochrome text style
        (the ⚾ becomes a flat dark circle).
        """
        self.title = text
        try:
            button = self._nsapp.nsstatusitem.button()
            if color is None:
                attrs = {}  # default attributes: colored emoji, standard font
            else:
                attrs = {
                    NSForegroundColorAttributeName: self._TITLE_COLORS[color](),
                    NSFontAttributeName: NSFont.menuBarFontOfSize_(0),
                }
            astr = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
            button.setAttributedTitle_(astr)
        except Exception as exc:
            # Before the app is running there's no status item yet — plain
            # title (set above) still applies once it exists.
            logging.debug("colored title unavailable: %s", exc)

    def update_title(self) -> None:
        """Set the menu bar title from the favorites' games.

        The first favorite (in config order) with a live game wins; failing
        that, one that just finished (held 30 minutes). Scores are colored
        green/red/yellow for your team winning/losing/tied. Otherwise the
        icon of your first favorite's sport.
        """
        best = None
        mlb_seen = False
        for order, (league, ref) in enumerate(favorite_refs(self.config)):
            if league == "mlb":
                # Only the first MLB favorite (the one followed) has live data
                if mlb_seen or not self.follow_mlb:
                    continue
                mlb_seen = True
                candidate = self._mlb_title_candidate()
            else:
                followed = self.espn.find(league, ref)
                candidate = self.espn.title_candidate(followed) if followed else None
            if candidate and (best is None or (candidate.rank, order) < best[0]):
                best = ((candidate.rank, order), candidate)
        if best:
            self._set_status_title(best[1].text, best[1].color)
        else:
            self._set_status_title(self._idle_icon())

    def _idle_icon(self) -> str:
        refs = favorite_refs(self.config)
        if refs and refs[0][0] in espn.LEAGUES:
            return espn.LEAGUES[refs[0][0]].emoji
        return "⚾"

    def _mlb_title_candidate(self) -> Optional[TitleCandidate]:
        """The followed MLB team's title: live '2-5 ▼7' or final '2-5 F'
        (held for 30 minutes), colored by your team winning/losing/tied."""
        state = self.game_state.get("state", "off")
        game = self.game_state.get("game")
        if state == "live" and game and self.live_data:
            side = team_side(game, self.team.id)
            ld = self.live_data
            my_runs = ld.get(f"{side}_runs", 0)
            opp_side = "home" if side == "away" else "away"
            opp_runs = ld.get(f"{opp_side}_runs", 0)
            color = "green" if my_runs > opp_runs else ("red" if my_runs < opp_runs else "yellow")
            half_arrow = "▲" if ld.get("half") == "Top" else "▼"
            score = f"{ld.get('away_runs', 0)}-{ld.get('home_runs', 0)}"
            return TitleCandidate(0, f"{score} {half_arrow}{ld.get('inning', '')}", color)
        if state == "final" and game:
            if self.final_revert_time and now_local() >= self.final_revert_time:
                return None
            side = team_side(game, self.team.id)
            teams = game.get("teams", {})
            my_score = teams.get(side, {}).get("score", 0) or 0
            opp_side = "home" if side == "away" else "away"
            opp_score = teams.get(opp_side, {}).get("score", 0) or 0
            away_score = teams.get("away", {}).get("score", 0) or 0
            home_score = teams.get("home", {}).get("score", 0) or 0
            color = "green" if my_score > opp_score else ("red" if my_score < opp_score else "yellow")
            return TitleCandidate(1, f"{away_score}-{home_score} F", color)
        return None

    def update_top_section(self) -> None:
        """Update the five context-aware lines at the top of the menu."""
        state = self.game_state.get("state", "off")
        game = self.game_state.get("game")
        lines = ["—", "—", "—", "—", "—"]

        if state == "live" and game and self.live_data:
            ld = self.live_data
            side = team_side(game, self.team.id)
            opp_side = "home" if side == "away" else "away"
            away_abbr = ld.get("away_abbr", "AWY")
            home_abbr = ld.get("home_abbr", "HME")
            away_runs = ld.get("away_runs", 0)
            home_runs = ld.get("home_runs", 0)
            inning_ord = ld.get("inning_ordinal", "")
            half = ld.get("half", "")
            balls = ld.get("balls", 0)
            strikes = ld.get("strikes", 0)
            outs = ld.get("outs", 0)
            runners = ld.get("runners", [])
            pitcher = ld.get("pitcher", "")
            batter = ld.get("batter", "")
            tv = get_tv_broadcast(game, self.team.id)
            lines[0] = f"{away_abbr} {away_runs} — {home_abbr} {home_runs}  |  {half} {inning_ord}"
            lines[1] = f"Runners: {', '.join(runners) if runners else 'None'}  |  {balls}-{strikes}, {outs} out"
            lines[2] = f"P: {pitcher}  vs  B: {batter}"
            lines[3] = f"TV: {tv}"
            lines[4] = "—"

        elif state == "pre" and game:
            side = team_side(game, self.team.id)
            opp_side = "home" if side == "away" else "away"
            opp_name = game["teams"][opp_side]["team"]["name"]
            opp_nick = nickname(game["teams"][opp_side]["team"])
            game_time = format_game_time(game)
            at_symbol = "@" if side == "away" else "vs"
            my_rec = format_record(game, side)
            opp_rec = format_record(game, opp_side)
            tv = get_tv_broadcast(game, self.team.id)
            my_sp = get_probable_pitcher(game, side)
            opp_sp = get_probable_pitcher(game, opp_side)
            lines[0] = f"{self.team.nickname} {at_symbol} {opp_name}  |  {game_time}"
            lines[1] = f"{self.team.abbr} ({my_rec}) vs {opp_nick} ({opp_rec})"
            lines[2] = f"SP: {my_sp['name']} vs {opp_sp['name']}"
            lines[3] = f"TV: {tv}"
            lines[4] = "—"

        elif state == "final" and game:
            side = team_side(game, self.team.id)
            opp_side = "home" if side == "away" else "away"
            teams = game.get("teams", {})
            my_score = teams.get(side, {}).get("score", 0) or 0
            opp_score = teams.get(opp_side, {}).get("score", 0) or 0
            opp_name = game["teams"][opp_side]["team"]["name"]
            opp_nick = nickname(game["teams"][opp_side]["team"])
            rec = format_record(game, side)
            result = "W" if my_score > opp_score else ("L" if my_score < opp_score else "T")
            lines[0] = f"FINAL: {self.team.nickname} {my_score}, {opp_nick} {opp_score}  ({result})"
            lines[1] = f"Season: {rec}"
            lines[2] = "—"
            lines[3] = "—"
            lines[4] = "—"

        else:
            # Off day
            today = now_local().strftime("%Y-%m-%d")
            next_game = next(
                (g for g in self.schedule_data if g.get("officialDate", "") > today),
                None
            )
            lines[0] = "No game today"
            if next_game:
                nside = team_side(next_game, self.team.id)
                nopp_side = "home" if nside == "away" else "away"
                nopp_name = next_game["teams"][nopp_side]["team"]["name"]
                ntime = format_game_time(next_game)
                nat_sym = "@" if nside == "away" else "vs"
                ndate = next_game.get("officialDate", "")
                lines[1] = f"Next: {ndate} {nat_sym} {nopp_name}  {ntime}"
            lines[2] = "—"
            lines[3] = "—"
            lines[4] = "—"

        items = [self.top_line_1, self.top_line_2, self.top_line_3, self.top_line_4, self.top_line_5]
        self._apply_lines(items, lines)

    # ------------------------------------------------------------------
    # Submenu updates
    # ------------------------------------------------------------------

    def update_todays_game_menu(self) -> None:
        """Update the Today's Game submenu with detailed info."""
        state = self.game_state.get("state", "off")
        game = self.game_state.get("game")

        if state == "live":
            self.todays_game_menu.title = "⚾ Live Game"
        else:
            self.todays_game_menu.title = "⚾ Today's Game"

        lines = ["—", "—", "—", "—", "—", "—"]

        if state == "live" and game and self.live_data:
            ld = self.live_data
            side = team_side(game, self.team.id)
            opp_side = "home" if side == "away" else "away"
            away_abbr = ld.get("away_abbr", "AWY")
            home_abbr = ld.get("home_abbr", "HME")
            away_runs = ld.get("away_runs", 0)
            home_runs = ld.get("home_runs", 0)
            inning_ord = ld.get("inning_ordinal", "")
            half = ld.get("half", "")
            balls = ld.get("balls", 0)
            strikes = ld.get("strikes", 0)
            outs = ld.get("outs", 0)
            runners = ld.get("runners", [])
            pitcher = ld.get("pitcher", "")
            batter = ld.get("batter", "")
            my_rec = format_record(game, side)
            tv = get_tv_broadcast(game, self.team.id)
            lines[0] = f"{away_abbr} {away_runs} — {home_abbr} {home_runs}"
            lines[1] = f"{half} {inning_ord}  |  {balls}-{strikes}, {outs} out"
            lines[2] = f"Runners: {', '.join(runners) if runners else 'Bases empty'}"
            lines[3] = f"Pitching: {pitcher}  |  Batting: {batter}"
            lines[4] = f"Record: {my_rec}"
            lines[5] = f"TV: {tv}"

        elif state == "pre" and game:
            side = team_side(game, self.team.id)
            opp_side = "home" if side == "away" else "away"
            opp_name = game["teams"][opp_side]["team"]["name"]
            opp_nick = nickname(game["teams"][opp_side]["team"])
            game_time = format_game_time(game)
            at_symbol = "@" if side == "away" else "vs"
            my_rec = format_record(game, side)
            opp_rec = format_record(game, opp_side)
            my_sp = get_probable_pitcher(game, side)
            opp_sp = get_probable_pitcher(game, opp_side)
            tv = get_tv_broadcast(game, self.team.id)
            venue = game.get("venue", {}).get("name", "")
            lines[0] = f"{self.team.nickname} {at_symbol} {opp_name}  |  {game_time}"
            lines[1] = f"{self.team.abbr} ({my_rec}) vs {opp_nick} ({opp_rec})"
            lines[2] = f"SP — {self.team.abbr}: {my_sp['name']}  vs  OPP: {opp_sp['name']}"
            lines[3] = f"Venue: {venue}"
            lines[4] = f"TV: {tv}"
            lines[5] = "—"

        elif state == "final" and game:
            side = team_side(game, self.team.id)
            opp_side = "home" if side == "away" else "away"
            teams = game.get("teams", {})
            my_score = teams.get(side, {}).get("score", 0) or 0
            opp_score = teams.get(opp_side, {}).get("score", 0) or 0
            opp_name = game["teams"][opp_side]["team"]["name"]
            rec = format_record(game, side)
            result = "W" if my_score > opp_score else ("L" if my_score < opp_score else "T")
            at_symbol = "@" if side == "away" else "vs"
            venue = game.get("venue", {}).get("name", "")
            lines[0] = f"FINAL: {self.team.nickname} {at_symbol} {opp_name}"
            lines[1] = f"Score: {my_score} — {opp_score}  ({result})"
            lines[2] = f"Season Record: {rec}"
            lines[3] = f"Venue: {venue}"
            lines[4] = "—"
            lines[5] = "—"

        else:
            today = now_local().strftime("%Y-%m-%d")
            next_game = next(
                (g for g in self.schedule_data if g.get("officialDate", "") > today),
                None
            )
            lines[0] = "No game today"
            if next_game:
                nside = team_side(next_game, self.team.id)
                nopp_side = "home" if nside == "away" else "away"
                nopp_name = next_game["teams"][nopp_side]["team"]["name"]
                ntime = format_game_time(next_game)
                nat_sym = "@" if nside == "away" else "vs"
                ndate = next_game.get("officialDate", "")
                nsp = get_probable_pitcher(next_game, nside)
                lines[1] = f"Next: {ndate}  {nat_sym} {nopp_name}  {ntime}"
                lines[2] = f"Probable SP: {nsp['name']}"
            lines[3] = "—"
            lines[4] = "—"
            lines[5] = "—"

        tg_items = [
            self.tg_line_1, self.tg_line_2, self.tg_line_3,
            self.tg_line_4, self.tg_line_5, self.tg_line_6,
        ]
        self._apply_lines(tg_items, lines)

        # Line score rows (live and final only)
        box_items = [self.tg_box_1, self.tg_box_2, self.tg_box_3]
        if state in ("live", "final") and self.line_score:
            box_rows = format_line_score(self.line_score, state == "final")
            for item, text in zip(box_items, box_rows):
                self._set_mono_title(item, text)
                try:
                    item._menuitem.setHidden_(False)
                except Exception:
                    pass
        else:
            for item in box_items:
                try:
                    item._menuitem.setHidden_(True)
                except Exception:
                    pass

    def update_plays_menu(self) -> None:
        """List the game's scoring plays in chronological order."""
        self.plays_menu.clear()
        state = self.game_state.get("state", "off")
        if state == "off":
            self.plays_menu.update([self._item("No game today")])
            return
        if state == "pre":
            self.plays_menu.update([self._item("Game hasn't started")])
            return
        if not self.scoring_plays:
            self.plays_menu.update([self._item("No runs yet")])
            return
        rows: List[Any] = []
        seen: set = set()
        for play in self.scoring_plays:
            arrow = "▲" if play["top"] else "▼"
            star = "⭐ " if play["mine"] else ""
            desc = play["description"]
            if len(desc) > 95:
                desc = desc[:94].rstrip() + "…"
            title = f"{star}{arrow}{play['inning']}  {play['away_score']}-{play['home_score']}  {desc}"
            while title in seen:  # rumps menus key by title
                title += "\u2009"
            seen.add(title)
            rows.append(self._item(title))
        self.plays_menu.update(rows)

    def update_schedule_menu(self) -> None:
        """Populate the Schedule submenu with next 10 games."""
        today = now_local().strftime("%Y-%m-%d")
        upcoming = [g for g in self.schedule_data if g.get("officialDate", "") >= today]
        upcoming = upcoming[:10]

        self.schedule_menu.clear()

        for game in upcoming:
            side = team_side(game, self.team.id)
            opp_side = "home" if side == "away" else "away"
            opp_name = game["teams"][opp_side]["team"]["name"]
            date_str = game.get("officialDate", "")
            gtime = format_game_time(game)
            at_sym = "@" if side == "away" else "vs"
            label = f"{date_str}  {at_sym} {opp_name}  {gtime}"

            game_item = rumps.MenuItem(label)
            sp_mine = get_probable_pitcher(game, side)
            sp_opp = get_probable_pitcher(game, opp_side)
            tv = get_tv_broadcast(game, self.team.id)
            game_item.update([
                rumps.MenuItem(f"SP: {sp_mine['name']} vs {sp_opp['name']}", callback=self._noop),
                rumps.MenuItem(f"TV: {tv}", callback=self._noop),
            ])
            self.schedule_menu.update([game_item])

        view_all = rumps.MenuItem("View Full Schedule...", callback=self.open_link)
        view_all._url = self.team.schedule_url
        self.schedule_menu.update([None, view_all])

    def update_lineup_menu(self) -> None:
        """Show batting order 1-9 or a placeholder."""
        self.lineup_menu.clear()
        if not self.lineup_data:
            self.lineup_menu.update([rumps.MenuItem("Lineup not yet announced", callback=self._noop)])
            return
        for i, player in enumerate(self.lineup_data, start=1):
            self.lineup_menu.update([
                rumps.MenuItem(f"{i}. {player['name']} ({player['position']})", callback=self._noop)
            ])

    def update_rotation_menu(self) -> None:
        """Show probable pitchers from upcoming games with stats."""
        today = now_local().strftime("%Y-%m-%d")
        upcoming = [g for g in self.schedule_data if g.get("officialDate", "") >= today]

        seen_ids: set = set()
        pitchers: List[Dict[str, Any]] = []
        for game in upcoming:
            side = team_side(game, self.team.id)
            sp = get_probable_pitcher(game, side)
            pid = sp.get("id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                pitchers.append({
                    "name": sp["name"],
                    "id": pid,
                    "date": game.get("officialDate", ""),
                })

        self.rotation_menu.clear()
        if not pitchers:
            self.rotation_menu.update([rumps.MenuItem("No rotation data available", callback=self._noop)])
            return

        for p in pitchers[:6]:
            stats = self.pitcher_stats_cache.get(p["id"], {})
            wins = stats.get("wins", 0)
            losses = stats.get("losses", 0)
            era = stats.get("era", "—")
            label = f"{p['name']} — Next: {p['date']} ({wins}-{losses}, {era} ERA)"
            self.rotation_menu.update([rumps.MenuItem(label, callback=self._noop)])

    def update_scores_menu(self) -> None:
        """League-wide scoreboard in three sections: live, completed, upcoming."""
        self.scores_menu.clear()
        games = self.league_scores
        if not games:
            self.scores_menu.update([self._item("No MLB games today")])
            return

        live: List[dict] = []
        completed: List[dict] = []
        upcoming: List[dict] = []
        for g in games:
            if g.get("status", {}).get("detailedState", "") in NON_GAME_STATES:
                completed.append(g)
                continue
            status = _game_status(g)
            if status == "live":
                live.append(g)
            elif status == "final":
                completed.append(g)
            else:
                upcoming.append(g)

        rows: List[Any] = []
        favorite_ids = self._favorite_ids()

        def add_section(header: str, section_games: List[dict]) -> None:
            if not section_games:
                return
            if rows:
                rows.append(None)
            rows.append(self._item(header))
            for g in section_games:
                rows.append(self._item(f"   {format_league_game(g, favorite_ids)}"))

        add_section("🔴 Live", live)
        add_section("✅ Completed", completed)
        add_section("🕐 Upcoming", upcoming)
        self.scores_menu.update(rows)

    def update_standings_menu(self) -> None:
        """Full drill-down standings: MLB > League > Division."""
        self.standings_menu.clear()
        if not self.standings_data:
            self.standings_menu.update([rumps.MenuItem("Standings unavailable", callback=self._noop)])
            return

        # Build division-id → records lookup
        div_lookup: Dict[int, list] = {}
        for record in self.standings_data:
            div_id = record.get("division", {}).get("id")
            if div_id is not None:
                div_lookup[div_id] = record.get("teamRecords", [])

        for league_name, league_id in LEAGUES.items():
            league_item = rumps.MenuItem(league_name)
            league_divs = {
                name: did for name, did in DIVISIONS.items()
                if (league_id == 103 and name.startswith("AL")) or
                   (league_id == 104 and name.startswith("NL"))
            }

            # Wild card — teams not in 1st place per division
            wc_teams: List[Dict[str, Any]] = []

            for div_name, div_id in sorted(league_divs.items()):
                team_records = div_lookup.get(div_id, [])
                div_item = rumps.MenuItem(div_name)

                for tr in team_records:
                    tname = tr.get("team", {}).get("name", "Unknown")
                    rec = tr.get("leagueRecord", {})
                    wins = rec.get("wins", 0)
                    losses = rec.get("losses", 0)
                    pct = tr.get("winningPercentage", ".000")
                    gb = tr.get("gamesBack", "—")
                    streak = tr.get("streak", {}).get("streakCode", "—")
                    row = f"{tname}  {wins}-{losses}  {pct}  GB: {gb}  {streak}"
                    div_item.update([rumps.MenuItem(row, callback=self._noop)])
                    # Collect non-division leaders for wild card
                    if tr.get("divisionRank", "1") != "1":
                        wc_teams.append(tr)

                league_item.update([div_item])

            # Wild Card section
            wc_item = rumps.MenuItem("Wild Card")

            def _wc_key(tr: dict) -> int:
                try:
                    return int(tr.get("wildCardRank"))
                except (TypeError, ValueError):
                    return 999

            wc_teams_sorted = sorted(wc_teams, key=_wc_key)[:10]
            for tr in wc_teams_sorted:
                tname = tr.get("team", {}).get("name", "Unknown")
                rec = tr.get("leagueRecord", {})
                wins = rec.get("wins", 0)
                losses = rec.get("losses", 0)
                wcgb = tr.get("wildCardGamesBack", "—")
                wc_item.update([rumps.MenuItem(f"{tname}  {wins}-{losses}  WC GB: {wcgb}", callback=self._noop)])
            league_item.update([wc_item])

            self.standings_menu.update([league_item])

    def update_magic_menu(self) -> None:
        """Show magic numbers: division, playoff berth, wild card, #1 seed."""
        self.magic_menu.clear()
        team = self.team
        mn = compute_magic_numbers(self.standings_data, team.id, team.league_id)
        if not mn:
            self.magic_menu.update([self._item("Standings unavailable")])
            return

        rows: List[Any] = [
            self._item(f"{team.abbr} {mn['wins']}-{mn['losses']}  |  {mn['remaining']} games left"),
            None,
        ]

        # Division
        if mn["division_champ"]:
            rows.append(self._item(f"🏆 {team.division}: ✅ CLINCHED"))
        elif mn["division_eliminated"]:
            rows.append(self._item(f"🏆 {team.division}: ✗ Eliminated"))
        else:
            label = f"🏆 Win {team.division}: {mn['division']}"
            if not mn["division_leader"]:
                label += f"  ({mn['games_back']} GB)"
            rows.append(self._item(label))

        # Playoff berth
        if mn["clinched_postseason"]:
            rows.append(self._item("🎟 Playoff Berth: ✅ CLINCHED"))
        elif mn["division_eliminated"] and mn["wc_eliminated"]:
            rows.append(self._item("🎟 Playoffs: ✗ Eliminated"))
        else:
            rows.append(self._item(f"🎟 Make the Playoffs: {mn['playoffs']}"))

        # Wild card
        if mn["wc_eliminated"]:
            rows.append(self._item("🃏 Wild Card: ✗ Eliminated"))
        else:
            rows.append(self._item(f"🃏 Clinch a Wild Card: {mn['wild_card']}"))

        # 1 seed
        seed_label = f"🥇 Clinch #1 {team.league_abbr} Seed: {mn['top_seed']}"
        if mn["league_rank"] and mn["league_rank"] != "1":
            seed_label += f"  (now #{mn['league_rank']} in {team.league_abbr})"
        rows.append(self._item(seed_label))

        rows.append(None)
        rows.append(self._item(f"Magic # = {team.abbr} wins + rival losses needed (no tiebreakers)"))
        self.magic_menu.update(rows)

    def _refresh_pitcher_stats(self) -> None:
        """Fetch season stats for upcoming probable starters (network calls —
        only invoked from the full/slow refresh paths, not every tick)."""
        today = now_local().strftime("%Y-%m-%d")
        upcoming = [g for g in self.schedule_data if g.get("officialDate", "") >= today]
        pitcher_ids: List[int] = []
        for game in upcoming:
            sp = get_probable_pitcher(game, team_side(game, self.team.id))
            pid = sp.get("id")
            if pid and pid not in pitcher_ids:
                pitcher_ids.append(pid)
        for pid in pitcher_ids[:6]:
            stats = fetch_pitcher_stats(pid)
            if stats:
                self.pitcher_stats_cache[pid] = stats

    def update_odds_menu(self) -> None:
        """Show odds for the team's next game."""
        self.odds_menu.clear()
        api_key = self.config.get("odds_api_key", "")
        if not api_key:
            self.odds_menu.update([rumps.MenuItem("No API key — add odds_api_key to config", callback=self._noop)])
            return
        if not self.odds_data:
            self.odds_menu.update([rumps.MenuItem("No odds available", callback=self._noop)])
            return
        parsed = parse_odds(self.odds_data)
        matchup = parsed.get("matchup", "")
        ml = parsed.get("moneyline", {})
        spread = parsed.get("spread", {})
        total = parsed.get("total", {})
        updated = parsed.get("updated", "")

        away_ml = format_odds_price(ml.get("away", {}).get("price", 0)) if ml.get("away") else "—"
        home_ml = format_odds_price(ml.get("home", {}).get("price", 0)) if ml.get("home") else "—"
        away_sp = spread.get("away", {})
        home_sp = spread.get("home", {})
        over_d = total.get("over", {})
        under_d = total.get("under", {})

        # commence_time is the game's first pitch (UTC ISO) — show local time
        first_pitch = updated
        try:
            first_pitch = (
                dt.datetime.fromisoformat(updated.replace("Z", "+00:00"))
                .astimezone().strftime("%a %-I:%M %p")
            )
        except Exception:
            pass

        self.odds_menu.update([
            rumps.MenuItem(f"Game: {matchup}", callback=self._noop),
            None,
            rumps.MenuItem(f"Moneyline — Away: {away_ml}  Home: {home_ml}", callback=self._noop),
            rumps.MenuItem(
                f"Run Line — Away: {away_sp.get('point', '—')} ({format_odds_price(away_sp.get('price', 0)) if away_sp else '—'})"
                f"  Home: {home_sp.get('point', '—')} ({format_odds_price(home_sp.get('price', 0)) if home_sp else '—'})",
                callback=self._noop,
            ),
            rumps.MenuItem(
                f"O/U: {over_d.get('point', '—')}  Over {format_odds_price(over_d.get('price', 0)) if over_d else '—'}"
                f"  Under {format_odds_price(under_d.get('price', 0)) if under_d else '—'}",
                callback=self._noop,
            ),
            None,
            rumps.MenuItem(f"First Pitch: {first_pitch}", callback=self._noop),
        ])

    def update_weather_menu(self) -> None:
        """Show ballpark weather."""
        self.weather_menu.clear()
        w = self.weather_data
        if not w:
            self.weather_menu.update([rumps.MenuItem("Weather unavailable", callback=self._noop)])
            return
        temp_f = w.get("temp_f", 0)
        temp_c = w.get("temp_c", 0)
        condition = w.get("condition", "Unknown")
        max_f = w.get("max_f", 0)
        min_f = w.get("min_f", 0)
        max_c = w.get("max_c", 0)
        min_c = w.get("min_c", 0)
        wind_mph = w.get("wind_mph", 0)
        wind_kmh = w.get("wind_kmh", 0)
        updated = w.get("updated", "")

        # Name the ballpark the forecast is for
        game = self.game_state.get("game")
        venue_name = (game or {}).get("venue", {}).get("name", "") or self.team.venue

        self.weather_menu.update([
            rumps.MenuItem(f"📍 {venue_name}", callback=self._noop),
            rumps.MenuItem(f"Temp: {temp_f:.0f}°F / {temp_c:.0f}°C", callback=self._noop),
            rumps.MenuItem(f"Condition: {condition}", callback=self._noop),
            rumps.MenuItem(f"H/L: {max_f:.0f}°F / {min_f:.0f}°F  ({max_c:.0f}°C / {min_c:.0f}°C)", callback=self._noop),
            rumps.MenuItem(f"Wind: {wind_mph:.0f} mph ({wind_kmh:.0f} km/h)", callback=self._noop),
            None,
            rumps.MenuItem(f"Updated: {updated}", callback=self._noop),
        ])

    def update_stats_menu(self) -> None:
        """Show the favorite team's stats."""
        self.stats_menu.clear()
        h = self.team_stats.get("hitting", {})
        p = self.team_stats.get("pitching", {})
        if not h and not p:
            self.stats_menu.update([rumps.MenuItem("Stats unavailable", callback=self._noop)])
            return

        record = f"{h.get('wins', '—')}-{h.get('losses', '—')}"
        avg = h.get("avg", "—")
        hr = h.get("homeRuns", "—")
        runs = h.get("runs", "—")
        ops = h.get("ops", "—")
        era = p.get("era", "—")

        self.stats_menu.update([
            rumps.MenuItem(f"Record: {record}", callback=self._noop),
            rumps.MenuItem(f"Batting Avg: {avg}", callback=self._noop),
            rumps.MenuItem(f"Home Runs: {hr}", callback=self._noop),
            rumps.MenuItem(f"Runs Scored: {runs}", callback=self._noop),
            rumps.MenuItem(f"OPS: {ops}", callback=self._noop),
            rumps.MenuItem(f"Team ERA: {era}", callback=self._noop),
        ])

    # ------------------------------------------------------------------
    # Refresh logic
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Other leagues (ESPN): headline rows, team submenus, scoreboards
    # ------------------------------------------------------------------

    @staticmethod
    def _set_hidden(item: rumps.MenuItem, hidden: bool) -> None:
        try:
            item._menuitem.setHidden_(hidden)
        except Exception:
            pass

    def _mlb_items(self) -> List[rumps.MenuItem]:
        return [
            self.top_line_1, self.top_line_2, self.top_line_3, self.top_line_4,
            self.top_line_5, self.todays_game_menu, self.plays_menu,
            self.schedule_menu, self.lineup_menu, self.rotation_menu,
            self.scores_menu, self.standings_menu, self.magic_menu,
            self.odds_menu, self.weather_menu, self.stats_menu, self.game_text_item,
        ]

    def _update_mlb_visibility(self) -> None:
        """Hide the baseball menus when no MLB team is followed."""
        if self.follow_mlb:
            for item in self._mlb_items():
                if item.title != "—":  # placeholder rows manage their own visibility
                    self._set_hidden(item, False)
        else:
            for item in self._mlb_items():
                self._set_hidden(item, True)

    def update_espn_menus(self) -> None:
        followed = self.espn.followed[:ESPN_SLOTS]
        rows = []
        for f in followed:
            if f.team is None:
                continue
            line = espn.headline(f.game, f.team, f.league)
            game = f.game
            # Only games that are on now, today, or just finished
            if line and game and (game.state == LIVE or self._is_today(game)):
                rows.append(line)
        self._apply_lines(self.espn_rows, rows + ["—"] * (ESPN_SLOTS - len(rows)))

        for n, menu in enumerate(self.espn_menus):
            if n >= len(followed):
                self._set_hidden(menu, True)
                continue
            self._set_hidden(menu, False)
            self._fill_espn_team_menu(menu, followed[n])

        followed_leagues = {league.key for league in self.espn.leagues()}
        for key, menu in self.espn_score_menus.items():
            self._set_hidden(menu, key not in followed_leagues)
            if key in followed_leagues:
                self._fill_espn_scores_menu(menu, espn.LEAGUES[key])

    @staticmethod
    def _is_today(game) -> bool:
        return bool(game.start) and game.start.astimezone().date() == now_local().date()

    def _fill_espn_team_menu(self, menu: rumps.MenuItem, f: Followed) -> None:
        league = f.league
        live = f.game is not None and f.game.state == LIVE
        menu.title = f"{league.emoji} {f.label}" + ("  — Live" if live else "")
        menu.clear()
        if f.team is None:
            menu.update([self._item(
                f"⚠️ No {league.name} team matches “{f.ref}” — check favorites in the config"
                if f.unresolved else "Loading..."
            )])
            return
        rows: List[Any] = [self._item(line) for line in espn.status_lines(f.game, f.team, league)]
        if f.game and f.game.state in (LIVE, FINAL):
            box = espn.line_score_rows(f.game, league)
            if box:
                rows.append(None)
                for line in box:
                    item = self._item(line)
                    self._set_mono_title(item, line)
                    rows.append(item)
        if f.game and f.game.state == LIVE and f.game.last_play:
            rows.append(self._item(f"Last play: {f.game.last_play[:90]}"))

        schedule_menu = rumps.MenuItem("📅 Schedule")
        done = [g for g in f.schedule if g.state in (FINAL, POSTPONED)]
        ahead = [g for g in f.schedule if g.state not in (FINAL, POSTPONED)]
        sched_rows = [espn.schedule_row(g, f.team.id, league) for g in done[-4:] + ahead[:8]]
        sched_rows = [r for r in sched_rows if r]
        if sched_rows:
            for text in sched_rows:
                schedule_menu.update([self._item(text)])
        else:
            schedule_menu.update([self._item("Schedule unavailable")])
        link = rumps.MenuItem(f"🔗 {f.team.short_name} on ESPN", callback=self.open_link)
        link._url = league.team_url(f.team.id)
        rows += [None, schedule_menu, link]
        menu.update(rows)

    def _fill_espn_scores_menu(self, menu: rumps.MenuItem, league: espn.League) -> None:
        menu.clear()
        games = self.espn.scoreboards.get(league.key, [])
        favorite_ids = self.espn.team_ids(league.key)
        mode = ((self.config.get("leagues") or {}).get(league.key) or {}).get("scoreboard", "top25")
        if league.ranked and mode != "all":
            games = [
                g for g in games
                if g.away.rank or g.home.rank or any(g.involves(t) for t in favorite_ids)
            ]
        if not games:
            when = "today" if league.daily else "this week"
            menu.update([self._item(f"No {league.name} games {when}")])
            return
        sections = [
            ("🔴 Live", [g for g in games if g.state == LIVE]),
            ("✅ Completed", [g for g in games if g.state in (FINAL, POSTPONED)]),
            ("🕐 Upcoming", [g for g in games if g.state == PRE]),
        ]
        rows: List[Any] = []
        for header, section in sections:
            if not section:
                continue
            if rows:
                rows.append(None)
            rows.append(self._item(header))
            rows += [self._item(f"   {espn.scoreboard_row(g, league, favorite_ids)}") for g in section]
        if league.ranked and mode != "all":
            rows += [None, self._item("Showing ranked teams and your favorites")]
        menu.update(rows)

    def _refresh_espn(self, full: bool) -> int:
        """Refresh ESPN-league favorites (worker thread); returns the
        polling interval their games call for."""
        if not self.espn.followed:
            return 1800
        try:
            for title, message in self.espn.refresh(self.config.get("notifications", {}), full=full):
                self.send_notification(title, message)
            return self.espn.desired_interval()
        except Exception as exc:
            logging.exception("ESPN refresh failed: %s", exc)
            return 1800

    def _update_all_menus(self) -> None:
        """Call all update_* methods."""
        self._update_team_items()
        self._update_mlb_visibility()
        self.update_espn_menus()
        self.update_title()
        self.update_top_section()
        self.update_todays_game_menu()
        self.update_plays_menu()
        self.update_schedule_menu()
        self.update_lineup_menu()
        self.update_rotation_menu()
        self.update_scores_menu()
        self.update_standings_menu()
        self.update_magic_menu()
        self.update_odds_menu()
        self.update_weather_menu()
        self.update_stats_menu()
        if not self.follow_mlb:
            self._update_mlb_visibility()

    def refresh_all(self, _sender: Any) -> None:
        """Queue a full refresh of all data sources."""
        self.worker.submit("full", self._refresh_all_work, self._update_all_menus)

    def _refresh_all_work(self) -> None:
        """Full refresh of all data sources (runs on the worker thread)."""
        logging.info("refresh_all called")
        try:
            self._sync_team()
        except Exception as exc:
            logging.exception("_sync_team failed: %s", exc)
        if self.follow_mlb:
            self._mlb_full_work()
        self._set_interval(min(
            self._mlb_interval() if self.follow_mlb else 1800,
            self._refresh_espn(full=True),
        ))

    def _mlb_full_work(self) -> None:
        """Full MLB refresh for the followed team (worker thread)."""
        try:
            today = now_local().strftime("%Y-%m-%d")
            end = (now_local() + dt.timedelta(days=14)).strftime("%Y-%m-%d")
            self.schedule_data = fetch_schedule(today, end, self.team.id)
            self._write_team_cache("schedule", {"games": self.schedule_data})

            self.league_scores = fetch_league_scores()
            write_cache("league_scores", {"games": self.league_scores})

            self.game_state = detect_game_state(self.schedule_data)
            state = self.game_state.get("state", "off")
            game_pk = self.game_state.get("game_pk")

            # Keep the final-score icon color for 30 min, then revert —
            # also when the app starts up on an already-final game.
            if state == "final":
                if self.final_revert_time is None:
                    self.final_revert_time = now_local() + dt.timedelta(minutes=30)
            else:
                self.final_revert_time = None

            if state in ("live", "final") and game_pk:
                feed = fetch_live_game(game_pk)
                if state == "live":
                    self.live_data = parse_live_data(feed)
                game = self.game_state.get("game")
                if game:
                    self.scoring_plays = parse_scoring_plays(feed, team_side(game, self.team.id))
                    self.line_score = parse_line_score(feed)
                    self._plays_game_pk = game_pk
            elif state != "final":
                self.scoring_plays = []
                self.line_score = {}
            if game_pk:
                # Full refresh loads the lineup silently (no notification) —
                # a lineup that's already up when the app starts isn't news.
                boxscore = fetch_boxscore(game_pk)
                new_lineup = parse_lineup(boxscore, self.team.id)
                if new_lineup:
                    self.lineup_data = new_lineup
                    self._lineup_seen_pk = game_pk
                    self._write_team_cache("lineup", {"lineup": self.lineup_data})

            self.standings_data = fetch_standings()
            write_cache("standings", {"records": self.standings_data})

            self.team_stats = fetch_team_stats(self.team.id)
            self._write_team_cache("team_stats", self.team_stats)

            self._refresh_pitcher_stats()
            self._refresh_odds()

            game = self.game_state.get("game")
            if game:
                my_side = team_side(game, self.team.id)
                venue_team = self.team.id if my_side == "home" else opponent_team_id(game, self.team.id)
            else:
                venue_team = self.team.id
            self.weather_data = fetch_weather(venue_team)
            self._write_team_cache("weather", self.weather_data)

        except Exception as exc:
            logging.exception("refresh_all error: %s", exc)

    def _refresh_odds(self) -> None:
        """Fetch odds only when the cache is stale (>2h).

        The Odds API free tier is 500 requests/month — without this guard
        every app restart burns a request via the startup full refresh.
        """
        api_key = self.config.get("odds_api_key", "")
        if not api_key:
            return
        try:
            fetched = dt.datetime.fromisoformat(self._odds_fetched)
            if now_local() - fetched < dt.timedelta(hours=2):
                return
        except (TypeError, ValueError):
            pass  # no/invalid timestamp — fetch
        self.odds_data = fetch_odds(api_key, self.team)
        self._odds_fetched = now_local().isoformat()
        self._write_team_cache("odds", {"event": self.odds_data, "fetched": self._odds_fetched})

    def _check_lineup(self, game_pk: int) -> None:
        """Fetch the lineup; notify the first time it appears for this game."""
        boxscore = fetch_boxscore(game_pk)
        new_lineup = parse_lineup(boxscore, self.team.id)
        if not new_lineup:
            return
        self.lineup_data = new_lineup
        self._write_team_cache("lineup", {"lineup": self.lineup_data})
        if self._lineup_seen_pk != game_pk:
            self._lineup_seen_pk = game_pk
            notifs = self.config.get("notifications", {})
            if notifs.get("lineup_posted", False):
                self.send_notification("Lineup Posted", f"{self.team.nickname} lineup has been announced!")

    def _set_interval(self, seconds: int) -> None:
        """Adjust the primary timer interval (safe to call from the worker)."""
        AppHelper.callAfter(self._apply_interval, seconds)

    def _apply_interval(self, seconds: int) -> None:
        """Adjust the primary timer interval if it changed (main thread)."""
        try:
            if self.primary_timer.interval != seconds:
                self.primary_timer.interval = seconds
                logging.info("primary timer interval -> %ss", seconds)
        except Exception as exc:
            logging.exception("_set_interval failed: %s", exc)

    def refresh_primary(self, sender: Any) -> None:
        """Primary tick; handles game-state transitions. Interval adapts:
        60s live/near game time, 15 min pre-game/final, 30 min off days."""
        # On first tick, do a full refresh so all data is populated immediately
        if not self._did_initial_refresh:
            self._did_initial_refresh = True
            self.refresh_all(None)
            return
        self.worker.submit("primary", self._refresh_primary_work, self._update_all_menus)

    def _refresh_primary_work(self) -> None:
        """Primary tick body (runs on the worker thread)."""
        logging.info("refresh_primary tick")
        interval = self._mlb_primary_work() if self.follow_mlb else 1800
        interval = min(interval, self._refresh_espn(full=False))
        self._set_interval(interval)

    def _mlb_interval(self) -> int:
        """Polling interval the MLB game state calls for."""
        state = self.game_state.get("state", "off")
        if state == "live":
            return 60
        if state == "final":
            return 900
        if state == "pre":
            game_date_str = (self.game_state.get("game") or {}).get("gameDate", "")
            try:
                start = dt.datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
                minutes_until = (start - now_local().astimezone()).total_seconds() / 60
                return 60 if minutes_until <= 30 else 900
            except Exception:
                return 900
        return 1800

    def _mlb_primary_work(self) -> int:
        """MLB part of the primary tick; returns the interval it wants."""
        interval = 1800
        try:
            today = now_local().strftime("%Y-%m-%d")
            end = (now_local() + dt.timedelta(days=14)).strftime("%Y-%m-%d")
            new_schedule = fetch_schedule(today, end, self.team.id)
            if new_schedule:
                self.schedule_data = new_schedule
                self._write_team_cache("schedule", {"games": self.schedule_data})

            new_scores = fetch_league_scores()
            if new_scores:
                self.league_scores = new_scores
                write_cache("league_scores", {"games": self.league_scores})

            old_state = self.game_state.get("state", "off")
            new_game_state = detect_game_state(self.schedule_data)
            new_state = new_game_state.get("state", "off")
            game_pk = new_game_state.get("game_pk")
            game = new_game_state.get("game")

            # Commit the new state FIRST so a failure below can never leave
            # us stuck re-detecting the same transition forever.
            self.game_state = new_game_state

            # State transition: entering live
            if old_state != "live" and new_state == "live":
                logging.info("Game going live")
                notifs = self.config.get("notifications", {})
                if notifs.get("game_starting", True):
                    self.send_notification("Game Starting", f"The {self.team.nickname} game is underway!")

            # State transition: live ending → final
            if old_state == "live" and new_state == "final":
                logging.info("Game ended — final")
                notifs = self.config.get("notifications", {})
                if notifs.get("final_score", True) and game:
                    side = team_side(game, self.team.id)
                    opp_side = "home" if side == "away" else "away"
                    teams = game.get("teams", {})
                    my_score = teams.get(side, {}).get("score", 0) or 0
                    opp_score = teams.get(opp_side, {}).get("score", 0) or 0
                    opp_nick = nickname(game["teams"][opp_side]["team"])
                    result = "W" if my_score > opp_score else "L"
                    self.send_notification(
                        "Final Score",
                        f"{self.team.nickname} {my_score}, {opp_nick} {opp_score} — {result}"
                    )

            # Final-score icon: hold color 30 min, then revert
            if new_state == "final":
                if self.final_revert_time is None:
                    self.final_revert_time = now_local() + dt.timedelta(minutes=30)
            else:
                self.final_revert_time = None

            # Adaptive polling interval + "starting soon" notification
            if new_state == "live":
                interval = 60
            elif new_state == "final":
                interval = 900
            elif new_state == "off":
                interval = 1800
            elif new_state == "pre":
                minutes_until = None
                game_date_str = (game or {}).get("gameDate", "")
                if game_date_str:
                    try:
                        utc_dt = dt.datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
                        local_dt = utc_dt.astimezone()
                        minutes_until = (local_dt - now_local().astimezone()).total_seconds() / 60
                    except Exception:
                        minutes_until = None
                # Poll fast near first pitch so "live" is caught promptly
                if minutes_until is not None and minutes_until <= 30:
                    interval = 60
                else:
                    interval = 900
                notifs = self.config.get("notifications", {})
                if (
                    minutes_until is not None
                    and 0 < minutes_until <= 15
                    and notifs.get("game_starting", True)
                    and self._starting_soon_pk != game_pk  # only notify once per game
                ):
                    self._starting_soon_pk = game_pk
                    self.send_notification(
                        "Game Starting Soon",
                        f"{self.team.nickname} game starts in ~{int(minutes_until)} min!"
                    )
                # Lineups usually post a few hours before first pitch —
                # start checking within 4 hours of game time.
                if game_pk and minutes_until is not None and minutes_until <= 240:
                    self._check_lineup(game_pk)

            # Final: grab the completed game's scoring plays once
            if new_state == "final" and game_pk and game and self._plays_game_pk != game_pk:
                feed = fetch_live_game(game_pk)
                self.scoring_plays = parse_scoring_plays(feed, team_side(game, self.team.id))
                self.line_score = parse_line_score(feed)
                self._plays_game_pk = game_pk
            if new_state in ("off", "pre"):
                self.scoring_plays = []
                self.line_score = {}

            # If live: fetch live data, check scoring plays, update lineup
            if new_state == "live" and game_pk:
                # New game (or game 2 of a doubleheader): reset score tracking
                if game_pk != self._score_watch_pk:
                    self._score_watch_pk = game_pk
                    self.previous_my_score = None
                feed = fetch_live_game(game_pk)
                self.live_data = parse_live_data(feed)
                if game:
                    self.scoring_plays = parse_scoring_plays(feed, team_side(game, self.team.id))
                    self.line_score = parse_line_score(feed)
                    self._plays_game_pk = game_pk

                # Scoring plays notification
                if game:
                    side = team_side(game, self.team.id)
                    opp_side = "home" if side == "away" else "away"
                    current_my_runs = self.live_data.get(f"{side}_runs", 0) or 0
                    notifs = self.config.get("notifications", {})
                    if (
                        self.previous_my_score is not None
                        and current_my_runs > self.previous_my_score
                        and notifs.get("scoring_plays", False)
                    ):
                        opp_runs = self.live_data.get(f"{opp_side}_runs", 0) or 0
                        away_abbr = self.live_data.get("away_abbr", "AWY")
                        home_abbr = self.live_data.get("home_abbr", "HME")
                        self.send_notification(
                            f"{self.team.nickname} Score!",
                            f"{away_abbr} {self.live_data.get('away_runs', 0)} — "
                            f"{home_abbr} {self.live_data.get('home_runs', 0)}"
                        )
                    self.previous_my_score = current_my_runs

                # Update lineup (also catches in-game substitutions)
                self._check_lineup(game_pk)

        except Exception as exc:
            logging.exception("refresh_primary error: %s", exc)
        return interval

    @rumps.timer(7200)
    def refresh_slow(self, _sender: Any) -> None:
        """Called every 2 hours: standings, team stats, odds, weather."""
        self.worker.submit("slow", self._refresh_slow_work, self._update_slow_menus)

    def _refresh_slow_work(self) -> None:
        """Slow refresh body (runs on the worker thread)."""
        logging.info("refresh_slow tick")
        if self.follow_mlb:
            self._mlb_slow_work()
        self._refresh_espn(full=True)

    def _mlb_slow_work(self) -> None:
        try:
            self.standings_data = fetch_standings()
            write_cache("standings", {"records": self.standings_data})

            self.team_stats = fetch_team_stats(self.team.id)
            self._write_team_cache("team_stats", self.team_stats)

            self._refresh_pitcher_stats()
            self._refresh_odds()

            game = self.game_state.get("game")
            if game:
                my_side = team_side(game, self.team.id)
                venue_team = self.team.id if my_side == "home" else opponent_team_id(game, self.team.id)
            else:
                venue_team = self.team.id
            self.weather_data = fetch_weather(venue_team)
            self._write_team_cache("weather", self.weather_data)

        except Exception as exc:
            logging.exception("refresh_slow error: %s", exc)

    def _update_slow_menus(self) -> None:
        """Rebuild the menus fed by the slow refresh."""
        self.update_espn_menus()
        self.update_standings_menu()
        self.update_magic_menu()
        self.update_stats_menu()
        self.update_rotation_menu()
        self.update_odds_menu()
        self.update_weather_menu()
