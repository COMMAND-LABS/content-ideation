"""STEP: search queries -> each query with its hits and its repeatability score.

A query is searched on YouTube. A result is a HIT when it has HIT_MULTIPLE+ times its own channel's
median views (and MIN_HIT_VIEWS+ views, and is at most MAX_HIT_AGE_DAYS old). A hit weighs more when
it is recent and when its channel is close to yours in size. The score is the sum of the weights:
1.0 is one brand-new hit from a channel exactly your size.

    in:   [{"search_query": "claude code", "topic": "Claude Code"}]
    out:  [{"search_query": "claude code", "topic": "Claude Code", "score": 3.45, "hit_channels": 13,
            "hits": [{"title": "...", "channel": "...", "views": 450000, "channel_median": 9909, "multiple": 45.4, "weight": 0.257, ...}]}]

Try it:   uv run python -m steps.score_repeatability "claude code"    (a YouTube search: 100 quota units, free when cached)
     or:  curl "https://www.googleapis.com/youtube/v3/search?part=id&type=video&maxResults=5&q=claude+code&key=$YOUTUBE_API_KEY"
"""

import sys

from shared import channel_stats, youtube_api
from shared.settings import config


def score_repeatability(queries: list[dict]) -> list[dict]:
    """Every query with its hits and score, best first."""
    my_channel_id = youtube_api.resolve_channel_id(config.MY_CHANNEL)
    my_median = channel_stats.channel_median(my_channel_id)
    if my_median == 0:
        raise SystemExit(f"{config.MY_CHANNEL} has no {config.FORMAT} uploads with views to compare against.")

    scored = []
    for query in queries:
        hits = find_hits(query["search_query"], my_channel_id, my_median)
        scored.append(query | {"score": round(sum(hit["weight"] for hit in hits), 3), "hit_channels": len({hit["channel_id"] for hit in hits}), "hits": hits})
    return sorted(scored, key=lambda idea: idea["score"], reverse=True)


def find_hits(search_query: str, my_channel_id: str, my_median: float) -> list[dict]:
    """Search results that outperformed their own channel's median, the heaviest first.

    Videos too old or too little watched for that comparison to mean anything are left out first.
    """
    results = [
        video
        for video in youtube_api.search(search_query)
        if channel_stats.matches_format(video)
        and video.channel_id != my_channel_id
        and video.age_days <= config.MAX_HIT_AGE_DAYS
        and video.views >= config.MIN_HIT_VIEWS
    ]
    channels = first_distinct([video.channel_id for video in results], config.CHANNELS_PER_QUERY)

    hits = []
    for video in results:
        if video.channel_id not in channels:
            continue
        median_views = channel_stats.channel_median(video.channel_id)
        if median_views > 0 and video.views >= config.HIT_MULTIPLE * median_views:
            weight = channel_stats.hit_weight(median_views, my_median, video.age_days)
            hits.append(video.facts() | {"channel_median": median_views, "multiple": round(video.views / median_views, 1), "weight": round(weight, 4)})
    return sorted(hits, key=lambda hit: hit["weight"], reverse=True)


def is_repeatable(idea: dict) -> bool:
    return idea["hit_channels"] >= config.MIN_HITS and idea["score"] >= config.MIN_SCORE


def first_distinct(items: list[str], limit: int) -> set[str]:
    return set(list(dict.fromkeys(items))[:limit])


def show(scored: list[dict]):
    for idea in scored:
        mark = "repeatable" if is_repeatable(idea) else "          "
        print(f'  {idea["score"]:5.2f}  {len(idea["hits"]):2d} hits on {idea["hit_channels"]:2d} channels  {mark}  "{idea["search_query"]}"')


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "claude code"
    [idea] = score_repeatability([{"search_query": query, "topic": query}])
    show([idea])
    for hit in idea["hits"][:5]:
        print(f"      weight {hit['weight']:.3f}  {hit['multiple']:5.1f}x  {hit['title'][:60]}   ({hit['channel']}, {hit['age_days']}d ago)")
