"""STEP: topics -> the search queries to score: each topic's own query, plus the phrasings viewers really type.

Each query goes to YouTube's search autocomplete (free, no API quota), which answers with what
viewers really type, most popular first. An LLM picks up to QUERY_VARIANTS of them: same language,
still on topic, a distinct angle. A pick that is not in YouTube's list is thrown away.

    in:   [{"name": "Claude Code", "search_query": "claude code"}]
    out:  [{"search_query": "claude code", "topic": "Claude Code"},
           {"search_query": "claude code tutorial for beginners", "topic": "Claude Code"}, ...]

Try it:   uv run python -m steps.query_variants "claude code"     (one autocomplete call, one small LLM call)
     or:  curl "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&hl=en&q=claude+code"
"""

import sys

from pydantic import BaseModel

from shared import llm, youtube_api
from shared.settings import config

VARIANTS_PROMPT = """\
A YouTube creator is researching the video topic "{name}" (search query: "{query}").
Below are YouTube's autocomplete suggestions for that query, most popular first.

Pick up to {limit} suggestions worth researching as separate video ideas. Keep a suggestion only if
it is in the same language as the query, is still about the topic, and targets a distinct angle or
audience (not a rewording of the query or of another pick). Prefer the more popular suggestions.
Copy each pick exactly as written. Pick fewer, or none, if the rest don't qualify.

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
    """The topic's own query, then the autocomplete suggestions for it that the LLM picked."""
    own = topic["search_query"]
    if config.QUERY_VARIANTS == 0:
        return [own]
    suggestions = [s for s in youtube_api.autocomplete(own) if s.lower() != own.lower()]
    if not suggestions:
        return [own]
    prompt = VARIANTS_PROMPT.format(name=topic["name"], query=own, limit=config.QUERY_VARIANTS, suggestions="\n".join(f"- {s}" for s in suggestions))
    picks = [query for query in llm.ask(prompt, Variants).queries if query in suggestions]  # no invented queries
    return [own] + picks[: config.QUERY_VARIANTS]


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "claude code"
    print("  YouTube suggests:", youtube_api.autocomplete(query))
    print("  queries to score:", [q["search_query"] for q in query_variants([{"name": query.title(), "search_query": query}])])
