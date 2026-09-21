"""STEP: keywords with their monthly searches -> the same keywords with a trend: rising, flat, shrinking or new.

Search demand is seasonal, so every comparison is year over year: the last 12 months against the
12 before. Both windows contain every calendar month once, which cancels the seasons. The trend
comes from the FLOOR, the mean of the 3 quietest months of a window: the demand that is there even
when nothing is happening. One spike can't move it.

    in:   [{"keyword": "ai agents", "monthly_searches": {"2022-09": 880, ..., "2026-08": 49500}}, ...]
    out:  [{"keyword": "ai agents", "yoy_change_pct": -3.4, "floor_prior_12m": 29467, "floor_last_12m": 41033,
            "floor_change_pct": 39.3, "trend": "rising", ...}, ...]     biggest first

Try it:   uv run python -m steps.search_trends        (no API key needed)
"""

# Keyword Planner rounds volumes into buckets roughly 20-25% apart, so a smaller change than this
# can be a single bucket step, not a real move.
THRESHOLD_PCT = 20


def search_trends(keywords: list[dict]) -> list[dict]:
    measured = [keyword | measure(keyword["monthly_searches"]) for keyword in keywords]
    return sorted(measured, key=lambda keyword: keyword["avg_monthly_searches"], reverse=True)


def measure(monthly_searches: dict[str, int]) -> dict:
    values = [searches for _, searches in sorted(monthly_searches.items())]
    if len(values) < 24:
        return {"last_12m_avg": None, "prior_12m_avg": None, "yoy_change_pct": None, "floor_last_12m": None, "floor_prior_12m": None, "floor_change_pct": None, "trend": "needs 24+ months"}  # fmt: skip

    last, prior = values[-12:], values[-24:-12]
    floor_last, floor_prior = _floor(last), _floor(prior)
    floor_change = _change_pct(floor_last, floor_prior)

    if floor_change is None:
        trend = "new" if sum(last) else "no volume"  # no baseline a year ago: it either just appeared or never had volume
    elif floor_change >= THRESHOLD_PCT:
        trend = "rising"
    elif floor_change <= -THRESHOLD_PCT:
        trend = "shrinking"
    else:
        trend = "flat"

    return {
        "last_12m_avg": round(sum(last) / 12),
        "prior_12m_avg": round(sum(prior) / 12),
        "yoy_change_pct": _change_pct(sum(last) / 12, sum(prior) / 12),
        "floor_last_12m": round(floor_last),
        "floor_prior_12m": round(floor_prior),
        "floor_change_pct": floor_change,
        "trend": trend,
    }


def _floor(values: list[int]) -> float:
    return sum(sorted(values)[:3]) / 3


def _change_pct(now: float, before: float) -> float | None:
    return round((now - before) / before * 100, 1) if before else None


if __name__ == "__main__":
    # Two years of a keyword whose quiet months doubled, while one spike a year ago keeps the average flat.
    prior = [100, 100, 100, 900, 200, 200, 200, 200, 200, 200, 200, 200]
    last = [200, 200, 200, 300, 250, 250, 250, 250, 250, 250, 250, 250]
    months = {f"{2024 + n // 12}-{n % 12 + 1:02d}": searches for n, searches in enumerate(prior + last)}
    print("in: ", months)
    print("out:", measure(months))
