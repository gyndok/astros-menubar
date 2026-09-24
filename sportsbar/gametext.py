"""Witty, situation-aware game text for the clipboard."""

from __future__ import annotations

import datetime as dt
import random

from .mlb import format_game_time, get_astros_side, get_probable_pitcher


def generate_game_text(game_state: dict, live_data: dict, schedule_data: list) -> str:
    """Generate a witty, situational text message about the current Astros game."""
    state = game_state.get("state", "off")
    game = game_state.get("game")

    if state == "off" or not game:
        # Off day
        today = dt.datetime.now().strftime("%Y-%m-%d")
        next_game = next(
            (g for g in schedule_data if g.get("officialDate", "") > today), None
        )
        off_day_msgs = [
            "No Astros today. What am I supposed to do with my evening?",
            "Off day. Guess I'll just stare at my Altuve jersey.",
            "No game today. The Astros are resting. I am not.",
            "Day off for the boys. My blood pressure thanks them.",
        ]
        msg = random.choice(off_day_msgs)
        if next_game:
            opp_side = "home" if get_astros_side(next_game) == "away" else "away"
            opp = next_game["teams"][opp_side]["team"]["name"]
            msg += f" Next up: {opp}."
        return msg

    side = get_astros_side(game)
    opp_side = "home" if side == "away" else "away"
    opp_name = game["teams"][opp_side]["team"]["name"].split()[-1]

    if state == "pre":
        time_str = format_game_time(game)
        sp = get_probable_pitcher(game, side)
        pre_msgs = [
            f"Stros vs {opp_name} at {time_str}. {sp['name']} on the bump. Let's ride. 🤘",
            f"{sp['name']} dealing tonight against the {opp_name}. First pitch {time_str}. LFG!",
            f"Game day! {opp_name} have no idea what's coming. {time_str} CT. ⚾",
            f"It's {sp['name']} day. Stros vs {opp_name} at {time_str}. Shoot it! 🚀",
            f"Tonight: Astros. {opp_name}. {time_str}. {sp['name']} vs the world.",
        ]
        return random.choice(pre_msgs)

    if state == "final":
        a_score = game["teams"][side].get("score", 0) or 0
        o_score = game["teams"][opp_side].get("score", 0) or 0
        if a_score == o_score:
            return f"Final: Astros {a_score}, {opp_name} {o_score}. A tie?? In baseball?? What year is it."
        if a_score > o_score:
            win_msgs = [
                f"Astros {a_score}, {opp_name} {o_score}. SHOOT IT HOUSTON TEXAS! 🚀🤘",
                f"W. {a_score}-{o_score} over the {opp_name}. Good guys win again.",
                f"Stros take it {a_score}-{o_score}! {opp_name} in shambles. 😤",
                f"FINAL: Astros {a_score}, {opp_name} {o_score}. Go ahead and play the train horn. 🚂",
                f"Another one. Astros {a_score}, {opp_name} {o_score}. This team is different. 🔥",
            ]
            return random.choice(win_msgs)
        else:
            loss_msgs = [
                f"Astros {a_score}, {opp_name} {o_score}. We don't talk about this one.",
                f"L. {a_score}-{o_score} to the {opp_name}. Delete this from the record books.",
                f"Final: {a_score}-{o_score}. The {opp_name} got lucky. That's my story.",
                f"Stros fall {a_score}-{o_score}. Tomorrow we choose violence. 😤",
                f"Not our night. {a_score}-{o_score}. But 162 games is a marathon not a sprint.",
            ]
            return random.choice(loss_msgs)

    # Live game
    if not live_data:
        return f"Stros vs {opp_name} — game is live but I'm still loading. Hold tight."

    astros_runs = live_data.get(f"{side}_runs", 0)
    opp_runs = live_data.get(f"{opp_side}_runs", 0)
    inning = live_data.get("inning_ordinal", "")
    half = live_data.get("half", "")
    pitcher = live_data.get("pitcher", "someone")
    batter = live_data.get("batter", "someone")
    runners = live_data.get("runners", [])
    outs = live_data.get("outs", 0)
    diff = astros_runs - opp_runs

    if diff > 4:
        blowout_msgs = [
            f"Astros {astros_runs}, {opp_name} {opp_runs} in the {half} {inning}. This is a clinic. 🏥",
            f"{astros_runs}-{opp_runs} Stros. {opp_name} need to call their therapist.",
            f"Astros up {astros_runs}-{opp_runs}. I almost feel bad. Almost. 😏",
            f"It's {astros_runs}-{opp_runs} in the {inning}. {opp_name} already booking flights home.",
        ]
        return random.choice(blowout_msgs)

    if diff > 0:
        leading_msgs = [
            f"Astros {astros_runs}, {opp_name} {opp_runs}. {half} {inning}. We're cooking. 🔥",
            f"Stros up {astros_runs}-{opp_runs} in the {inning}. Keep it rolling boys!",
            f"{astros_runs}-{opp_runs} Astros, {half} {inning}. {batter} at the plate. Let's add on.",
            f"Leading {astros_runs}-{opp_runs} in the {inning}. Vibes are immaculate. ✨",
        ]
        return random.choice(leading_msgs)

    if diff == 0:
        tied_msgs = [
            f"Tied {astros_runs}-{opp_runs} in the {half} {inning}. Someone needs to be a hero.",
            f"All knotted up {astros_runs}-{opp_runs}, {half} {inning}. Clench time. 😬",
            f"{astros_runs}-{opp_runs} tie game in the {inning}. This is why we watch baseball.",
            f"Tied at {astros_runs} in the {inning}. {batter} up. DO SOMETHING.",
        ]
        return random.choice(tied_msgs)

    if diff >= -2:
        close_trail_msgs = [
            f"Astros down {astros_runs}-{opp_runs} in the {half} {inning}. Not worried. Yet. 😅",
            f"{opp_runs}-{astros_runs} {opp_name}, {half} {inning}. Plenty of game left. Come on Stros!",
            f"Trailing {astros_runs}-{opp_runs} in the {inning}. This team knows how to come back. 💪",
            f"Down {opp_runs - astros_runs} in the {inning}. {batter} at the plate. Rally caps on! 🧢",
        ]
        return random.choice(close_trail_msgs)

    # Down big
    down_bad_msgs = [
        f"Astros {astros_runs}, {opp_name} {opp_runs} in the {inning}. This is fine. Everything is fine. 🔥🐶🔥",
        f"Down {astros_runs}-{opp_runs}. I'm not panicking, you're panicking.",
        f"{opp_runs}-{astros_runs} {opp_name} in the {inning}. Fade me. 💀",
        f"It's {astros_runs}-{opp_runs} and I'm choosing to believe in miracles.",
    ]
    return random.choice(down_bad_msgs)
