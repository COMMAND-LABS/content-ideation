"""PIPELINE 1: start from Google search. What are people looking for around these seed keywords?

    uv run pipeline1_from_keywords.py "ai agents" "claude code"

    seeds -> keyword ideas -> trends -> rising keywords -> topics -> topics worth a search -> repeatability -> SCOREBOARD

Every step is one small module in steps/, and every step saves its input and its output in
runs/<run id>/, so you can follow a run file by file (or step by step in the viewer).
"""

import argparse

from shared import cache
from shared.run import Run
from steps.choose_topics import choose_topics
from steps.group_into_topics import group_into_topics
from steps.keyword_ideas import keyword_ideas
from steps.rising_keywords import GOES_ON, rising_keywords
from steps.score_repeatability import score_repeatability, show
from steps.scoreboard import scoreboard, show_and_save
from steps.search_trends import search_trends
from viewer import build_viewer


def pipeline(seeds: list[str]):
    run = Run("from-keywords", seeds)
    try:
        run.step("What do people search for on Google?")
        #   in:  ["ai agents", "claude code"]
        #   out: 139 keywords, each with 48 months of searches
        ideas = keyword_ideas(seeds)
        run.save("keyword_ideas", input=seeds, output=ideas)
        print(f"  {len(ideas)} keywords")

        run.step("Is each keyword rising, flat or shrinking?")
        #   in:  {"keyword": "ai agents", "monthly_searches": {"2022-09": 880, ...}}
        #   out: {"keyword": "ai agents", "yoy_change_pct": -3.4, "floor_change_pct": 39.3, "trend": "rising", ...}
        keywords = search_trends(ideas)
        run.save("search_trends", input=ideas, output=keywords)

        run.step("Which keywords are rising, with enough searches to trust?")
        #   in:  139 keywords with a trend
        #   out: the same keywords, each with a verdict: "goes on", or the reason it doesn't
        judged = rising_keywords(keywords)
        run.save("rising_keywords", input=keywords, output=judged)
        rising = [keyword for keyword in judged if keyword["verdict"] == GOES_ON]
        print(f"  {len(rising)} of {len(keywords)} keywords are rising")
        if not rising:
            raise SystemExit("None of the keywords is rising with enough searches. Try other seeds.")

        run.step("Which video topics are they about?  (LLM)")
        #   in:  11 rising keywords
        #   out: [{"name": "AI Agents", "search_query": "ai agents", "keywords": [9 phrasings], "skip": ""}, ...]
        topics = group_into_topics(rising, about=seeds)
        run.save("group_into_topics", input=rising, output=topics)

        run.step("Which topics are worth a YouTube search?")
        #   in:  3 topics
        #   out: the same topics, with "goes_on": true for the ones that gained the most searches
        grouped = topics
        topics = choose_topics(grouped, keywords)
        run.save("choose_topics", input=grouped, output=topics)
        to_search = [{"search_query": topic["search_query"].strip(), "topic": topic["name"]} for topic in topics if topic["goes_on"]]
        if not to_search:
            raise SystemExit("The rising keywords are all too broad, unrelated or brand names. Try more specific seeds.")

        run.step("Is each topic repeatable on YouTube?")
        #   in:  [{"search_query": "claude code", "topic": "Claude Code"}, ...]      one YouTube search per topic
        #   out: [{"search_query": "claude code", "score": 3.45, "hit_channels": 13, "hits": [22 videos]}, ...]
        scored = score_repeatability(to_search)
        run.save("score_repeatability", input=to_search, output=scored)
        show(scored)

        run.step("SCOREBOARD: which topics are repeatable AND rising?")
        #   in:  the topics, their Google keywords, their YouTube scores
        #   out: one row per topic, with a verdict
        rows = scoreboard(topics, keywords, scored)
        run.save("scoreboard", input={"topics": topics, "scored": scored}, output=rows)
        show_and_save(rows, run.folder)
    finally:
        build_viewer.build(open_run=run.id)  # also after a failed run: the viewer shows how far it got


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find video topics that are rising in Google search, then check they are repeatable on YouTube.")
    parser.add_argument("seeds", nargs="+", help='seed keywords, e.g. "ai agents" "claude code"')
    parser.add_argument("--refresh", action="store_true", help="ignore cached YouTube and LLM responses and pull the latest data")
    args = parser.parse_args()
    cache.refresh = args.refresh
    pipeline(args.seeds)
