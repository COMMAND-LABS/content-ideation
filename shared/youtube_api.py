"""Thin wrapper around the YouTube Data API v3. All YouTube network calls live here."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

import requests

from shared import cache
from shared.settings import api_key, config

API_URL = "https://www.googleapis.com/youtube/v3"
AUTOCOMPLETE_URL = "https://suggestqueries.google.com/complete/search"  # unofficial: no key, no quota
MAX_PAGE_SIZE = 50  # API limit for a single request

DURATION_PATTERN = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


@dataclass(frozen=True)
class Video:
    id: str
    title: str
    channel_id: str
    channel_title: str
    views: int
    duration_seconds: int
    published_at: datetime
    description: str = ""

    @property
    def age_days(self) -> int:
        return (datetime.now(timezone.utc) - self.published_at).days

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"

    def facts(self) -> dict:
        """The video as plain data, the way the steps hand it on."""
        return {
            "video_id": self.id,
            "title": self.title,
            "url": self.url,
            "channel_id": self.channel_id,
            "channel": self.channel_title,
            "views": self.views,
            "published_at": self.published_at.isoformat(),
            "age_days": self.age_days,
        }


class YouTubeError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"YouTube API error {status}: {message}")
        self.status = status


def resolve_channel_id(handle_or_id: str) -> str:
    """Accepts "@handle" or a "UC..." channel ID and returns the channel ID."""
    if not handle_or_id.startswith("@"):
        return handle_or_id
    items = _get("channels", part="id", forHandle=handle_or_id).get("items", [])
    if not items:
        raise ValueError(f"No YouTube channel found for {handle_or_id}")
    return items[0]["id"]


@lru_cache(maxsize=None)
def recent_uploads(channel_id: str) -> tuple[Video, ...]:
    """The channel's most recent uploads (up to 50), newest first."""
    uploads_playlist = "UU" + channel_id[2:]  # every channel's uploads playlist follows this pattern
    try:
        page = _get("playlistItems", part="contentDetails", playlistId=uploads_playlist, maxResults=MAX_PAGE_SIZE)
    except YouTubeError as error:
        if error.status == 404:  # channel has no public uploads
            return ()
        raise
    return tuple(videos([item["contentDetails"]["videoId"] for item in page["items"]]))


def search(query: str) -> list[Video]:
    """Videos returned by a YouTube search, in ranking order. Costs 100 quota units."""
    page = _get("search", part="id", type="video", q=query, maxResults=config.SEARCH_RESULTS_PER_QUERY)
    # For a brand name ("claude ai") YouTube can slip the brand's channel in, even with type="video".
    return videos([item["id"]["videoId"] for item in page["items"] if "videoId" in item["id"]])


def autocomplete(query: str) -> list[str]:
    """What YouTube's search box suggests for the query, most popular first ([] if the endpoint is unreachable)."""
    try:
        return cache.get_or_fetch({"youtube": "autocomplete", "q": query}, lambda: _fetch_autocomplete(query))["suggestions"]
    except requests.RequestException as error:
        print(f"  (autocomplete unavailable for \"{query}\": {error})")
        return []


def videos(video_ids: list[str]) -> list[Video]:
    """Full details for the given video IDs, in the order given."""
    found = {}
    for start in range(0, len(video_ids), MAX_PAGE_SIZE):
        batch = video_ids[start : start + MAX_PAGE_SIZE]
        page = _get("videos", part="snippet,contentDetails,statistics", id=",".join(batch))
        found.update((item["id"], _to_video(item)) for item in page["items"])
    return [found[video_id] for video_id in video_ids if video_id in found]


def parse_duration(iso_duration: str) -> int:
    """ISO 8601 duration ("PT1H2M3S") to seconds."""
    days, hours, minutes, seconds = (int(part or 0) for part in DURATION_PATTERN.fullmatch(iso_duration).groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def _to_video(item: dict) -> Video:
    return Video(
        id=item["id"],
        title=item["snippet"]["title"],
        channel_id=item["snippet"]["channelId"],
        channel_title=item["snippet"]["channelTitle"],
        views=int(item["statistics"].get("viewCount", 0)),
        duration_seconds=parse_duration(item["contentDetails"].get("duration", "PT0S")),
        published_at=datetime.fromisoformat(item["snippet"]["publishedAt"]),
        description=item["snippet"].get("description", ""),
    )


def _get(endpoint: str, **params) -> dict:
    """A YouTube API response, served from the disk cache when fresh."""
    return cache.get_or_fetch({"youtube": endpoint, **params}, lambda: _fetch(endpoint, params))


def _fetch_autocomplete(query: str) -> dict:
    response = requests.get(AUTOCOMPLETE_URL, params={"client": "firefox", "ds": "yt", "hl": "en", "q": query}, timeout=30)
    response.raise_for_status()
    return {"suggestions": response.json()[1]}  # the response is [query, [suggestion, ...], ...]


def _fetch(endpoint: str, params: dict) -> dict:
    response = requests.get(f"{API_URL}/{endpoint}", params={**params, "key": api_key("YOUTUBE_API_KEY")}, timeout=30)
    if not response.ok:
        raise YouTubeError(response.status_code, response.json()["error"]["message"])
    return response.json()
