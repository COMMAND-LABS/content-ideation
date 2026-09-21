"""Sorts Google search keywords into video topics with an LLM. Used by ../ideate.py.

    uv run keyword_topics.py --keywords keywords.json --about "ai agents" --out topics.json   # find the topics in the keywords
    uv run keyword_topics.py --google-seeds given.json --out seeds.json                       # how would people google these topics?
    uv run keyword_topics.py --topics given.json --out topics.json                            # pick each given topic's keywords

A topic has many phrasings, and YouTube and Google know it under different ones. Judging a topic
(is it repeatable on YouTube AND rising on Google?) only works once its phrasings are together.

keywords.json: [{"keyword": "ai agents", "monthly_searches": 49500, "history": "2022-09:880 2022-10:590 ..."}, ...]
given.json:    [{"name": "AI agents", "search_query": "build ai agents", "phrasings": [what viewers type into YouTube],
                 "candidates": [the keywords Google suggests for it, as above]}, ...]   (--google-seeds adds "seeds" to each topic)
topics.json:   [{"name": ..., "search_query": ..., "keywords": [...], "skip": ""}, ...]
"""

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

import cache
import llm

FIND_PROMPT = """\
A YouTube creator is researching video topics{about}. Below are keywords people search for on Google,
with their searches per month. Copy only the keyword itself, the part before the first "|".

Group the keywords that are about the same video topic, so each topic appears once. For each topic,
write a short name and the search query a viewer would type into YouTube to find videos on that
topic. Keep queries short and generic: no clickbait phrasing. Copy each keyword exactly as written.

Set `skip` to a short reason when searching YouTube for the topic would tell the creator nothing:
- "unrelated": it has nothing to do with what the creator researches (a keyword can look alike and
  still be about something else, such as a TV series or a person)
- "too broad": it could not be one video ("ai")
- "brand name": a bare company or product name people type to reach a website ("chatgpt", "openai").
  A product the creator could make a tutorial about is fine.
Leave `skip` empty otherwise.

Keywords:
{keywords}
"""

SEEDS_PROMPT = """\
A YouTube creator wants to know how many people search Google for the numbered video topics below.
Each topic comes with the phrasings viewers type into YouTube. Google's Keyword Planner does not
know such long phrasings: it needs short seed keywords to suggest related searches from.

For each topic, write {limit} seed keywords of 1 to 3 words that people would type into Google about
it, the most specific first. For "build and sell ai agent 6 hours course": "ai agent course",
"build ai agents", "ai agent tutorial". No channel names, no clickbait phrasing.

Topics:
{topics}
"""

PICK_PROMPT = """\
A YouTube creator is researching a video topic. Viewers find such videos on YouTube by typing:
{phrasings}

Below are keywords Google suggests around it, with their searches per month. Copy only the keyword
itself, the part before the first "|".

List the keywords of people who want the same thing as those viewers. Be strict: leave out a keyword
that is broader (it would also fit many other videos), only loosely related, or about something
else. Copy each keyword exactly as written. List none if none qualifies.

Keywords:
{keywords}
"""


class KeywordTopic(BaseModel):
    name: str
    search_query: str  # what a viewer would type into YouTube
    keywords: list[str]  # the Google keywords about this topic
    skip: str  # why the topic is not worth a YouTube search ("" when it is)


class KeywordTopics(BaseModel):
    topics: list[KeywordTopic]


class TopicSeeds(BaseModel):
    topic_number: int
    seeds: list[str]


class Seeds(BaseModel):
    topics: list[TopicSeeds]


class Picks(BaseModel):
    keywords: list[str]


def find_topics(keywords: list[dict], about: str = "") -> list[KeywordTopic]:
    """The video topics the keywords are about."""
    groups = variant_groups(keywords)
    prompt = FIND_PROMPT.format(about=f" around: {about}" if about else "", keywords=keyword_lines(groups, keywords))
    topics = llm.ask(prompt, KeywordTopics).topics
    taken = set()
    for topic in topics:
        topic.keywords = with_variants(topic.keywords, groups, taken)
    return [topic for topic in topics if topic.keywords]


def google_seeds(given: list[dict], limit: int = 3) -> list[dict]:
    """The given topics, each with the short seed keywords to ask Google about it."""
    numbered = "\n".join(f'{number}. {topic["name"]}: {", ".join(topic["phrasings"])}' for number, topic in enumerate(given, start=1))
    answers = llm.ask(SEEDS_PROMPT.format(limit=limit, topics=numbered), Seeds).topics
    seeds = {answer.topic_number: answer.seeds[:limit] for answer in answers}
    return [topic | {"seeds": seeds.get(number) or [topic["search_query"]]} for number, topic in enumerate(given, start=1)]


def pick_keywords(given: list[dict]) -> list[KeywordTopic]:
    """The given topics, each with the candidates that are really about it (none, if Google knows no phrasing of it)."""
    taken = set()  # a keyword two topics claim stays with the first
    topics = []
    for topic in given:
        groups = variant_groups(topic["candidates"])
        picked = []
        if groups:
            phrasings = "\n".join(f"- {phrasing}" for phrasing in topic.get("phrasings") or [topic["search_query"]])
            prompt = PICK_PROMPT.format(phrasings=phrasings, keywords=keyword_lines(groups, topic["candidates"]))
            picked = llm.ask(prompt, Picks).keywords
        topics.append(KeywordTopic(name=topic["name"], search_query=topic["search_query"], keywords=with_variants(picked, groups, taken), skip=""))
    return topics


def variant_groups(keywords: list[dict]) -> dict[str, list[str]]:
    """Keywords with exactly the same search history are variants Google counts together: the LLM only sees the first.

    Returns first keyword -> every keyword of the group, biggest group first.
    """
    groups = {}
    for row in sorted(keywords, key=lambda row: row["monthly_searches"], reverse=True):
        same_searches = row["history"] if row["monthly_searches"] else row["keyword"]  # no searches: nothing to compare
        groups.setdefault(same_searches, []).append(row["keyword"])
    return {group[0]: group for group in groups.values()}


def keyword_lines(groups: dict[str, list[str]], keywords: list[dict]) -> str:
    searches = {row["keyword"]: row["monthly_searches"] for row in keywords}
    return "\n".join(
        f"- {first} | {searches[first]:,} a month" + (f" | also searched as: {', '.join(group[1:])}" if len(group) > 1 else "")
        for first, group in groups.items()
    )


def with_variants(picked: list[str], groups: dict[str, list[str]], taken: set[str]) -> list[str]:
    """The LLM's picks plus their variants: no invented keywords, and no keyword in two topics."""
    keywords = []
    for keyword in picked:
        if keyword in groups and keyword not in taken:
            taken.add(keyword)
            keywords += groups[keyword]
    return keywords


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sort Google search keywords into video topics.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--keywords", metavar="FILE", help="find the topics in these keywords (JSON, with monthly searches and history)")
    source.add_argument("--google-seeds", metavar="FILE", help="write short Google seed keywords for these topics (JSON)")
    source.add_argument("--topics", metavar="FILE", help="pick the keywords of these topics from their candidates (JSON)")
    parser.add_argument("--out", required=True, metavar="FILE", help="where to write the topics (JSON)")
    parser.add_argument("--about", default="", help="with --keywords: what the creator researches, e.g. the seed keywords")
    parser.add_argument("--refresh", action="store_true", help="ignore the cached LLM answers")
    args = parser.parse_args()
    cache.refresh = args.refresh

    if args.google_seeds:
        seeded = google_seeds(json.loads(Path(args.google_seeds).read_text()))
        Path(args.out).write_text(json.dumps(seeded, indent=2, ensure_ascii=False))
        for topic in seeded:
            print(f"  {topic['name']}  ->  {', '.join(topic['seeds'])}")
        raise SystemExit
    if args.topics:
        topics = pick_keywords(json.loads(Path(args.topics).read_text()))
    else:
        topics = find_topics(json.loads(Path(args.keywords).read_text()), args.about)
    Path(args.out).write_text(json.dumps([topic.model_dump() for topic in topics], indent=2, ensure_ascii=False))

    for topic in topics:
        note = f"  (skipped: {topic.skip})" if topic.skip else ""
        print(f'  {topic.name}  ->  "{topic.search_query}"{note}')
        print(f"      {', '.join(topic.keywords) or 'no keywords'}")
    print(f"\n{len(topics)} topics saved to {args.out}")
