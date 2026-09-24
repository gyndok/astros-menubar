"""Witty, situation-aware game text for the clipboard.

Messages are templates filled in with the favorite team's nickname
(`{team}`), the opponent (`{opp}`), scores, and so on. Teams can add their
own flavor lines in TEAM_FLAVOR, which join the generic pool.
"""

from __future__ import annotations

import datetime as dt
import random
from typing import Dict, List

from .mlb import (
    format_game_time,
    get_probable_pitcher,
    nickname,
    other_side,
    team_side,
)
from .teams import Team

GENERIC: Dict[str, List[str]] = {
    "off": [
        "No {team} today. What am I supposed to do with my evening?",
        "No game today. The {team} are resting. I am not.",
        "Day off for the boys. My blood pressure thanks them.",
    ],
    "pre": [
        "{team} vs {opp} at {time}. {sp} on the bump. Let's ride. 🤘",
        "{sp} dealing tonight against the {opp}. First pitch {time}. LFG!",
        "Game day! {opp} have no idea what's coming. {time}. ⚾",
        "Tonight: {team}. {opp}. {time}. {sp} vs the world.",
    ],
    "tie_final": [
        "Final: {team} {us}, {opp} {them}. A tie?? In baseball?? What year is it.",
    ],
    "win": [
        "W. {us}-{them} over the {opp}. Good guys win again.",
        "{team} take it {us}-{them}! {opp} in shambles. 😤",
        "Another one. {team} {us}, {opp} {them}. This team is different. 🔥",
    ],
    "loss": [
        "{team} {us}, {opp} {them}. We don't talk about this one.",
        "L. {us}-{them} to the {opp}. Delete this from the record books.",
        "Final: {us}-{them}. The {opp} got lucky. That's my story.",
        "{team} fall {us}-{them}. Tomorrow we choose violence. 😤",
        "Not our night. {us}-{them}. But 162 games is a marathon not a sprint.",
    ],
    "loading": [
        "{team} vs {opp} — game is live but I'm still loading. Hold tight.",
    ],
    "blowout": [
        "{team} {us}, {opp} {them} in the {half} {inning}. This is a clinic. 🏥",
        "{us}-{them} {team}. {opp} need to call their therapist.",
        "{team} up {us}-{them}. I almost feel bad. Almost. 😏",
        "It's {us}-{them} in the {inning}. {opp} already booking flights home.",
    ],
    "leading": [
        "{team} {us}, {opp} {them}. {half} {inning}. We're cooking. 🔥",
        "{team} up {us}-{them} in the {inning}. Keep it rolling boys!",
        "{us}-{them} {team}, {half} {inning}. {batter} at the plate. Let's add on.",
        "Leading {us}-{them} in the {inning}. Vibes are immaculate. ✨",
    ],
    "tied": [
        "Tied {us}-{them} in the {half} {inning}. Someone needs to be a hero.",
        "All knotted up {us}-{them}, {half} {inning}. Clench time. 😬",
        "{us}-{them} tie game in the {inning}. This is why we watch baseball.",
        "Tied at {us} in the {inning}. {batter} up. DO SOMETHING.",
    ],
    "close_trail": [
        "{team} down {us}-{them} in the {half} {inning}. Not worried. Yet. 😅",
        "{them}-{us} {opp}, {half} {inning}. Plenty of game left. Come on {team}!",
        "Trailing {us}-{them} in the {inning}. This team knows how to come back. 💪",
        "Down {deficit} in the {inning}. {batter} at the plate. Rally caps on! 🧢",
    ],
    "down_bad": [
        "{team} {us}, {opp} {them} in the {inning}. This is fine. Everything is fine. 🔥🐶🔥",
        "Down {us}-{them}. I'm not panicking, you're panicking.",
        "{them}-{us} {opp} in the {inning}. Fade me. 💀",
        "It's {us}-{them} and I'm choosing to believe in miracles.",
    ],
}

TEAM_FLAVOR: Dict[str, Dict[str, List[str]]] = {
    "mlb/HOU": {
        "off": ["Off day. Guess I'll just stare at my Altuve jersey."],
        "pre": ["It's {sp} day. Stros vs {opp} at {time}. Shoot it! 🚀"],
        "win": [
            "Astros {us}, {opp} {them}. SHOOT IT HOUSTON TEXAS! 🚀🤘",
            "FINAL: Astros {us}, {opp} {them}. Go ahead and play the train horn. 🚂",
        ],
        "blowout": ["{us}-{them} Stros. {opp} need to call their therapist."],
        "leading": ["Stros up {us}-{them} in the {inning}. Keep it rolling boys!"],
        "close_trail": ["{them}-{us} {opp}, {half} {inning}. Plenty of game left. Come on Stros!"],
    },
}


def _pick(situation: str, team: Team, **fields) -> str:
    pool = GENERIC[situation] + TEAM_FLAVOR.get(team.key, {}).get(situation, [])
    return random.choice(pool).format(team=team.nickname, **fields)


def generate_game_text(
    game_state: dict, live_data: dict, schedule_data: list, team: Team
) -> str:
    """Generate a witty, situational text message about the team's game."""
    state = game_state.get("state", "off")
    game = game_state.get("game")

    if state == "off" or not game:
        today = dt.datetime.now().strftime("%Y-%m-%d")
        next_game = next(
            (g for g in schedule_data if g.get("officialDate", "") > today), None
        )
        msg = _pick("off", team)
        if next_game:
            opp_side = other_side(team_side(next_game, team.id))
            opp = next_game["teams"][opp_side]["team"]["name"]
            msg += f" Next up: {opp}."
        return msg

    side = team_side(game, team.id)
    opp_side = other_side(side)
    opp = nickname(game["teams"][opp_side]["team"])

    if state == "pre":
        sp = get_probable_pitcher(game, side)["name"]
        return _pick("pre", team, opp=opp, time=format_game_time(game), sp=sp)

    if state == "final":
        us = game["teams"][side].get("score", 0) or 0
        them = game["teams"][opp_side].get("score", 0) or 0
        situation = "tie_final" if us == them else ("win" if us > them else "loss")
        return _pick(situation, team, opp=opp, us=us, them=them)

    # Live game
    if not live_data:
        return _pick("loading", team, opp=opp)

    us = live_data.get(f"{side}_runs", 0)
    them = live_data.get(f"{opp_side}_runs", 0)
    diff = us - them
    if diff > 4:
        situation = "blowout"
    elif diff > 0:
        situation = "leading"
    elif diff == 0:
        situation = "tied"
    elif diff >= -2:
        situation = "close_trail"
    else:
        situation = "down_bad"
    return _pick(
        situation, team, opp=opp, us=us, them=them, deficit=them - us,
        inning=live_data.get("inning_ordinal", ""),
        half=live_data.get("half", ""),
        batter=live_data.get("batter", "someone"),
    )
