"""PIPELINE 4: Google search keyword research, then YouTube confirmation.
What are people looking for around these seed keywords, and is it also repeatable on YouTube?

    uv run pipeline_4_google_search_keyword_research_plus_youtube_confirmation.py "ai agents" "claude code"

Steps 1 to 5 are pipeline 2 (Google search keyword analysis); steps 6 and 7 add the YouTube side.

    seeds -> keyword ideas -> trends -> rising keywords -> topics -> topics worth a search -> repeatability -> SCOREBOARD

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
from steps.score_repeatability import is_repeatable, score_repeatability, show
from steps.scoreboard import scoreboard, show_and_save
from steps.search_trends import search_trends
from viewer import build_viewer


def pipeline(seeds: list[str]):
    run = Run("google-then-youtube", seeds)
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

        run.step("Which topics are worth a YouTube search?")
        #   in:  3 topics
        #   out: the same topics, with "goes_on": true for the ones that gained the most searches
        grouped = topics
        topics = choose_topics(grouped, keywords)
        to_search = [{"search_query": topic["search_query"].strip(), "topic": topic["name"]} for topic in topics if topic["goes_on"]]
        run.save("choose_topics", input=grouped, output=topics, summary={"topics in": len(grouped), "topics that go on to a YouTube search": len(to_search)})
        if not to_search:
            raise SystemExit("The rising keywords are all too broad, unrelated or brand names. Try more specific seeds.")

        run.step("Is each topic repeatable on YouTube?")
        #   in:  [{"search_query": "claude code", "topic": "Claude Code"}, ...]      one YouTube search per topic
        #   out: [{"search_query": "claude code", "score": 3.45, "hit_channels": 13, "hits": [22 videos]}, ...]
        scored = score_repeatability(to_search)
        run.save("score_repeatability", input=to_search, output=scored, summary={"YouTube searches": len(scored), "hit videos found": sum(len(idea["hits"]) for idea in scored), "repeatable": sum(map(is_repeatable, scored))})
        show(scored)

        run.step("SCOREBOARD: which topics are repeatable AND rising?")
        #   in:  the topics, their Google keywords, their YouTube scores
        #   out: one row per topic, with a verdict
        rows = scoreboard(topics, keywords, scored)
        run.save("scoreboard", input={"topics": topics, "scored": scored}, output=rows, summary={"topics": len(rows)} | tally(rows, "verdict"))
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
