"""The math shared by the pipeline steps: format filter, channel medians, hit weights."""

import math
from statistics import median

import config
import youtube
from youtube import Video


def matches_format(video: Video) -> bool:
    is_short = 0 < video.duration_seconds <= config.SHORTS_MAX_SECONDS
    is_longform = video.duration_seconds > config.SHORTS_MAX_SECONDS
    return is_short if config.FORMAT == "shorts" else is_longform


def channel_uploads(channel_id: str) -> list[Video]:
    """The channel's last N uploads in the configured format."""
    uploads = [video for video in youtube.recent_uploads(channel_id) if matches_format(video)]
    return uploads[: config.UPLOADS_FOR_MEDIAN]


def channel_median(channel_id: str) -> float:
    """Median views over the channel's last N uploads in the configured format (0 if none)."""
    uploads = channel_uploads(channel_id)
    return median(video.views for video in uploads) if uploads else 0


def hit_weight(channel_median_views: float, my_median_views: float, age_days: int) -> float:
    """Hits from channels near my size, and recent hits, weigh the most."""
    size_gap = abs(math.log10(channel_median_views) - math.log10(my_median_views))
    recency = 0.5 ** (age_days / config.AGE_HALF_LIFE_DAYS)
    return recency / (1 + size_gap)
