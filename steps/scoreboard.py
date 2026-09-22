"""STEP: topics + their Google keywords + their YouTube scores -> one verdict per topic.

Two tests:
  repeatable  its best-scoring phrasing on YouTube has hits on MIN_HITS+ channels and a score of MIN_SCORE+
  rising      its most searched Google keyword is rising (the rule of steps/rising_keywords.py)

A pipeline that ran both tests gives "make it" when a topic passes both. A pipeline that ran only
one (keywords=None or scored=None) gives that test's verdict alone: "repeatable" or "rising".

    in:   topics, keywords (with trends) or None, scored (the YouTube queries with their scores) or None
    out:  [{"topic": "Claude Code", "verdict": "make it", "repeatability": 3.45, "hit_channels": 13,
            "keyword": "claude code", "monthly_searches": 550000, "yoy_change_pct": 405.6, "search_trend": "rising", ...}]

Try it:   uv run python -m steps.scoreboard           (no API key needed)
"""

import csv
from pathlib import Path

from shared.settings import config
from steps.choose_topics import biggest_keyword, searches_gained
from steps.rising_keywords import why_not_rising
from steps.score_repeatability import is_repeatable

MAKE_IT = "make it"  # both tests passed
REPEATABLE, RISING = "repeatable", "rising"  # the verdicts of a pipeline that ran one test
GOOD = (MAKE_IT, REPEATABLE, RISING)


def scoreboard(topics: list[dict], keywords: list[dict] | None, scored: list[dict] | None) -> list[dict]:
    by_keyword = {row["keyword"]: row for row in keywords or []}
    rows = []
    for topic in topics:
        # A topic can be scored under several phrasings on YouTube: the best one counts.
        phrasings = [idea for idea in scored or [] if idea["topic"] == topic["name"]]
        best = max(phrasings, key=lambda idea: idea["score"], default=None)
        searches = biggest_keyword(topic, by_keyword) if by_keyword else None  # a YouTube-only pipeline has no keywords
        not_rising = why_not_rising(searches) if searches else "Google knows no phrasing of it"
        verdict = _verdict(topic, best, not_rising, youtube=scored is not None, google=keywords is not None)

        rising = sum(not why_not_rising(by_keyword[keyword]) for keyword in topic.get("keywords", []) if keyword in by_keyword)
        rows.append({
            "topic": topic["name"],
            "verdict": verdict,
            "youtube_query": best["search_query"] if best else topic["search_query"],
            "repeatability": best["score"] if best else None,
            "hit_channels": best["hit_channels"] if best else None,
            "keyword": searches["keyword"] if searches else "",
            "monthly_searches": searches["avg_monthly_searches"] if searches else None,
            "yoy_change_pct": searches["yoy_change_pct"] if searches else None,
            "search_trend": searches["trend"] if searches else "",
            "searches_gained": searches_gained(searches) if searches else None,
            "rising_keywords": f"{rising} of {len(topic.get('keywords', []))}",
            "keywords": topic.get("keywords", []),
        })  # fmt: skip
    return sorted(rows, key=lambda row: (row["verdict"] in GOOD, row["repeatability"] or 0, row["searches_gained"] or 0), reverse=True)


def _verdict(topic: dict, best: dict | None, not_rising: str, youtube: bool, google: bool) -> str:
    if topic.get("skip"):
        return f"skipped: {topic['skip']}"
    if youtube and not best:
        return f"not searched on YouTube: outside the {config.MAX_TOPICS} biggest"
    repeatable = best is not None and is_repeatable(best)
    if youtube and google:
        if repeatable:
            return f"repeatable, but {not_rising}" if not_rising else MAKE_IT
        return "not repeatable" if not_rising else "rising, but not repeatable"
    if youtube:
        return REPEATABLE if repeatable else "not repeatable"
    return RISING if not not_rising else f"not rising: {not_rising}"


def show_and_save(rows: list[dict], folder: Path):
    dash = lambda value: "-" if value in (None, "") else value  # noqa: E731
    print(f"{'repeatability':>13}  {'channels':>8}  {'searches/mo':>11}  {'YoY %':>7}  {'verdict':<44}  topic")
    for row in rows:
        print(f"{dash(row['repeatability']):>13}  {dash(row['hit_channels']):>8}  {dash(row['monthly_searches']):>11}  {dash(row['yoy_change_pct']):>7}  {row['verdict'][:44]:<44}  {row['topic']}")
    good = [row["topic"] for row in rows if row["verdict"] in GOOD]
    print(f"\nTopics that passed: {', '.join(good) or 'none this time'}")

    path = folder / "scoreboard.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["topic"])
        writer.writeheader()
        writer.writerows(row | {"keywords": "; ".join(row["keywords"])} for row in rows)
    print(f"Saved to {path}")


if __name__ == "__main__":
    topics = [{"name": "Claude Code", "search_query": "claude code", "keywords": ["claude code"], "skip": ""}]
    keywords = [{"keyword": "claude code", "avg_monthly_searches": 550000, "trend": "rising", "yoy_change_pct": 405.6, "last_12m_avg": 505000, "prior_12m_avg": 99886}]
    scored = [{"search_query": "claude code", "topic": "Claude Code", "score": 3.45, "hit_channels": 13, "hits": []}]
    [row] = scoreboard(topics, keywords, scored)
    print(f"  {row['topic']}: {row['verdict']}   (repeatability {row['repeatability']} on {row['hit_channels']} channels, {row['monthly_searches']:,} searches a month, {row['search_trend']})")
