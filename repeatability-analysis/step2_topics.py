"""STEP 2: an LLM merges candidates about the same topic and writes one search query per topic.

Each query is then expanded with YouTube autocomplete suggestions (the phrasings viewers really
type); the LLM picks the ones worth scoring as ideas of their own in step 3.
"""

from pydantic import BaseModel

import config
import llm
import youtube
from step1_outliers import Candidate

PROMPT = """\
Below are YouTube videos that massively outperformed their channel's usual views.

Group the videos that are about the same underlying topic, so each topic appears once.
For each topic, write the search query a viewer would type into YouTube to find videos
on that topic. Keep queries short and generic: no channel names, no clickbait phrasing.

Videos:
{videos}
"""

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


class Topic(BaseModel):
    name: str
    search_query: str
    video_ids: list[str]  # the candidate videos this topic was derived from


class Topics(BaseModel):
    topics: list[Topic]


class Variants(BaseModel):
    queries: list[str]


def dedupe_topics(candidates: list[Candidate]) -> list[Topic]:
    videos = "\n".join(
        f'- id={c.video.id} | "{c.video.title}" | {c.video.channel_title} | {c.multiple:.1f}x median'
        for c in candidates
    )
    return llm.ask(PROMPT.format(videos=videos), Topics).topics


def query_variants(topic: Topic) -> list[str]:
    """The topic's own query, then the autocomplete suggestions for it that the LLM picked."""
    if config.QUERY_VARIANTS == 0:
        return [topic.search_query]
    suggestions = [s for s in youtube.autocomplete(topic.search_query) if s.lower() != topic.search_query.lower()]
    if not suggestions:
        return [topic.search_query]
    prompt = VARIANTS_PROMPT.format(
        name=topic.name,
        query=topic.search_query,
        limit=config.QUERY_VARIANTS,
        suggestions="\n".join(f"- {suggestion}" for suggestion in suggestions),
    )
    picks = [query for query in llm.ask(prompt, Variants).queries if query in suggestions]  # no invented queries
    return [topic.search_query] + picks[: config.QUERY_VARIANTS]
