"""STEP: topics with the keywords Google suggested around them -> topics with only the keywords that are really about them.

Google's suggestions are only loosely related to the seeds. For each topic, an LLM keeps the
keywords of people who want the same thing as the viewers typing the topic's YouTube phrasings.
It is told to be strict: one big, loosely related keyword would otherwise decide the whole topic.
    in:   topics = [{"name": "PDF to text", "search_query": "convert pdf to text", "phrasings": [...]}]
          candidates = {"PDF to text": [{"keyword": "ocr pdf", ...}, {"keyword": "edit pdf", ...}]}
    out:  [{"name": "PDF to text", "search_query": "convert pdf to text", "keywords": ["ocr pdf"], "skip": "", "candidates": 2}]

Try it:   uv run python -m steps.pick_topic_keywords   (one small LLM call)
"""

from pydantic import BaseModel

from shared import llm
from shared.keyword_variants import keyword_lines, variant_groups, with_variants
from shared.settings import config

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


class Picks(BaseModel):
    keywords: list[str]


def biggest_candidates(suggested: list[dict]) -> list[dict]:
    """Of everything Google suggested (biggest first), the keywords worth judging: MIN_MONTHLY_SEARCHES+ a month, at most MAX_TOPIC_KEYWORDS."""
    return [row for row in suggested if row["avg_monthly_searches"] >= config.MIN_MONTHLY_SEARCHES][: config.MAX_TOPIC_KEYWORDS]


def pick_topic_keywords(topics: list[dict], candidates_per_topic: dict[str, list[dict]]) -> list[dict]:
    taken = set()  # a keyword two topics claim stays with the first
    picked_topics = []
    for topic in topics:
        candidates = candidates_per_topic.get(topic["name"], [])
        groups = variant_groups(candidates)
        picked = []
        if groups:  # a topic Google knows no phrasing of costs no LLM call
            phrasings = "\n".join(f"- {phrasing}" for phrasing in topic.get("phrasings") or [topic["search_query"]])
            picked = llm.ask(PICK_PROMPT.format(phrasings=phrasings, keywords=keyword_lines(groups, candidates)), Picks).keywords
        picked_topics.append({"name": topic["name"], "search_query": topic["search_query"], "keywords": with_variants(picked, groups, taken), "skip": "", "candidates": len(candidates)})
    return picked_topics


if __name__ == "__main__":
    def example(keyword, searches):
        return {"keyword": keyword, "avg_monthly_searches": searches, "monthly_searches": {"2026-08": searches, "note": keyword}}

    topic = {"name": "PDF to text", "search_query": "convert pdf to text", "phrasings": ["convert scanned pdf to text", "pdf ocr tutorial"]}
    candidates = {"PDF to text": [example("edit pdf", 90500), example("ocr pdf", 8100), example("pdf to text converter", 5400)]}
    print("  kept:", pick_topic_keywords([topic], candidates)[0]["keywords"])
