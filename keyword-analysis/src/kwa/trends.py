"""Trend measures from monthly search volumes.

Search demand is seasonal, so every comparison here is year over year: the
last 12 months against the 12 months before. Both windows contain every
calendar month once, which cancels seasonality.

- yoy_change_pct:   change in average monthly volume (overall demand).
- floor_change_pct: change in the floor, where the floor is the mean of the
                    3 lowest months in a window (the baseline demand that is
                    there even in the quiet season; using 3 months instead of
                    the single minimum keeps one odd month from deciding it).
"""

# Keyword Planner rounds volumes into buckets roughly 20-25% apart, so a
# smaller change than this can be a single bucket step, not a real move.
THRESHOLD_PCT = 20

TREND_FIELDS = [
    "last_12m_avg",
    "prior_12m_avg",
    "yoy_change_pct",
    "floor_last_12m",
    "floor_prior_12m",
    "floor_change_pct",
    "floor_trend",
]


def parse_monthly(packed: str) -> list[tuple[str, int]]:
    """'2026-07:2900 2026-08:2400' -> [('2026-07', 2900), ('2026-08', 2400)]"""
    pairs = (item.split(":") for item in packed.split())
    return sorted((month, int(n)) for month, n in pairs)


def _floor(values: list[int]) -> float:
    return sum(sorted(values)[:3]) / 3


def _change_pct(now: float, before: float) -> float | None:
    return round((now - before) / before * 100, 1) if before else None


def measure(packed: str) -> dict:
    values = [n for _, n in parse_monthly(packed)]
    if len(values) < 24:
        return dict.fromkeys(TREND_FIELDS, "") | {"floor_trend": "needs 24+ months"}

    last, prior = values[-12:], values[-24:-12]
    floor_last, floor_prior = _floor(last), _floor(prior)
    floor_change = _change_pct(floor_last, floor_prior)

    if floor_change is None:
        # no baseline a year ago: the term either just appeared or never had volume
        trend = "new" if sum(last) else "no volume"
    elif floor_change >= THRESHOLD_PCT:
        trend = "rising"
    elif floor_change <= -THRESHOLD_PCT:
        trend = "shrinking"
    else:
        trend = "flat"

    yoy = _change_pct(sum(last) / 12, sum(prior) / 12)
    return {
        "last_12m_avg": round(sum(last) / 12),
        "prior_12m_avg": round(sum(prior) / 12),
        "yoy_change_pct": "" if yoy is None else yoy,
        "floor_last_12m": round(floor_last),
        "floor_prior_12m": round(floor_prior),
        "floor_change_pct": "" if floor_change is None else floor_change,
        "floor_trend": trend,
    }


def monthly_wide(rows: list[dict]) -> list[dict]:
    """One row per keyword, one column per month - easy to scan or chart."""
    parsed = [(r["keyword"], dict(parse_monthly(r["monthly_searches"]))) for r in rows]
    months = sorted({m for _, volumes in parsed for m in volumes})
    return [{"keyword": k} | {m: volumes.get(m, "") for m in months} for k, volumes in parsed]
