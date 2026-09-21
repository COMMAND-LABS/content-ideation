"""STEP: topics with their YouTube phrasings -> the same topics, each with 3 short seed keywords for Google.

Google rarely knows a YouTube phrasing: nobody googles "build and sell ai agent 6 hours course".
So an LLM writes the short keywords people would type into Google about the topic.

    in:   [{"name": "AI agent course", "search_query": "build ai agents",
            "phrasings": ["build ai agents", "build and sell ai agent 6 hours course"]}]
    out:  [{..., "seeds": ["ai agent course", "build ai agents", "ai agent tutorial"]}]

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

Topics:
{topics}
"""


class TopicSeeds(BaseModel):
    topic_number: int
    seeds: list[str]


class Seeds(BaseModel):
    topics: list[TopicSeeds]


def google_seeds(topics: list[dict]) -> list[dict]:
    numbered = "\n".join(f'{number}. {topic["name"]}: {", ".join(topic["phrasings"])}' for number, topic in enumerate(topics, start=1))
    answers = llm.ask(SEEDS_PROMPT.format(limit=SEEDS_PER_TOPIC, topics=numbered), Seeds).topics
    seeds = {answer.topic_number: answer.seeds[:SEEDS_PER_TOPIC] for answer in answers}
    return [topic | {"seeds": seeds.get(number) or [topic["search_query"]]} for number, topic in enumerate(topics, start=1)]


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
    print("  seeds:", google_seeds([example])[0]["seeds"])
