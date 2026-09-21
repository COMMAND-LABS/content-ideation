"""Writes a run's final results to <OUTPUT_DIR>/final_output_<run_id>.json."""

import json
from datetime import datetime
from pathlib import Path

import config
from step3_repeatability import Idea

SETTINGS_SHOWN = [
    "FORMAT", "UPLOADS_FOR_MEDIAN", "OUTLIER_MULTIPLE", "TOP_CANDIDATES", "LLM_PROVIDER", "QUERY_VARIANTS",
    "SEARCH_RESULTS_PER_QUERY", "CHANNELS_PER_QUERY", "HIT_MULTIPLE", "MIN_HIT_VIEWS", "MAX_HIT_AGE_DAYS",
    "AGE_HALF_LIFE_DAYS", "MIN_HITS", "MIN_SCORE", "MAX_HIT_OVERLAP", "TOP_IDEAS",
]  # fmt: skip


def save(run_id: str, my_median: float, scored: list[Idea], ideas: list[Idea], subscribers: dict[str, int]) -> Path:
    """Dump the results and return the path of the JSON file."""
    results = build(run_id, my_median, scored, ideas, subscribers)
    path = Path(config.OUTPUT_DIR) / f"final_output_{run_id}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    return path


def build(run_id: str, my_median: float, scored: list[Idea], ideas: list[Idea], subscribers: dict[str, int]) -> dict:
    return {
        "run_id": run_id,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "my_channel": config.MY_CHANNEL,
        "my_median_views": my_median,
        "channels_scanned": len(config.CHANNELS_TO_SCAN),
        "settings": {name: getattr(config, name) for name in SETTINGS_SHOWN},
        "ideas": [_idea(rank, idea, subscribers) for rank, idea in enumerate(ideas, start=1)],
        "queries_scored": [
            {
                "search_query": idea.search_query,
                "topic": idea.topic.name,
                "score": round(idea.score, 3),
                "hits": len(idea.hits),
                "hit_channels": idea.hit_channels,
                "in_top_ideas": idea in ideas,
            }
            for idea in scored
        ],
    }


def _idea(rank: int, idea: Idea, subscribers: dict[str, int]) -> dict:
    ranked_hits = sorted(idea.hits, key=lambda hit: hit.weight, reverse=True)
    return {
        "rank": rank,
        "search_query": idea.search_query,
        "topic": idea.topic.name,
        "score": round(idea.score, 3),
        "hit_channels": idea.hit_channels,
        "hits": [
            {
                "label": f"{rank}.{hit_rank}",
                "video_id": hit.video.id,
                "title": hit.video.title,
                "url": hit.video.url,
                "views": hit.video.views,
                "published_at": hit.video.published_at.isoformat(),
                "age_days": hit.video.age_days,
                "multiple": round(hit.video.views / hit.channel_median, 1),
                "weight": round(hit.weight, 4),
                "channel_id": hit.video.channel_id,
                "channel_title": hit.video.channel_title,
                "channel_median_views": hit.channel_median,
                "channel_subscribers": subscribers.get(hit.video.channel_id),  # None when the channel hides it
            }
            for hit_rank, hit in enumerate(ranked_hits, start=1)
        ],
    }
