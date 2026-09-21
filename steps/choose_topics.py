"""STEP: topics -> the same topics, marked with which ones are worth a YouTube search.

A YouTube search costs 100 of your 10,000 daily quota units, so at most MAX_TOPICS topics go on:
the ones whose biggest keyword GAINED the most searches on the year before (big AND growing).
Topics the LLM marked to skip never go on.

    in:   topics = [{"name": "AI Agents", "keywords": ["ai agents", "ai agency"], "skip": ""}, ...]
          keywords = the keywords with their trends
    out:  [{"name": "AI Agents", ..., "biggest_keyword": "ai agents", "searches_gained": -1900, "goes_on": true}, ...]

Try it:   uv run python -m steps.choose_topics        (no API key needed)
"""

from shared.settings import config


def choose_topics(topics: list[dict], keywords: list[dict]) -> list[dict]:
    by_keyword = {row["keyword"]: row for row in keywords}
    chosen = []
    for topic in topics:
        biggest = biggest_keyword(topic, by_keyword)
        chosen.append(topic | {"biggest_keyword": biggest["keyword"] if biggest else "", "searches_gained": searches_gained(biggest)})
    chosen.sort(key=lambda topic: (not topic["skip"], topic["searches_gained"]), reverse=True)
    going_on = [topic["name"] for topic in chosen if not topic["skip"]][: config.MAX_TOPICS]
    return [topic | {"goes_on": topic["name"] in going_on} for topic in chosen]


def biggest_keyword(topic: dict, by_keyword: dict[str, dict]) -> dict | None:
    """The most searched of a topic's keywords stands for the topic on Google (None when Google knows no phrasing of it)."""
    return max((by_keyword[keyword] for keyword in topic["keywords"] if keyword in by_keyword), key=lambda row: row["avg_monthly_searches"], default=None)


def searches_gained(keyword: dict | None) -> int:
    """Searches a month in the last 12 months, minus the 12 months before."""
    return (keyword["last_12m_avg"] or 0) - (keyword["prior_12m_avg"] or 0) if keyword else 0


if __name__ == "__main__":
    keywords = [
        {"keyword": "claude code", "avg_monthly_searches": 550000, "last_12m_avg": 505000, "prior_12m_avg": 99886},
        {"keyword": "ai agents", "avg_monthly_searches": 49500, "last_12m_avg": 53758, "prior_12m_avg": 55658},
        {"keyword": "codegeass", "avg_monthly_searches": 135000, "last_12m_avg": 140000, "prior_12m_avg": 120000},
    ]
    topics = [
        {"name": "AI Agents", "search_query": "ai agents", "keywords": ["ai agents"], "skip": ""},
        {"name": "Claude Code", "search_query": "claude code", "keywords": ["claude code"], "skip": ""},
        {"name": "Code Geass", "search_query": "code geass", "keywords": ["codegeass"], "skip": "unrelated"},
    ]
    for topic in choose_topics(topics, keywords):
        print(f"  {topic['name']:<12} gained {topic['searches_gained']:>8,} searches a month   goes on: {topic['goes_on']}")
