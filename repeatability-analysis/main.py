"""Runs the full pipeline: outliers -> topics -> repeatability -> top ideas.

Usage: python main.py [--refresh] [--queries FILE] [--run-id ID]

With --queries, steps 1 and 2 are skipped: the search queries in the file (one per line) are scored as given.
With --run-id, the checkpoints and results are saved under that ID (../ideate.py gives both tools its own).
"""

import argparse
from pathlib import Path

import cache
import checkpoints
import config
import final_output
import stats
import youtube
from step1_outliers import find_outliers
from step2_topics import Topic, dedupe_topics
from step3_repeatability import Idea, score_topics, top_ideas


def main(queries_file: str | None = None, run_id: str | None = None):
    run_id = run_id or checkpoints.new_run_id()
    print(f"Run {run_id} (checkpoints in {config.CHECKPOINT_DIR}/)\n")

    my_channel_id = youtube.resolve_channel_id(config.MY_CHANNEL)
    my_median = stats.channel_median(my_channel_id)
    if my_median == 0:
        raise SystemExit(f"{config.MY_CHANNEL} has no {config.FORMAT} uploads with views to compare against.")
    print(f"Your median views ({config.FORMAT}): {my_median:,.0f}\n")

    topics = read_queries(queries_file) if queries_file else find_topics(run_id)

    print("\nSTEP 3: scoring repeatability...")
    scored = score_topics(topics, my_channel_id, my_median)
    checkpoints.save(run_id, 3, scored)
    for idea in scored:
        print(f'  {idea.score:5.2f}  {len(idea.hits):2d} hits, {idea.hit_channels:2d} channels  "{idea.search_query}"  ({idea.topic.name})')
    ideas = top_ideas(scored)
    if not ideas:
        print(f"\nNo search query had hits on {config.MIN_HITS}+ channels and a score of {config.MIN_SCORE}+.")

    subscribers = youtube.subscriber_counts({hit.video.channel_id for idea in ideas for hit in idea.hits})
    print(f"\nTOP {len(ideas)} IDEAS")
    for rank, idea in enumerate(ideas, start=1):
        print_idea(rank, idea, subscribers)

    results_path = final_output.save(run_id, my_median, scored, ideas, subscribers)
    print(f"\nResults saved to {results_path}")
    print("View them: run `python3 run_viewer.py` in the parent folder and open its index.html")


def find_topics(run_id: str) -> list[Topic]:
    """Steps 1 and 2: the topics behind the scanned channels' outlier videos."""
    print(f"STEP 1: scanning {len(config.CHANNELS_TO_SCAN)} channels for outliers...")
    candidates = find_outliers(config.CHANNELS_TO_SCAN)
    checkpoints.save(run_id, 1, candidates)
    for candidate in candidates:
        print(f"  {candidate.multiple:5.1f}x  {candidate.video.title}")
        print(f"          {candidate.video.channel_title}, median {candidate.channel_median:,.0f} views")
    if not candidates:
        raise SystemExit("No outliers found. Add channels or lower OUTLIER_MULTIPLE in ../config.py.")

    print("\nSTEP 2: deduping topics...")
    topics = dedupe_topics(candidates)
    checkpoints.save(run_id, 2, topics)
    for topic in topics:
        print(f'  {topic.name}  ->  "{topic.search_query}"')
    return topics


def read_queries(queries_file: str) -> list[Topic]:
    """One search query per line, each scored exactly as written (no autocomplete variants)."""
    config.QUERY_VARIANTS = 0
    lines = [line.strip() for line in Path(queries_file).read_text().splitlines()]
    queries = list(dict.fromkeys(line for line in lines if line))
    print(f"STEPS 1-2 skipped: {len(queries)} search queries read from {queries_file}")
    return [Topic(name=query, search_query=query, video_ids=[]) for query in queries]


def print_idea(rank: int, idea: Idea, subscribers: dict[str, int]):
    print(f'\n{rank}. "{idea.search_query}"')
    print(f"   repeatability {idea.score:.2f}  |  {len(idea.hits)} hits from {idea.hit_channels} channels  |  topic: {idea.topic.name}")
    ranked_hits = sorted(idea.hits, key=lambda hit: hit.weight, reverse=True)
    for hit_rank, hit in enumerate(ranked_hits, start=1):
        label = f"{rank}.{hit_rank}"
        indent = " " * (len(label) + 5)  # lines up under the multiple
        multiple = hit.video.views / hit.channel_median
        subs = subscribers.get(hit.video.channel_id)
        subs_text = f"{subs:,} subscribers" if subs is not None else "subscribers hidden"
        print(f"   {label}  {multiple:.1f}x  {hit.video.title}  ({hit.video.age_days}d ago)")
        print(f"{indent}{hit.video.channel_title}, {subs_text}, median {hit.channel_median:,.0f} views")
        print(f"{indent}{hit.video.url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find repeatable content ideas.")
    parser.add_argument("--refresh", action="store_true", help="ignore cached API responses and pull the latest data")
    parser.add_argument("--queries", metavar="FILE", help="skip steps 1 and 2: score the search queries in this file (one per line)")
    parser.add_argument("--run-id", metavar="ID", help="save the checkpoints and results under this ID instead of a new one")
    args = parser.parse_args()
    cache.refresh = args.refresh
    main(args.queries, args.run_id)
