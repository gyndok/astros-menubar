# Houston Astros Menu Bar App — Design Spec

**Date:** 2026-04-05
**Status:** Draft

## Overview

A macOS menu bar app for following the Houston Astros throughout the 2026 MLB season. Displays live scores, schedules, lineups, pitching rotations, standings, Vegas odds, and ballpark weather — all from a single ⚾ icon in the menu bar.

Modeled after the existing Japan Trip Countdown app (`~/japan-trip-countdown/`), using the same tech stack: Python + `rumps` for the menu bar, `requests` for API calls, YAML config, and JSON file caching.

## Menu Bar Title

Dynamic icon based on game state:

| Status | Icon |
|---|---|
| No game / Off day | ⚾ |
| Pre-game (game day) | ⚾ |
| Live — Astros winning | ⚾🟢 |
| Live — Tied | ⚾🟡 |
| Live — Astros losing | ⚾🔴 |
| Final — Astros won | ⚾🟢 (reverts to ⚾ after 30 min) |
| Final — Astros lost | ⚾🔴 (reverts to ⚾ after 30 min) |

## Menu Structure

### Top Section (Context-Aware)

The top of the dropdown changes based on game state:

**During a live game:**
```
HOU 4 - TEX 2 (Bot 7th)
Runners: 1st & 3rd, 1 Out
Count: 2-1
Pitching: F. Valdez vs M. Semien
TV: Space City Home Network
```

**Pre-game (game day, before first pitch):**
```
HOU vs TEX — 7:10 PM CT
Probable: F. Valdez (3-1, 2.85) vs N. Eovaldi (2-2, 3.40)
TV: Space City Home Network
```

**Off day:**
```
No game today
Next: HOU @ SEA — Tue Apr 8, 7:10 PM CT
Record: 15-8 (1st AL West, +3.0 GB)
```

### Menu Items

```
[Context-aware top section]
──────────────────────────
⚾ Today's Game              >  (or "Live Game" during game)
   [Live: score, inning, situation, pitchers, TV]
   [Pre-game: matchup, starters, time, TV]
📅 Schedule                  >
   [Next 10 games with date, opponent, time, probable pitcher, TV]
   View Full Schedule...        (opens astros.com/schedule)
👥 Lineup                    >
   [Batting order: 1-9 with position and name]
   [Shows "Lineup not yet announced" if unavailable]
⚾ Starting Rotation         >
   [Each pitcher with next start date, W-L, ERA]
──────────────────────────
📊 Standings                 >
   American League            >
      AL West                 >
         [Team, W, L, PCT, GB]
      AL Central              >
      AL East                 >
      AL Wild Card            >
         [Team, W, L, PCT, WC GB]
   National League            >
      NL West                 >
      NL Central              >
      NL East                 >
      NL Wild Card            >
💰 Vegas Odds                >
   [Next game matchup header]
   Moneyline: HOU -135 / TEX +115
   Run Line: HOU -1.5 (+130) / TEX +1.5 (-150)
   Over/Under: 8.5 (O -110 / U -110)
   Updated: [timestamp]
🌤 Ballpark Weather          >
   [Temp, condition, wind for game-day ballpark]
   [Shows Minute Maid Park or away park]
──────────────────────────
🔗 Quick Links               >
   Astros.com
   MLB.tv
   Space City Home Network
   r/Astros
   Astros on X
📊 Team Stats                >
   Record: 15-8
   Batting Avg: .267
   Home Runs: 42
   Team ERA: 3.15
   vs AL West: 6-2
   Last 10: 7-3
   Streak: W3
🔄 Refresh Now
──────────────────────────
⚙️ Settings                  >
   Notifications              >
      Game Starting Soon        [on/off]
      Final Score               [on/off]
      Astros Scoring Plays      [on/off]
      Lineup Posted             [on/off]
   Edit Config
   Quit
```

## Data Sources

### MLB Stats API (free, no key required)

Base URL: `https://statsapi.mlb.com/api/v1/`

Endpoints used:
- `/schedule` — game schedule, scores, game state, broadcast/TV info
- `/game/{gamePk}/feed/live` — live game data (score, inning, count, runners, pitchers)
- `/game/{gamePk}/boxscore` — lineup and batting order
- `/standings` — division and wild card standings
- `/teams/{teamId}/roster` — current roster
- `/people/{playerId}` — pitcher stats (W-L, ERA)

TV/broadcast info is included in the schedule endpoint response under the `broadcasts` field — no separate data source needed.

Houston Astros team ID: **117**

### The Odds API (free tier, key required)

- URL: `https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/`
- Free tier: 500 requests/month
- Provides: moneyline, run line (spreads), over/under (totals)
- Markets: `h2h`, `spreads`, `totals`

**Setup instructions for user:**
1. Go to https://the-odds-api.com
2. Click "Get API Key" (free tier)
3. Enter email and sign up
4. Copy the API key from your dashboard or confirmation email
5. Paste the key into the app's `config.yaml` under `odds_api_key`

### Open-Meteo (free, no key required)

- URL: `https://api.open-meteo.com/v1/forecast`
- Used for game-day ballpark weather
- Includes a lookup table mapping MLB ballparks to lat/lon coordinates

## Refresh Intervals

| Context | Interval |
|---|---|
| Live game | 60 seconds |
| Game day (pre-game) | 30 minutes |
| Off day | 60 minutes |
| Standings | 2 hours |
| Vegas odds | 2 hours |
| Weather | 2 hours |
| Manual refresh | On-demand via menu item |

The app detects game state on each refresh cycle:
- If a game is live (`gameState` is "Live" or "In Progress"), switch to 60s polling
- When the game ends, revert to 30-min or 60-min interval
- Manual "Refresh Now" triggers an immediate full refresh of all data

## Notifications (All Configurable)

Each notification type can be toggled on/off in Settings and persisted in `config.yaml`:

| Notification | Default | Trigger |
|---|---|---|
| Game Starting Soon | ON | 15 minutes before first pitch |
| Final Score | ON | Game reaches "Final" state |
| Astros Scoring Plays | OFF | Astros score changes (increase) |
| Lineup Posted | OFF | Lineup data becomes available for today's game |

Notifications use `rumps.notification()` (macOS native).

## Configuration

File: `~/.config/astros-menubar/config.yaml`

```yaml
# API Keys
odds_api_key: ""

# Notification preferences
notifications:
  game_starting: true
  final_score: true
  scoring_plays: false
  lineup_posted: false

# Display preferences
show_odds: true
show_weather: true

# Quick Links (customizable)
quick_links:
  - name: "Astros.com"
    url: "https://www.mlb.com/astros"
  - name: "MLB.tv"
    url: "https://www.mlb.com/tv"
  - name: "Space City Home Network"
    url: "https://www.spacecityhomenetwork.com"
  - name: "r/Astros"
    url: "https://www.reddit.com/r/Astros/"
  - name: "Astros on X"
    url: "https://x.com/astros"
```

Cache directory: `~/.config/astros-menubar/cache/`
Log file: `~/.config/astros-menubar/app.log`

## Architecture

Single-file Python application (`astros_menubar.py`), same pattern as the Japan trip app:

### Class: `AstrosMenuBarApp(rumps.App)`

**Initialization:**
- Load config from YAML
- Read cached data (schedule, standings, odds, weather)
- Build menu structure
- Start refresh timers based on current game state

**Core methods:**

| Method | Purpose |
|---|---|
| `_build_menu()` | Creates all menu items and submenus |
| `refresh_all()` | Full refresh of all data sources |
| `refresh_game_state()` | Check schedule, detect live game, update top section |
| `refresh_live_game()` | Poll live game feed for score/inning/situation |
| `refresh_schedule()` | Fetch upcoming 10 games with probable pitchers |
| `refresh_lineup()` | Fetch announced lineup for today's game |
| `refresh_rotation()` | Fetch starting rotation with stats |
| `refresh_standings()` | Fetch all division and wild card standings |
| `refresh_odds()` | Fetch Vegas odds for next game |
| `refresh_weather()` | Fetch weather for game-day ballpark |
| `refresh_stats()` | Fetch team batting/pitching stats |
| `_adjust_timers()` | Switch between live (60s) and idle (30-60 min) intervals |
| `_send_notification()` | Send macOS notification if enabled in config |
| `_read_cache()` / `_write_cache()` | JSON file caching |
| `open_link()` | Open URL in default browser |

**Timer management:**
- A primary timer runs `refresh_game_state()` to detect whether a game is live
- When a live game is detected, a fast timer (60s) is started for `refresh_live_game()`
- When the game ends, the fast timer stops and reverts to the idle schedule
- Separate slower timers handle standings, odds, and weather

### Ballpark Coordinates

A dictionary mapping team IDs to ballpark lat/lon for weather lookups:

```python
BALLPARK_COORDS = {
    117: (29.7573, -95.3555),   # Minute Maid Park (Houston)
    140: (30.2862, -97.7437),   # Globe Life Field (Texas)
    # ... all 30 MLB parks
}
```

## Installation

Same pattern as the Japan trip app:

1. `install.sh` — installs Python dependencies (`rumps`, `requests`, `pyyaml`), creates default config, installs LaunchAgent
2. LaunchAgent plist at `~/Library/LaunchAgents/com.gyndok.astros-menubar.plist` for auto-start on login
3. `uninstall.sh` — kills process, removes LaunchAgent, optionally removes config

## File Layout

```
~/astros-menubar/
  astros_menubar.py          # Main application (~800-1200 lines)
  install.sh                 # Setup script
  uninstall.sh               # Removal script
  README.md                  # Usage docs
  requirements.txt           # rumps, requests, pyyaml
```

## Out of Scope

- Player-level detailed stats (batting averages per player, etc.)
- Historical game results beyond current season
- Multiple team support (Astros only)
- Fantasy baseball integration
- Ticket purchasing
