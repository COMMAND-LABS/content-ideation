"""STEP: topics -> what YouTube's search box suggests for each topic's query: the phrasings viewers really type.

Each topic's search query goes to YouTube's search autocomplete, the same suggestions you see while
typing in the search box, most popular first. It is free: no API key and no API quota.

    in:   [{"name": "Claude Code", "search_query": "claude code"}]
    out:  [{"name": "Claude Code", "search_query": "claude code",
            "suggestions": ["claude code tutorial", "claude code vs cursor", "claude code mcp", ...]}]

Try it:   uv run python -m steps.youtube_suggestions "claude code"
     or:  curl "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&hl=en&q=claude+code"
"""

import sys

from shared import youtube_api


def youtube_suggestions(topics: list[dict]) -> list[dict]:
    return [topic | {"suggestions": _suggestions_for(topic["search_query"])} for topic in topics]


def _suggestions_for(search_query: str) -> list[str]:
    """YouTube's suggestions, without the query itself."""
    return [s for s in youtube_api.autocomplete(search_query) if s.lower() != search_query.lower()]


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "claude code"
    for suggestion in youtube_suggestions([{"name": query.title(), "search_query": query}])[0]["suggestions"]:
        print(f"  {suggestion}")
