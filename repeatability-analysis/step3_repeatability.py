"""STEP 3: score each topic by how many other channels have also had a hit with it.

Each topic is searched by its own query and by its autocomplete variants (see step 2).
Every query is scored as an idea of its own.
"""

from dataclasses import dataclass

import config
import stats
import youtube
from step2_topics import Topic, query_variants
from youtube import Video


@dataclass(frozen=True)
class Hit:
    video: Video
    channel_median: float
    weight: float


@dataclass(frozen=True)
class Idea:
    topic: Topic
    search_query: str  # the topic's own query, or an autocomplete variant of it
    hits: list[Hit]
    score: float  # repeatability: the sum of the hit weights

    @property
    def hit_channels(self) -> int:
        """How many different channels the hits come from."""
        return len({hit.video.channel_id for hit in self.hits})


def score_topics(topics: list[Topic], my_channel_id: str, my_median: float) -> list[Idea]:
    """Every query variant of every topic with its hits and repeatability score, best first."""
    ideas = []
    queries = {}  # search query -> topic; a query two topics share is only scored once
    for topic in topics:
        for search_query in query_variants(topic):
            queries.setdefault(search_query, topic)

    for search_query, topic in queries.items():
        hits = find_hits(search_query, my_channel_id, my_median)
        ideas.append(Idea(topic, search_query, hits, score=sum(hit.weight for hit in hits)))
    return sorted(ideas, key=lambda idea: idea.score, reverse=True)


def top_ideas(ideas: list[Idea]) -> list[Idea]:
    """The best ideas to present, skipping unrepeatable ones (too few channels or too low a score) and repeats of a better idea."""
    chosen = []
    for idea in ideas:
        is_repeatable = idea.hit_channels >= config.MIN_HITS and idea.score >= config.MIN_SCORE
        is_repeat = any(hit_overlap(idea, better) > config.MAX_HIT_OVERLAP for better in chosen)
        if is_repeatable and not is_repeat:
            chosen.append(idea)
    return chosen[: config.TOP_IDEAS]


def hit_overlap(idea: Idea, other: Idea) -> float:
    """The share of the idea's hits that are also hits of the other idea."""
    other_ids = {hit.video.id for hit in other.hits}
    return sum(hit.video.id in other_ids for hit in idea.hits) / len(idea.hits) if idea.hits else 0.0


def find_hits(search_query: str, my_channel_id: str, my_median: float) -> list[Hit]:
    """Search results that outperformed their own channel's median.

    Videos too old or too little watched for that comparison to mean anything are left out first.
    """
    results = [
        video
        for video in youtube.search(search_query)
        if stats.matches_format(video)
        and video.channel_id != my_channel_id
        and video.age_days <= config.MAX_HIT_AGE_DAYS
        and video.views >= config.MIN_HIT_VIEWS
    ]
    channels = first_distinct([video.channel_id for video in results], config.CHANNELS_PER_QUERY)

    hits = []
    for video in results:
        if video.channel_id not in channels:
            continue
        median_views = stats.channel_median(video.channel_id)
        if median_views > 0 and video.views >= config.HIT_MULTIPLE * median_views:
            weight = stats.hit_weight(median_views, my_median, video.age_days)
            hits.append(Hit(video, median_views, weight))
    return hits


def first_distinct(items: list[str], limit: int) -> set[str]:
    return set(list(dict.fromkeys(items))[:limit])
