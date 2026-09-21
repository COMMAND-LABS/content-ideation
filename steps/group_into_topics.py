"""STEP: rising Google keywords -> video topics, each with the search query a viewer would type into YouTube.

An LLM groups the keywords that are about the same video topic, so nine phrasings of "ai agents"
become one topic and cost one YouTube search instead of nine. It also marks the topics a YouTube
search would say nothing about (`skip`): unrelated, too broad, or a bare brand name.
The LLM may only use the keywords it was given: an invented keyword is thrown away.

    in:   [{"keyword": "ai agents", "avg_monthly_searches": 49500, "monthly_searches": {...}}, ...]    about=["ai agents"]
    out:  [{"name": "AI Agents", "search_query": "ai agents", "keywords": ["ai agents", "ai agency", ...], "skip": ""},
           {"name": "Code Geass", "search_query": "code geass", "keywords": ["codegeass"], "skip": "unrelated"}]

Try it:   uv run python -m steps.group_into_topics     (one small LLM call)
"""

from pydantic import BaseModel

from shared import llm
from shared.keyword_variants import keyword_lines, variant_groups, with_variants

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


class KeywordTopic(BaseModel):
    name: str
    search_query: str  # what a viewer would type into YouTube
    keywords: list[str]  # the Google keywords about this topic
    skip: str  # why the topic is not worth a YouTube search ("" when it is)


class KeywordTopics(BaseModel):
    topics: list[KeywordTopic]


def group_into_topics(keywords: list[dict], about: list[str] = ()) -> list[dict]:
    groups = variant_groups(keywords)
    about_text = f" around: {', '.join(about)}" if about else ""
    answer = llm.ask(FIND_PROMPT.format(about=about_text, keywords=keyword_lines(groups, keywords)), KeywordTopics)
    taken = set()
    topics = [topic.model_dump() | {"keywords": with_variants(topic.keywords, groups, taken)} for topic in answer.topics]
    return [topic for topic in topics if topic["keywords"]]


if __name__ == "__main__":
    def example(keyword, searches):
        return {"keyword": keyword, "avg_monthly_searches": searches, "monthly_searches": {"2026-08": searches, "note": keyword}}

    examples = [example("ai agents", 49500), example("what is an ai agent", 8100), example("claude code", 550000), example("code geass", 135000)]
    for topic in group_into_topics(examples, about=["ai agents", "claude code"]):
        print(f"  {topic['name']:<14} search YouTube for \"{topic['search_query']}\"   keywords: {topic['keywords']}   skip: {topic['skip'] or '-'}")
