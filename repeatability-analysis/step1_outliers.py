"""STEP 1: find videos that far outperformed their own channel's median."""

from dataclasses import dataclass

import config
import stats
import youtube
from youtube import Video


@dataclass(frozen=True)
class Candidate:
    video: Video
    channel_median: float
    multiple: float  # views / channel median


def find_outliers(channels: list[str]) -> list[Candidate]:
    """The top outlier videos across all channels, best first."""
    outliers = []
    for channel in channels:
        channel_id = youtube.resolve_channel_id(channel)
        median_views = stats.channel_median(channel_id)
        if median_views == 0:
            continue
        for video in stats.channel_uploads(channel_id):
            multiple = video.views / median_views
            if multiple >= config.OUTLIER_MULTIPLE:
                outliers.append(Candidate(video, median_views, multiple))

    outliers.sort(key=lambda candidate: candidate.multiple, reverse=True)
    return outliers[: config.TOP_CANDIDATES]
