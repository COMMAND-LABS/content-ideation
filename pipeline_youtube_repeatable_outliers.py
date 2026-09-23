"""PIPELINE 1: YouTube repeatable outliers.
What is working for the channels in your niche (CHANNELS_TO_SCAN in config.py), and does it work for many channels?

    uv run pipeline_1_youtube_repeatable_outliers.py

    channels -> outliers -> topics -> YouTube suggestions -> search queries -> repeatability -> SCOREBOARD

Needs only a YouTube API key and an LLM key. Pipeline 3 is this pipeline plus a Google search check.
Every step is one small module in steps/, and every step saves its input and its output in
runs/<run id>/, so you can follow a run file by file (or step by step in the viewer).
"""

import argparse

from shared import cache
from shared.run import Run, tally
from shared.settings import config
from steps.find_outliers import find_outliers
from steps.outliers_to_topics import outliers_to_topics
from steps.query_variants import query_variants
from steps.score_repeatability import is_repeatable, score_repeatability, show
from steps.scoreboard import scoreboard, show_and_save
from steps.youtube_suggestions import youtube_suggestions
from viewer import build_viewer


def pipeline():
    run = Run("youtube-repeatable-outliers")
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

        run.step("What do viewers really type to find them?  (a: YouTube autocomplete, b: LLM)")
        #   a. in:  [{"name": "Claude Code", "search_query": "claude code"}, ...]                     one free autocomplete call per topic
        #      out: [{"name": "Claude Code", "search_query": "claude code", "suggestions": ["claude code tutorial", "claude code vs cursor", ...]}, ...]
        suggested = youtube_suggestions(topics)
        suggestions = sum(len(topic["suggestions"]) for topic in suggested)
        run.save("youtube_suggestions", part="a", input=topics, output=suggested, summary={"search queries in": len(topics), "suggestions out": suggestions})

        #   b. in:  the topics with their suggestions                                                 the LLM picks up to QUERY_VARIANTS per topic
        #      out: [{"search_query": "claude code", "topic": "Claude Code"}, {"search_query": "claude code tutorial", "topic": "Claude Code"}, ...]
        queries = query_variants(suggested)
        run.save("query_variants", part="b", input=suggested, output=queries, summary={"topics in": len(suggested), "suggestions in": suggestions, "search queries out": len(queries)})

        run.step("Is each search query repeatable on YouTube?")
        #   in:  the search queries                                                  one YouTube search each
        #   out: [{"search_query": "claude code", "score": 3.45, "hit_channels": 13, "hits": [22 videos]}, ...]
        scored = score_repeatability(queries)
        run.save("score_repeatability", input=queries, output=scored, summary={"YouTube searches": len(scored), "hit videos found": sum(len(idea["hits"]) for idea in scored), "repeatable": sum(map(is_repeatable, scored))})
        show(scored)


        run.step("SCOREBOARD: which topics are repeatable?")
        #   in:  the topics and their YouTube scores
        #   out: one row per topic, with a verdict: "repeatable" or "not repeatable"
        rows = scoreboard(topics, None, scored)
        run.save("scoreboard", input={"topics": topics, "scored": scored}, output=rows, summary={"topics": len(rows)} | tally(rows, "verdict"))
        show_and_save(rows, run.folder)
    finally:
        build_viewer.build(open_run=run.id)  # also after a failed run: the viewer shows how far it got


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find the topics that are repeatable on YouTube for the channels in your niche.")
    parser.add_argument("--refresh", action="store_true", help="ignore cached YouTube and LLM responses and pull the latest data")
    args = parser.parse_args()
    cache.refresh = args.refresh
    pipeline()
