"""STEP: topics with YouTube's suggestions -> the search queries to score: each topic's own query, plus the best suggestions.

An LLM only filters YouTube's suggestions: keep or drop each one (same language, still on topic,
a distinct angle). Which of the kept ones go on is decided by YouTube's own order, most popular
first: the top QUERY_VARIANTS. A pick that is not in YouTube's list is thrown away.

    in:   [{"name": "Claude Code", "search_query": "claude code", "suggestions": ["claude code tutorial", "claude code vs cursor", ...]}]
    out:  [{"search_query": "claude code", "topic": "Claude Code"},
           {"search_query": "claude code tutorial", "topic": "Claude Code"}, ...]

Try it:   uv run python -m steps.query_variants "claude code"     (one autocomplete call, one small LLM call)
"""

import sys

from pydantic import BaseModel

from shared import llm
from shared.settings import config

VARIANTS_PROMPT = """\
A YouTube creator is researching the video topic "{name}" (search query: "{query}").
Below are YouTube's autocomplete suggestions for that query, most popular first.

Keep every suggestion worth researching as a separate video idea. Keep a suggestion only if it is
in the same language as the query, is still about the topic, and targets a distinct angle or
audience (not a rewording of the query or of another kept suggestion; when two are rewordings,
keep the more popular one). Copy each kept suggestion exactly as written. Keep none if none qualify.

Suggestions:
{suggestions}
"""


class Variants(BaseModel):
    queries: list[str]


def query_variants(topics: list[dict]) -> list[dict]:
    queries = {}  # search query -> topic; a query two topics share is only scored once
    for topic in topics:
        for search_query in _variants_of(topic):
            queries.setdefault(search_query, topic["name"])
    return [{"search_query": search_query, "topic": name} for search_query, name in queries.items()]


def _variants_of(topic: dict) -> list[str]:
    """The topic's own query, then the most popular of the suggestions the LLM kept."""
    own, suggestions = topic["search_query"], topic["suggestions"]
    if config.QUERY_VARIANTS == 0 or not suggestions:
        return [own]
    prompt = VARIANTS_PROMPT.format(name=topic["name"], query=own, suggestions="\n".join(f"- {s}" for s in suggestions))
    kept = {query for query in llm.ask(prompt, Variants).queries if query in suggestions}  # no invented queries
    popular_first = [query for query in suggestions if query in kept]  # YouTube's order decides, not the LLM's
    return [own] + popular_first[: config.QUERY_VARIANTS]


if __name__ == "__main__":
    from steps.youtube_suggestions import youtube_suggestions

    query = " ".join(sys.argv[1:]) or "claude code"
    suggested = youtube_suggestions([{"name": query.title(), "search_query": query}])
    print("  YouTube suggests:", suggested[0]["suggestions"])
    print("  queries to score:", [q["search_query"] for q in query_variants(suggested)])
