"""STEP: topics with their YouTube phrasings -> the same topics, each with 3 short seed keywords for Google.

Google rarely knows a YouTube phrasing: nobody googles "build and sell ai agent 6 hours course".
So an LLM writes the short keywords people would type into Google about the topic.

    in:   [{"name": "AI agent course", "search_query": "build ai agents",
            "phrasings": ["build ai agents", "build and sell ai agent 6 hours course"]}]
    out:  [{..., "seeds": ["ai agent course", "build ai agents", "ai agent tutorial"],
            "how": [{"phrasing": "build and sell ai agent 6 hours course", "seed": "ai agent course", "change": "shortened"}, ...]}]

`how` shows the transformation: which YouTube phrasing each seed was made from, and what changed.

Try it:   uv run python -m steps.google_seeds          (one small LLM call)
"""

from pydantic import BaseModel

from shared import llm

SEEDS_PER_TOPIC = 3

SEEDS_PROMPT = """\
A YouTube creator wants to know how many people search Google for the numbered video topics below.
Each topic comes with the phrasings viewers type into YouTube. Google's Keyword Planner does not
know such long phrasings: it needs short seed keywords to suggest related searches from.

For each topic, write {limit} seed keywords of 1 to 3 words that people would type into Google about
it, the most specific first. For "build and sell ai agent 6 hours course": "ai agent course",
"build ai agents", "ai agent tutorial". No channel names, no clickbait phrasing.

For each seed, say which phrasing it was made from (copy it exactly) and what you changed:
"kept" (the phrasing as it is), "shortened" (words dropped, nothing added) or "reworded" (said
the way people google it).

Topics:
{topics}
"""


class Seed(BaseModel):
    keyword: str
    from_phrasing: str  # the YouTube phrasing it was made from
    change: str  # "kept", "shortened" or "reworded"


class TopicSeeds(BaseModel):
    topic_number: int
    seeds: list[Seed]


class Seeds(BaseModel):
    topics: list[TopicSeeds]


def google_seeds(topics: list[dict]) -> list[dict]:
    numbered = "\n".join(f'{number}. {topic["name"]}: {", ".join(topic["phrasings"])}' for number, topic in enumerate(topics, start=1))
    answers = llm.ask(SEEDS_PROMPT.format(limit=SEEDS_PER_TOPIC, topics=numbered), Seeds).topics
    made = {answer.topic_number: answer.seeds[:SEEDS_PER_TOPIC] for answer in answers}
    return [topic | _seeds_and_how(topic, made.get(number)) for number, topic in enumerate(topics, start=1)]


def _seeds_and_how(topic: dict, seeds: list[Seed] | None) -> dict:
    """The seed keywords, plus how each one was made. A topic the LLM skipped keeps its own search query as its seed."""
    if not seeds:
        return {"seeds": [topic["search_query"]], "how": [{"phrasing": topic["search_query"], "seed": topic["search_query"], "change": "kept"}]}
    return {"seeds": [seed.keyword for seed in seeds], "how": [{"phrasing": seed.from_phrasing, "seed": seed.keyword, "change": seed.change} for seed in seeds]}


def with_phrasings(topics: list[dict], scored: list[dict]) -> list[dict]:
    """Each topic with every phrasing of it that was scored on YouTube."""
    return [
        {
            "name": topic["name"],
            "search_query": topic["search_query"],
            "phrasings": [idea["search_query"] for idea in scored if idea["topic"] == topic["name"]] or [topic["search_query"]],
        }
        for topic in topics
    ]


if __name__ == "__main__":
    example = {"name": "AI agent course", "search_query": "build ai agents", "phrasings": ["build ai agents", "build and sell ai agent 6 hours course"]}
    for made in google_seeds([example])[0]["how"]:
        print(f'  "{made["phrasing"]}"  ->  "{made["seed"]}"   ({made["change"]})')
