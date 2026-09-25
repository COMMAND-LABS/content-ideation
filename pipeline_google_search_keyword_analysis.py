"""PIPELINE 2: Google search keyword analysis.
What are people looking for around these seed keywords, and which of it is rising?

    uv run pipeline_google_search_keyword_analysis.py "ai agents" "claude code"

    seeds -> keyword ideas -> trends -> rising keywords -> topics -> topics that gained the most -> SCOREBOARD

Needs Google Ads API access and an LLM key. Pipeline 4 is this pipeline plus a YouTube check.
Every step is one small module in steps/, and every step saves its input and its output in
runs/<run id>/, so you can follow a run file by file (or step by step in the viewer).
"""

import argparse

from shared import cache
from shared.run import Run, tally
from steps.choose_topics import choose_topics
from steps.group_into_topics import group_into_topics
from steps.keyword_ideas import MONTHS, by_seed, keyword_ideas
from steps.rising_keywords import GOES_ON, rising_keywords
from steps.scoreboard import scoreboard, show_and_save
from steps.search_trends import search_trends
from viewer import build_viewer


def pipeline(seeds: list[str]):
    run = Run("google-search-keyword-analysis", seeds)
    try:
        run.step("What do people search for on Google?")
        #   in:  ["ai agents", "claude code"]
        #   out: 139 keywords, each with 48 months of searches
        ideas = keyword_ideas(seeds)
        #   saved twice. a, the short version: {"ai agents": {"ai agents": 49500, "what is an ai agent": 8100, ...}, "claude code": {...}, "related": {...}}
        #                b, the full version:  every keyword with its 48 months, which the next step reads
        found = by_seed(seeds, ideas)
        run.save("seeds_to_keywords", part="a", input=seeds, output=found["keywords"], summary=found["summary"])
        run.save("keyword_ideas", part="b", input=seeds, output=ideas, summary={"keywords": len(ideas), "months of searches for each": MONTHS})

        run.step("Is each keyword rising, flat or shrinking?")
        #   in:  {"keyword": "ai agents", "monthly_searches": {"2022-09": 880, ...}}
        #   out: {"keyword": "ai agents", "yoy_change_pct": -3.4, "floor_change_pct": 39.3, "trend": "rising", ...}
        keywords = search_trends(ideas)
        run.save("search_trends", input=ideas, output=keywords, summary={"keywords": len(keywords)} | tally(keywords, "trend"))

        run.step("Which keywords are rising, with enough searches to trust?")
        #   in:  139 keywords with a trend
        #   out: the same keywords, each with a verdict: "goes on", or the reason it doesn't
        judged = rising_keywords(keywords)
        run.save("rising_keywords", input=keywords, output=judged, summary={"keywords": len(judged)} | tally(judged, "verdict"))
        rising = [keyword for keyword in judged if keyword["verdict"] == GOES_ON]
        if not rising:
            raise SystemExit("None of the keywords is rising with enough searches. Try other seeds.")

        run.step("Which video topics are they about?  (LLM)")
        #   in:  11 rising keywords
        #   out: [{"name": "AI Agents", "search_query": "ai agents", "keywords": [9 phrasings], "skip": ""}, ...]
        topics = group_into_topics(rising, about=seeds)
        skipped = [topic for topic in topics if topic["skip"]]
        run.save("group_into_topics", input=rising, output=topics, summary={"rising keywords in": len(rising), "topics out": len(topics), "of which skipped": len(skipped)})

        run.step("Which topics gained the most searches?")
        #   in:  3 topics
        #   out: the same topics, with "goes_on": true for the ones that gained the most searches (the MAX_TOPICS biggest)
        grouped = topics
        topics = choose_topics(grouped, keywords)
        run.save("choose_topics", input=grouped, output=topics, summary={"topics in": len(grouped), "topics worth a video": sum(topic["goes_on"] for topic in topics)})


        run.step("SCOREBOARD: which topics are rising?")
        #   in:  the topics and their Google keywords
        #   out: one row per topic, with a verdict: "rising", or why not
        rows = scoreboard(topics, keywords, None)
        run.save("scoreboard", input={"topics": topics}, output=rows, summary={"topics": len(rows)} | tally(rows, "verdict"))
        show_and_save(rows, run.folder)
    finally:
        build_viewer.build(open_run=run.id)  # also after a failed run: the viewer shows how far it got


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find the video topics that are rising in Google search around your seed keywords.")
    parser.add_argument("seeds", nargs="+", help='seed keywords, e.g. "ai agents" "claude code"')
    parser.add_argument("--refresh", action="store_true", help="ignore cached LLM responses and pull the latest data")
    args = parser.parse_args()
    cache.refresh = args.refresh
    pipeline(args.seeds)
