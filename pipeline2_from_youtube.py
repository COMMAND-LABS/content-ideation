"""PIPELINE 2: start from YouTube. What is working for the channels in your niche (CHANNELS_TO_SCAN in config.py)?

    uv run pipeline2_from_youtube.py

    channels -> outliers -> topics -> YouTube suggestions -> search queries -> repeatability -> Google seeds -> keyword ideas -> keywords about the topic -> SCOREBOARD

Every step is one small module in steps/, and every step saves its input and its output in
runs/<run id>/, so you can follow a run file by file (or step by step in the viewer).
"""

import argparse

from shared import cache, google_ads
from shared.run import Run, tally
from shared.settings import config
from steps.find_outliers import find_outliers
from steps.google_seeds import google_seeds, with_phrasings
from steps.keyword_ideas import by_seed, keyword_ideas
from steps.outliers_to_topics import outliers_to_topics
from steps.pick_topic_keywords import biggest_candidates, pick_topic_keywords
from steps.query_variants import query_variants
from steps.score_repeatability import is_repeatable, score_repeatability, show
from steps.scoreboard import scoreboard, show_and_save
from steps.search_trends import search_trends
from steps.youtube_suggestions import youtube_suggestions
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
        if not google_ads.is_set_up():
            raise SystemExit("\nGoogle Ads is not set up yet (see the README), so the run stops here: this is the YouTube half of the answer.")

        run.step("How would people google each topic?  (a: the phrasings from YouTube, b: LLM)")
        #   a. in:  the topics, and the search queries scored in step 4
        #      out: [{"name": "AI agent course", "search_query": "build ai agents", "phrasings": ["build and sell ai agent 6 hours course", ...]}, ...]
        phrased = with_phrasings(topics, scored)
        phrasings = sum(len(topic["phrasings"]) for topic in phrased)
        run.save("topic_phrasings", part="a", input={"topics": topics, "scored": scored}, output=phrased, summary={"topics in": len(topics), "YouTube phrasings out": phrasings})

        #   b. in:  the topics with their phrasings                                                   the LLM writes 3 short Google keywords per topic
        #      out: [{..., "seeds": ["ai agent course", "build ai agents", "ai agent tutorial"]}, ...]
        topics = google_seeds(phrased)
        run.save("google_seeds", part="b", input=phrased, output=topics, summary={"topics in": len(phrased), "YouTube phrasings in": phrasings, "seed keywords out": sum(len(topic["seeds"]) for topic in topics)})

        run.step("What do people search for on Google around each topic?  (a: Google, b: keep the biggest)")
        #   a. in:  each topic's 3 seeds                     one request per topic: in a shared one, a big topic crowds out the rest
        #      out: {"AI agent course": {"ai agent course": {"ai agent course": 2400, ...}, "build ai agents": {...}, "related": {...}}, ...}
        #   b. in:  everything Google suggested, with 48 months of searches
        #      out: {"AI agent course": [the 40 biggest keywords, each with its trend], ...}
        suggested, candidates, suggested_in_all = {}, {}, 0
        for topic in topics:
            ideas = keyword_ideas(topic["seeds"])
            suggested[topic["name"]] = by_seed(topic["seeds"], ideas)["keywords"]
            candidates[topic["name"]] = biggest_candidates(search_trends(ideas))
            suggested_in_all += len(ideas)
            print(f"  {topic['name']}: {', '.join(topic['seeds'])}  ->  {len(ideas)} keywords, the {len(candidates[topic['name']])} biggest go on")
        seeds = [{"name": topic["name"], "seeds": topic["seeds"]} for topic in topics]
        kept = sum(len(rows) for rows in candidates.values())
        run.save("keywords_suggested", part="a", input=seeds, output=suggested, summary={"topics": len(topics), "seed keywords in": sum(len(topic["seeds"]) for topic in topics), "keywords Google suggested": suggested_in_all})
        run.save("keyword_ideas_per_topic", part="b", input={name: f"{sum(map(len, by.values()))} keywords, listed in 06_a_keywords_suggested.json" for name, by in suggested.items()}, output=candidates, summary={"keywords in": suggested_in_all, "kept, the biggest per topic": kept})

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
