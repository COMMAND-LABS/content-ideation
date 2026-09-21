"""STEP: outlier videos -> the topics behind them, each with the search query a viewer would type into YouTube.

A title is packaging; the thing another creator can repeat is the topic. An LLM reads each
outlier's title and the start of its description, where the creator says plainly what the video
covers. It groups the outliers about the same topic and writes one short, generic search query per topic.

    in:   [{"video_id": "abc", "title": "I Built a $10k AI Agent in 6 Hours", "description": "A full course on building AI agents with n8n ...",
            "channel": "Some Creator", "multiple": 12.4}, ...]
    out:  [{"name": "Building AI agents", "search_query": "build ai agents", "video_ids": ["abc", "def"]}, ...]

Try it:   uv run python -m steps.outliers_to_topics    (one small LLM call)
"""

from pydantic import BaseModel

from shared import llm

PROMPT = """\
Below are YouTube videos that massively outperformed their channel's usual views, each with its
title and the start of its description.

Judge what a video is about by its title and its description together: a title is often
clickbait, and the description usually says plainly what the video covers. Ignore links,
sponsors and channel promotion in a description.

Group the videos that are about the same underlying topic, so each topic appears once.
For each topic, write the search query a viewer would type into YouTube to find videos
on that topic. The topic is what another creator could make their own video about, not the
details of this one video. Keep queries short (2 to 4 words) and generic: no channel names,
no clickbait phrasing.

Videos:
{videos}
"""


class Topic(BaseModel):
    name: str
    search_query: str
    video_ids: list[str]  # the outlier videos this topic was derived from


class Topics(BaseModel):
    topics: list[Topic]


def outliers_to_topics(outliers: list[dict]) -> list[dict]:
    videos = "\n".join(f'- id={o["video_id"]} | "{o["title"]}" | {o["channel"]} | {o["multiple"]:.1f}x median\n  description: {o.get("description") or "(none)"}' for o in outliers)
    return [topic.model_dump() for topic in llm.ask(PROMPT.format(videos=videos), Topics).topics]


if __name__ == "__main__":
    examples = [
        {"video_id": "a1", "title": "I Built a $10k AI Agent in 6 Hours", "description": "Step by step: an n8n agent that answers support email, and how I sold it.", "channel": "Creator A", "multiple": 12.4},
        {"video_id": "b2", "title": "Build & Sell AI Agents: Full Course", "description": "Everything you need to build AI agents and find your first client.", "channel": "Creator B", "multiple": 9.1},
        {"video_id": "c3", "title": "This Changed How I Work", "description": "My Claude Code setup: subagents, hooks and the commands I use daily.", "channel": "Creator C", "multiple": 7.7},
    ]
    for topic in outliers_to_topics(examples):
        print(f"  {topic['name']:<24} search YouTube for \"{topic['search_query']}\"   from videos {topic['video_ids']}")
