"""STEP: keywords with a trend -> the same keywords, each with a verdict: "goes on", or the reason it doesn't.

A keyword goes on when its trend is rising or new (KEEP_TRENDS), it has MIN_MONTHLY_SEARCHES+
searches a month (smaller ones are too noisy to trust), and its whole year is not down
YOY_FALLING_PCT or more (a rising floor under a falling year is a keyword past its peak).
At most MAX_GROUPED_KEYWORDS go on, the biggest first.

    in:   [{"keyword": "ai agents", "avg_monthly_searches": 49500, "trend": "rising", "yoy_change_pct": -3.4}, ...]
    out:  [{"keyword": "ai agents", ..., "verdict": "goes on"},
           {"keyword": "ai jobs", ..., "verdict": "search is shrinking"}, ...]

Try it:   uv run python -m steps.rising_keywords      (no API key needed)
"""

from shared.settings import config

GOES_ON = "goes on"


def rising_keywords(keywords: list[dict]) -> list[dict]:
    """The keywords are expected biggest first, the way search_trends returns them."""
    judged, going_on = [], 0
    for keyword in keywords:
        verdict = why_not_rising(keyword) or GOES_ON
        if verdict == GOES_ON:
            going_on += 1
            if going_on > config.MAX_GROUPED_KEYWORDS:
                verdict = "not among the biggest"
        judged.append(keyword | {"verdict": verdict})
    return judged


def why_not_rising(keyword: dict) -> str:
    """Empty when the searches for a keyword are rising, otherwise the reason they are not."""
    if keyword["avg_monthly_searches"] < config.MIN_MONTHLY_SEARCHES:
        return f"under {config.MIN_MONTHLY_SEARCHES} searches a month"
    if keyword["trend"] not in config.KEEP_TRENDS:
        return f"search is {keyword['trend']}"
    if keyword["yoy_change_pct"] is not None and keyword["yoy_change_pct"] <= config.YOY_FALLING_PCT:
        return "the quiet months rose, but searches over the whole year fell"
    return ""


if __name__ == "__main__":
    examples = [
        {"keyword": "ai agents", "avg_monthly_searches": 49500, "trend": "rising", "yoy_change_pct": -3.4},
        {"keyword": "ai jobs", "avg_monthly_searches": 27100, "trend": "shrinking", "yoy_change_pct": -31.0},
        {"keyword": "ai agent for dentists", "avg_monthly_searches": 40, "trend": "rising", "yoy_change_pct": 80.0},
    ]
    for keyword in rising_keywords(examples):
        print(f"  {keyword['keyword']:<24} {keyword['verdict']}")
