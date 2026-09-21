"""STEP: topics + their Google keywords + their YouTube scores -> one verdict per topic.

A topic gets "make it" when it passes both tests:
  repeatable  its best-scoring phrasing on YouTube has hits on MIN_HITS+ channels and a score of MIN_SCORE+
  rising      its most searched Google keyword is rising (the rule of steps/rising_keywords.py)

    in:   topics, keywords (with trends), scored (the YouTube queries with their scores)
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

MAKE_IT = "make it"


def scoreboard(topics: list[dict], keywords: list[dict], scored: list[dict]) -> list[dict]:
    by_keyword = {row["keyword"]: row for row in keywords}
    rows = []
    for topic in topics:
        # A topic can be scored under several phrasings on YouTube: the best one counts.
        phrasings = [idea for idea in scored if idea["topic"] == topic["name"]]
        best = max(phrasings, key=lambda idea: idea["score"], default=None)
        searches = biggest_keyword(topic, by_keyword)
        not_rising = why_not_rising(searches) if searches else "Google knows no phrasing of it"

        if topic["skip"]:
            verdict = f"skipped: {topic['skip']}"
        elif not best:
            verdict = f"not searched on YouTube: outside the {config.MAX_TOPICS} biggest"
        elif is_repeatable(best):
            verdict = f"repeatable, but {not_rising}" if not_rising else MAKE_IT
        else:
            verdict = "not repeatable" if not_rising else "rising, but not repeatable"

        rising = sum(not why_not_rising(by_keyword[keyword]) for keyword in topic["keywords"] if keyword in by_keyword)
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
            "rising_keywords": f"{rising} of {len(topic['keywords'])}",
            "keywords": topic["keywords"],
        })  # fmt: skip
    return sorted(rows, key=lambda row: (row["verdict"] == MAKE_IT, row["repeatability"] or 0), reverse=True)


def show_and_save(rows: list[dict], folder: Path):
    dash = lambda value: "-" if value in (None, "") else value  # noqa: E731
    print(f"{'repeatability':>13}  {'channels':>8}  {'searches/mo':>11}  {'YoY %':>7}  {'verdict':<44}  topic")
    for row in rows:
        print(f"{dash(row['repeatability']):>13}  {dash(row['hit_channels']):>8}  {dash(row['monthly_searches']):>11}  {dash(row['yoy_change_pct']):>7}  {row['verdict'][:44]:<44}  {row['topic']}")
    to_make = [row["topic"] for row in rows if row["verdict"] == MAKE_IT]
    print(f"\nTopics to make: {', '.join(to_make) or 'none this time'}")

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
