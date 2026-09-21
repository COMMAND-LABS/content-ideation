"""PIPELINE 2: start from YouTube. What is working for the channels in your niche (CHANNELS_TO_SCAN in config.py)?

    uv run pipeline2_from_youtube.py

    channels -> outliers -> topics -> search queries -> repeatability -> Google seeds -> keyword ideas -> keywords about the topic -> SCOREBOARD

Every step is one small module in steps/, and every step saves its input and its output in
runs/<run id>/, so you can follow a run file by file (or step by step in the viewer).
"""

import argparse

from shared import cache, google_ads
from shared.run import Run, tally
from shared.settings import config
from steps.find_outliers import find_outliers
from steps.google_seeds import google_seeds, with_phrasings
from steps.keyword_ideas import keyword_ideas
from steps.outliers_to_topics import outliers_to_topics
from steps.pick_topic_keywords import biggest_candidates, pick_topic_keywords
from steps.query_variants import query_variants
from steps.score_repeatability import is_repeatable, score_repeatability, show
from steps.scoreboard import scoreboard, show_and_save
from steps.search_trends import search_trends
from viewer import build_viewer


def pipeline():
    run = Run("from-youtube")
    try:
        run.step("Which videos far outperformed their own channel?")
        #   in:  ["@Fireship", "@t3dotgg", ...]
        #   out: [{"title": "...", "channel": "...", "views": 410000, "channel_median": 11000, "multiple": 37.3}, ...]
        outliers = find_outliers(config.CHANNELS_TO_SCAN)
        run.save("find_outliers", input=config.CHANNELS_TO_SCAN, output=outliers, summary={"channels scanned": len(config.CHANNELS_TO_SCAN), "outlier videos found": len(outliers)})
        for outlier in outliers:
            print(f"  {outlier['multiple']:5.1f}x  {outlier['title']}   ({outlier['channel']})")
        if not outliers:
            raise SystemExit("No outliers found. Add channels or lower OUTLIER_MULTIPLE in config.py.")

        run.step("Which topics are those videos about?  (LLM)")
        #   in:  10 outlier videos
        #   out: [{"name": "Claude Code", "search_query": "claude code", "video_ids": ["abc", "def"]}, ...]
        topics = outliers_to_topics(outliers)
        run.save("outliers_to_topics", input=outliers, output=topics, summary={"outlier videos in": len(outliers), "topics out": len(topics)})

        run.step("What do viewers really type to find them?  (YouTube autocomplete + LLM)")
        #   in:  [{"name": "Claude Code", "search_query": "claude code"}, ...]
        #   out: [{"search_query": "claude code", "topic": "Claude Code"}, {"search_query": "claude code tutorial", "topic": "Claude Code"}, ...]
        queries = query_variants(topics)
        run.save("query_variants", input=topics, output=queries, summary={"topics in": len(topics), "search queries out": len(queries)})

        run.step("Is each search query repeatable on YouTube?")
        #   in:  the search queries                                                  one YouTube search each
        #   out: [{"search_query": "claude code", "score": 3.45, "hit_channels": 13, "hits": [22 videos]}, ...]
        scored = score_repeatability(queries)
        run.save("score_repeatability", input=queries, output=scored, summary={"YouTube searches": len(scored), "hit videos found": sum(len(idea["hits"]) for idea in scored), "repeatable": sum(map(is_repeatable, scored))})
        show(scored)
        if not google_ads.is_set_up():
            raise SystemExit("\nGoogle Ads is not set up yet (see the README), so the run stops here: this is the YouTube half of the answer.")

        run.step("How would people google each topic?  (LLM)")
        #   in:  [{"name": "AI agent course", "phrasings": ["build and sell ai agent 6 hours course", ...]}, ...]
        #   out: [{..., "seeds": ["ai agent course", "build ai agents", "ai agent tutorial"]}, ...]
        phrased = with_phrasings(topics, scored)
        topics = google_seeds(phrased)
        run.save("google_seeds", input=phrased, output=topics, summary={"topics in": len(phrased), "seed keywords out": sum(len(topic["seeds"]) for topic in topics)})

        run.step("What do people search for on Google around each topic?")
        #   in:  each topic's 3 seeds                     one request per topic: in a shared one, a big topic crowds out the rest
        #   out: {"AI agent course": [the 40 biggest keywords Google suggests, with 48 months of searches and a trend], ...}
        candidates, suggested_in_all = {}, 0
        for topic in topics:
            suggested = search_trends(keyword_ideas(topic["seeds"]))
            suggested_in_all += len(suggested)
            candidates[topic["name"]] = biggest_candidates(suggested)
            print(f"  {topic['name']}: {', '.join(topic['seeds'])}  ->  {len(suggested)} keywords, the {len(candidates[topic['name']])} biggest go on")
        kept = sum(len(rows) for rows in candidates.values())
        run.save("keyword_ideas_per_topic", input=[{"name": topic["name"], "seeds": topic["seeds"]} for topic in topics], output=candidates, summary={"topics": len(topics), "keywords Google suggested": suggested_in_all, "kept, the biggest per topic": kept})

        run.step("Which of those keywords are really about the topic?  (LLM)")
        #   in:  each topic with its candidates
        #   out: [{"name": "AI agent course", "keywords": ["ai agent course", "ai agents course"], ...}, ...]
        topics = pick_topic_keywords(topics, candidates)
        run.save("pick_topic_keywords", input=[{"name": topic["name"], "candidates": topic["candidates"]} for topic in topics], output=topics, summary={"candidate keywords in": kept, "keywords picked": sum(len(topic["keywords"]) for topic in topics)})

        run.step("SCOREBOARD: which topics are repeatable AND rising?")
        #   in:  the topics, their Google keywords, their YouTube scores
        #   out: one row per topic, with a verdict
        keywords = list({row["keyword"]: row for rows in candidates.values() for row in rows}.values())  # a keyword suggested for two topics is one keyword
        rows = scoreboard(topics, keywords, scored)
        run.save("scoreboard", input={"topics": topics, "scored": scored}, output=rows, summary={"topics": len(rows)} | tally(rows, "verdict"))
        show_and_save(rows, run.folder)
    finally:
        build_viewer.build(open_run=run.id)  # also after a failed run: the viewer shows how far it got


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find the topics that are repeatable on YouTube, then check they are rising in Google search.")
    parser.add_argument("--refresh", action="store_true", help="ignore cached YouTube and LLM responses and pull the latest data")
    args = parser.parse_args()
    cache.refresh = args.refresh
    pipeline()
