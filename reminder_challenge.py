"""Pure helpers for answer-required health reminders."""

import random


DEFAULT_CHALLENGE_CONFIG = {
    "answer_required": False,
    "snooze_minutes": 5,
    "max_snooze_count": 2,
}


def normalize_challenge_config(raw):
    """Return a validated challenge configuration with safe defaults."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "answer_required": raw.get("answer_required") is True,
        "snooze_minutes": (
            raw.get("snooze_minutes")
            if isinstance(raw.get("snooze_minutes"), int)
            and not isinstance(raw.get("snooze_minutes"), bool)
            and raw["snooze_minutes"] > 0
            else DEFAULT_CHALLENGE_CONFIG["snooze_minutes"]
        ),
        "max_snooze_count": (
            raw.get("max_snooze_count")
            if isinstance(raw.get("max_snooze_count"), int)
            and not isinstance(raw.get("max_snooze_count"), bool)
            and raw["max_snooze_count"] >= 0
            else DEFAULT_CHALLENGE_CONFIG["max_snooze_count"]
        ),
    }


def generate_math_challenge(rng=None):
    """Generate a bounded arithmetic expression and its integer answer."""
    rng = rng or random.SystemRandom()
    while True:
        operation = rng.choice(("add", "subtract", "multiply"))
        if operation == "add":
            left, right = rng.randint(10, 99), rng.randint(10, 99)
            expression, answer = f"{left} + {right}", left + right
        elif operation == "subtract":
            left, right = rng.randint(10, 99), rng.randint(10, 99)
            if left < right:
                left, right = right, left
            expression, answer = f"{left} - {right}", left - right
        else:
            left, right = rng.randint(2, 9), rng.randint(2, 9)
            expression, answer = f"{left} × {right}", left * right

        if 10 <= answer <= 999:
            return expression, answer


def is_correct_answer(value, expected):
    """Return whether *value* is an integer representation of *expected*."""
    try:
        return int(str(value).strip()) == expected
    except (TypeError, ValueError):
        return False
