"""STEP: channels -> the videos that far outperformed their own channel's normal.

Every channel gets a baseline: the median views of its last UPLOADS_FOR_MEDIAN uploads. An upload
with OUTLIER_MULTIPLE+ times that median is an outlier. The TOP_CANDIDATES biggest go on.

    in:   ["@Fireship", "@t3dotgg", ...]
    out:  [{"title": "...", "channel": "Fireship", "views": 4100000, "channel_median": 820000, "multiple": 5.0, ...}, ...]

Try it:   uv run python -m steps.find_outliers @Fireship        (about 3 YouTube quota units)
     or:  curl "https://www.googleapis.com/youtube/v3/channels?part=id&forHandle=@Fireship&key=$YOUTUBE_API_KEY"
"""

import sys

from shared import channel_stats, youtube_api
from shared.settings import config


def find_outliers(channels: list[str]) -> list[dict]:
    outliers = []
    for channel in channels:
        channel_id = youtube_api.resolve_channel_id(channel)
        median_views = channel_stats.channel_median(channel_id)
        if median_views == 0:
            continue
        for video in channel_stats.channel_uploads(channel_id):
            multiple = video.views / median_views
            if multiple >= config.OUTLIER_MULTIPLE:
                outliers.append(video.facts() | {"channel_median": median_views, "multiple": multiple})

    outliers.sort(key=lambda outlier: outlier["multiple"], reverse=True)
    return outliers[: config.TOP_CANDIDATES]


if __name__ == "__main__":
    channels = sys.argv[1:] or ["@Fireship"]
    for channel in channels:
        channel_id = youtube_api.resolve_channel_id(channel)
        print(f"  {channel}: median {channel_stats.channel_median(channel_id):,.0f} views over its last {len(channel_stats.channel_uploads(channel_id))} {config.FORMAT} uploads")
    outliers = find_outliers(channels)
    for outlier in outliers:
        print(f"  {outlier['multiple']:5.1f}x  {outlier['title']}   ({outlier['channel']}, {outlier['views']:,} views)")
    if not outliers:
        print(f"  no upload reached {config.OUTLIER_MULTIPLE}x the median: nothing unusual happened on this channel lately")
