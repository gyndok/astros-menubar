# ⚾ Astros Menu Bar — User's Guide

Everything the app does, menu by menu.

The app follows the **Houston Astros** out of the box, but it works for any
MLB team — pick yours under ⚙️ Settings → **⭐ Favorite MLB Team**. Wherever
this guide says "Astros", read "your team". It can also follow **NFL,
college football, NBA, and NHL** teams — see
[Other sports](#other-sports-nfl-college-football-nba-nhl).

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

During and after a game it also shows a classic **box score** — innings with
R/H/E totals, filling in live as each half-inning ends:

```
      1  2  3  4  5  6  7  8  9    R  H  E
HOU   1  0  0  0  0  1  0  0  0    2  5  0
TB    0  0  0  0  2  0  1  0  X    3  7  0
```

The `X` means the home team didn't need its last at-bat; extra innings extend
the grid. Like the menu bar score, it sticks around for 30 minutes after the
final.

## 📝 Scoring Plays

Every run of the game in chronological order — half-inning, the score after
the play, and MLB's official play description. **Astros plays are starred ⭐**
so the good news is easy to scan. Updates live during the game and stays
available for 30 minutes after the final; shows "No runs yet" early and
"Game hasn't started" before first pitch.

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

Your team's game is starred ⭐ — and so is any other team you list under
`favorites` in the config. Sections that are empty are hidden.

## 📊 Standings

Full MLB drill-down: pick a league, then a division, for records, winning
percentage, games back, and streaks. Each league also has a **Wild Card**
section ranked by the current wild-card race.

## 🔮 Magic Numbers

How close your team is to clinching, updated all season (shown here for the
Astros — the division and league follow your team):

- **🏆 Win AL West** — MLB's official magic number when published
- **🎟 Make the Playoffs** — any berth (division title or wild card)
- **🃏 Clinch a Wild Card**
- **🥇 Clinch #1 AL Seed** — best record in the league

A magic number is the combined count of **your team's wins + rival losses** that
guarantees the prize — when it hits zero you'll see **✅ CLINCHED** (or
**✗ Eliminated** if a race slips away). Numbers ignore tiebreakers, same as
the ones published on MLB.com.

## Other sports: NFL, college football, NBA, NHL

Add teams from any of these leagues to `favorites` in the config (⚙️ Settings
→ **Edit Config**, then **🔄 Refresh Now**):

```yaml
favorites:
  - league: nfl
    team: HOU          # Texans
  - league: ncaaf      # college football
    team: Texas        # Longhorns
  - league: nba
    team: Rockets
  - league: nhl
    team: Stars
  - league: mlb
    team: HOU          # Astros — or leave MLB out entirely
```

Name teams by abbreviation (`HOU`, `TEX`), full name (`Texas Longhorns`),
short name (`Texas`), or nickname (`Texans`). If a name fits more than one
team — "Tigers" in college football — the team's menu says so; use its
abbreviation instead.

Each team gets:

- **A line at the top of the menu** on game day — start time before the
  game, the live score and clock during it, the final after
- **Its own submenu** (🏈 Texans, 🏀 Rockets, 🏒 Stars) — matchup, records,
  TV, and venue before the game; score and clock while live (plus
  possession, down and distance, red zone, and the last play in football);
  a period-by-period line score; a **📅 Schedule** with results
  (`W 27-13  vs IND`) and upcoming games; and a link to the team's ESPN page
- **The menu bar score** when it's playing — <code>🏈 21-17 Q3</code>,
  <code>🏀 98-96 Q4</code>, <code>🏒 2-1 P2</code> — colored like baseball
  (green winning, red losing, yellow tied) and held 30 minutes after the
  final. `Half`, `End P2`, `OT`, and `SO` (shootout) show up as you'd expect.

**Scoreboards** — **🏈 NFL Scores** and **🏈 College Football Scores** list
the week's games; **🏀 NBA Scores** and **🏒 NHL Scores** list today's. Each
has live, completed, and upcoming sections, with your teams starred and
college poll ranks (`#7 TEX`). The college scoreboard shows ranked teams and
your favorites; to see every FBS game, add:

```yaml
leagues:
  ncaaf:
    scoreboard: all
```

**When several favorites play at once**, the menu bar shows the first one in
your `favorites` list that's live, so list them in the order you care about.
If you don't list an MLB team, the baseball menus disappear.

**Notifications** use the same toggles as baseball: game starting soon (and
underway), final score, and scoring — every touchdown, field goal, or goal
for your team. Basketball would buzz on every basket, so for NBA teams the
scoring toggle instead sends one **Crunch Time** alert when the game is
within 5 points in the last 5 minutes of the 4th quarter or overtime.

Standings, odds, and weather aren't available for these leagues yet.

## 💰 Vegas Odds

Moneyline, run line, and over/under for the Astros game (DraftKings lines).
This is the one feature that needs setup:

1. Get a **free** API key at [the-odds-api.com](https://the-odds-api.com)
2. Open ⚙️ Settings → **Edit Config**
3. Set `odds_api_key: "your-key-here"`, save, then **🔄 Refresh Now**

Without a key the menu simply says so — nothing else is affected.

## 🌤 Ballpark Weather

Current conditions **wherever tonight's game is** — your team's park for
home games, the opponent's park on the road. Temperature, condition, daily
high/low, and wind.

## 🔗 Quick Links

One-click links for your team: its MLB.com page and MLB.tv (plus Space City
Home Network, r/Astros, and the Astros on X for Houston). Replace them with
your own in the config file (see below).

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

### ⭐ Favorite MLB Team

Pick the MLB team the app follows: **American League / National League →
division → team**. The checkmark shows your current team. Switching reloads
everything — schedule, live game, lineup, magic numbers, odds, weather,
links, and the Game Text lines — for the new team right away. Choose
**None — don't follow MLB** to hide the baseball menus (if you only follow other sports).
Teams in other leagues are set in the config (see
[Other sports](#other-sports-nfl-college-football-nba-nhl)).

### Notifications

Four independent toggles (✓ = on):

| Notification | When it fires |
|--------------|---------------|
| **Game Starting Soon** | ~15 minutes before first pitch, and again at first pitch |
| **Final Score** | The moment the game ends, with the score and W/L |
| **Astros Scoring Plays** | Any time your team adds runs (named for your team) |
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
favorites:                  # in priority order for the menu bar score
  - league: mlb             # first MLB team = the one the app follows
    team: HOU               # abbreviation, full name, or nickname
  - league: mlb             # other MLB teams are starred on 🌎 MLB Scores
    team: Dodgers
  - league: nfl             # also: ncaaf (college football), nba, nhl
    team: Texans
  - league: ncaaf
    team: Texas
leagues:
  ncaaf:
    scoreboard: top25       # or "all" for every FBS game
notifications:
  game_starting: true
  final_score: true
  scoring_plays: false
  lineup_posted: false
show_odds: true
show_weather: true
quick_links: auto           # "auto" = links for your team, or your own list:
# quick_links:
#   - name: Astros.com
#     url: https://www.mlb.com/astros
#   - name: MLB.tv
#     url: https://www.mlb.com/tv
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
| NFL, college football, NBA & NHL scores, schedules | ESPN's public site API (free, no key) | 60s while live, 15–30 min otherwise; schedules every 2 hours |

Not affiliated with MLB or the Houston Astros. Go Stros. 🚀
