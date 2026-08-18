# ⚾ Astros Menu Bar — User's Guide

Everything the app does, menu by menu.

<p align="center">
  <img src="screenshot.png" alt="Astros Menu Bar on game day" width="420">
</p>

---

## The menu bar icon

The icon itself is a scoreboard. You never have to open the menu to know how
the game is going:

| You see | It means |
|---------|----------|
| ⚾ | No game right now |
| <code>2-5 ▼7</code> in **green** | Game on — Astros winning (score is away-home, ▼7 = bottom of the 7th) |
| <code>6-5 ▲9</code> in **red** | Astros losing (▲9 = top of the 9th) |
| score in **yellow** | Tied |
| <code>2-5 F</code> in green/red | Final — win/loss color, shown for 30 minutes, then back to ⚾ |

The score is always **away team first** (standard scoreboard order), and the
color always tracks the **Astros**, home or away.

---

## The top of the menu

Click the icon and the first few lines adapt to the moment:

- **Before a game** — matchup, first pitch time, records, probable starting
  pitchers, TV broadcast
- **During a game** — score and inning, runners on, ball-strike count and
  outs, current pitcher vs batter, TV
- **After a game** — final score with W/L and the season record
- **Off day** — the next scheduled game and probable starter

## ⚾ Today's Game

The same information as the top section, but fuller — venue, records for both
teams, and during a live game the complete situation (runners, count, outs,
who's pitching, who's batting).

## 📅 Schedule

The next 10 games: date, opponent, home/away (`vs` = home, `@` = away), and
start time in **your** timezone. Hover any game for the pitching matchup and
TV broadcast. "View Full Schedule..." opens mlb.com.

## 👥 Lineup

The batting order 1–9 with positions, once it's posted (usually 2–4 hours
before first pitch). Shows "Lineup not yet announced" until then.

## ⚾ Starting Rotation

Probable starters for upcoming games with their season W-L and ERA, and the
date each pitches next.

## 🌎 MLB Scores

Every game in the league today, in three sections:

- **🔴 Live** — score with the inning (`▲`/`▼` for top/bottom)
- **✅ Completed** — finals; `F/10` means extra innings; `PPD` postponed
- **🕐 Upcoming** — matchup and local start time

The Astros game is starred ⭐. Sections that are empty are hidden.

## 📊 Standings

Full MLB drill-down: pick a league, then a division, for records, winning
percentage, games back, and streaks. Each league also has a **Wild Card**
section ranked by the current wild-card race.

## 🔮 Magic Numbers

How close the Astros are to clinching, updated all season:

- **🏆 Win AL West** — MLB's official magic number when published
- **🎟 Make the Playoffs** — any berth (division title or wild card)
- **🃏 Clinch a Wild Card**
- **🥇 Clinch #1 AL Seed** — best record in the American League

A magic number is the combined count of **Astros wins + rival losses** that
guarantees the prize — when it hits zero you'll see **✅ CLINCHED** (or
**✗ Eliminated** if a race slips away). Numbers ignore tiebreakers, same as
the ones published on MLB.com.

## 💰 Vegas Odds

Moneyline, run line, and over/under for the Astros game (DraftKings lines).
This is the one feature that needs setup:

1. Get a **free** API key at [the-odds-api.com](https://the-odds-api.com)
2. Open ⚙️ Settings → **Edit Config**
3. Set `odds_api_key: "your-key-here"`, save, then **🔄 Refresh Now**

Without a key the menu simply says so — nothing else is affected.

## 🌤 Ballpark Weather

Current conditions **wherever tonight's game is** — Daikin Park for home
games, the opponent's park on the road. Temperature, condition, daily
high/low, and wind.

## 🔗 Quick Links

One-click links: Astros.com, MLB.tv, Space City Home Network, r/Astros, and
the Astros on X. Add your own in the config file (see below).

## 📊 Team Stats

Season batting average, home runs, runs scored, OPS, and team ERA.

## 💬 Game Text

Click it and a witty, situation-aware message about the game lands on your
clipboard, ready to paste into the group text. It knows the difference
between a blowout, a nail-biter, a comeback, an off day, and a loss we
don't talk about. Different every time.

## 🔄 Refresh Now

Forces an immediate refresh of everything. The app already refreshes itself
(every 60 seconds during games and the half hour before first pitch, every
15–30 minutes otherwise) — this is for the impatient.

---

## ⚙️ Settings

### Notifications

Four independent toggles (✓ = on):

| Notification | When it fires |
|--------------|---------------|
| **Game Starting Soon** | ~15 minutes before first pitch, and again at first pitch |
| **Final Score** | The moment the game ends, with the score and W/L |
| **Astros Scoring Plays** | Any time the Astros add runs |
| **Lineup Posted** | When the day's batting order is announced |

If notifications never appear, check **System Settings → Notifications** and
allow them for **Astros Menu Bar** (or **Python** if you run from source).

### Check for Updates…

Compares your version against the latest GitHub release. If there's a newer
one, you get a notification and the download page opens in your browser;
otherwise a notification confirms you're current.

**Updating is drag-and-drop**: download the new zip, drag the app into
Applications (choose Replace), and open it — the old version quits itself
automatically.

### Edit Config

Opens the config file in your default editor. Everything in it:

```yaml
# ~/.config/astros-menubar/config.yaml
odds_api_key: ""            # from the-odds-api.com (free) — enables Vegas Odds
notifications:
  game_starting: true
  final_score: true
  scoring_plays: false
  lineup_posted: false
show_odds: true
show_weather: true
quick_links:                # add/remove/reorder as you like
  - name: Astros.com
    url: https://www.mlb.com/astros
  - name: MLB.tv
    url: https://www.mlb.com/tv
```

After editing, click **🔄 Refresh Now** to apply.

### Quit

Stops the app until you open it again or log back in.

---

## Troubleshooting

- **Menus say "Loading..." or "unavailable"** — usually no internet, or the
  MLB API is briefly down. The app retries on its normal schedule; data
  reappears on its own.
- **App doesn't start at login** — open it once from Applications; it
  installs (and repairs) its own login item automatically.
- **No notifications** — see the Notifications section above.
- **Something looks stuck** — **🔄 Refresh Now**, or quit and reopen.
- **Logs** (for the curious): `~/.config/astros-menubar/app.log`

## Uninstall

Drag the app to the Trash, then optionally remove the leftovers:

```bash
rm -rf ~/.config/astros-menubar ~/Library/LaunchAgents/com.gyndok.astros-menubar.plist
```

(Source installs: run `./uninstall.sh` from the repo instead.)

---

## Where the data comes from

| Data | Source | Refresh |
|------|--------|---------|
| Scores, schedule, lineups, standings, stats | [MLB Stats API](https://statsapi.mlb.com) (free) | 60s in-game, 15–30 min otherwise |
| Standings, team & pitcher stats | MLB Stats API | every 2 hours |
| Vegas odds | [The Odds API](https://the-odds-api.com) (free key) | every 2 hours |
| Weather | [Open-Meteo](https://open-meteo.com) (free) | every 2 hours |

Not affiliated with MLB or the Houston Astros. Go Stros. 🚀
