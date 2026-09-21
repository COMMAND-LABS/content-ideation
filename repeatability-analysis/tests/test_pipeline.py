"""Offline tests: YouTube is replaced by an in-memory fake."""

import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import cache
import checkpoints
import config
import final_output
import keyword_topics
import llm
import main
import stats
import youtube
from step1_outliers import find_outliers
from step2_topics import Topic
from step3_repeatability import find_hits, first_distinct, hit_overlap, score_topics, top_ideas
from youtube import Video


def make_video(id, channel_id, views, duration_seconds=600, age_days=0):
    published_at = datetime.now(timezone.utc) - timedelta(days=age_days)
    return Video(id, f"title {id}", channel_id, f"channel {channel_id}", views, duration_seconds, published_at)


def make_channel(channel_id, outlier_views=None):
    """19 uploads at 100 views, plus one outlier if requested."""
    uploads = [make_video(f"{channel_id}-{n}", channel_id, 100) for n in range(19)]
    if outlier_views:
        uploads.insert(0, make_video(f"{channel_id}-hit", channel_id, outlier_views))
    return uploads


@pytest.fixture
def fake_youtube(monkeypatch):
    channels = {name: make_channel(name, views) for name, views in [("UCa", 1000), ("UCb", 500), ("UCc", 400), ("UCme", 900), ("UCflat", None)]}
    monkeypatch.setattr(youtube, "resolve_channel_id", lambda channel: channel)
    monkeypatch.setattr(youtube, "recent_uploads", lambda channel_id: tuple(channels[channel_id]))
    monkeypatch.setattr(youtube, "autocomplete", lambda query: [])
    monkeypatch.setattr(youtube, "search", lambda query: [uploads[0] for uploads in channels.values()])
    monkeypatch.setattr(config, "FORMAT", "longform")
    monkeypatch.setattr(config, "MIN_HIT_VIEWS", 0)
    monkeypatch.setattr(config, "MIN_SCORE", 0)


def test_parse_duration():
    assert youtube.parse_duration("PT45S") == 45
    assert youtube.parse_duration("PT1H2M3S") == 3723
    assert youtube.parse_duration("P1DT1S") == 86401
    assert youtube.parse_duration("P0D") == 0


def test_subscriber_counts_skips_hidden(monkeypatch):
    items = [
        {"id": "UCa", "statistics": {"subscriberCount": "1200", "hiddenSubscriberCount": False}},
        {"id": "UCb", "statistics": {"hiddenSubscriberCount": True}},
    ]
    monkeypatch.setattr(youtube, "_get", lambda endpoint, **params: {"items": items})
    assert youtube.subscriber_counts({"UCa", "UCb"}) == {"UCa": 1200}


def test_matches_format(monkeypatch):
    short, long = make_video("s", "UCa", 1, duration_seconds=59), make_video("l", "UCa", 1, duration_seconds=61)
    monkeypatch.setattr(config, "FORMAT", "shorts")
    assert stats.matches_format(short) and not stats.matches_format(long)
    monkeypatch.setattr(config, "FORMAT", "longform")
    assert stats.matches_format(long) and not stats.matches_format(short)


def test_hit_weight():
    assert stats.hit_weight(1000, 1000, age_days=0) == 1.0  # same size, brand new
    assert stats.hit_weight(1000, 1000, age_days=180) == 0.5  # one half-life old
    assert stats.hit_weight(10_000, 1000, age_days=0) == 0.5  # 10x bigger channel
    assert stats.hit_weight(100, 1000, age_days=0) == 0.5  # 10x smaller channel


def test_first_distinct():
    assert first_distinct(["a", "b", "a", "c"], 2) == {"a", "b"}


def test_find_outliers_sorts_and_limits(fake_youtube, monkeypatch):
    monkeypatch.setattr(config, "TOP_CANDIDATES", 2)
    candidates = find_outliers(["UCa", "UCb", "UCc", "UCflat"])
    assert [(c.video.id, c.channel_median, c.multiple) for c in candidates] == [("UCa-hit", 100, 10.0), ("UCb-hit", 100, 5.0)]


def test_score_topics_excludes_my_channel_and_scores_hits(fake_youtube):
    topic = Topic(name="topic", search_query="query", video_ids=[])
    [idea] = score_topics([topic], my_channel_id="UCme", my_median=100)
    assert sorted(hit.video.id for hit in idea.hits) == ["UCa-hit", "UCb-hit", "UCc-hit"]
    assert idea.score == 3.0  # three same-size, brand-new hits


def test_top_ideas_drops_topics_with_too_few_hits(fake_youtube, monkeypatch):
    topic = Topic(name="topic", search_query="query", video_ids=[])
    scored = score_topics([topic], my_channel_id="UCme", my_median=100)
    monkeypatch.setattr(config, "MIN_HITS", 3)
    assert top_ideas(scored) == scored
    monkeypatch.setattr(config, "MIN_HITS", 4)
    assert top_ideas(scored) == []


def test_find_hits_skips_videos_too_old_or_too_little_watched(fake_youtube, monkeypatch):
    results = youtube.search("query")
    too_old = replace(results[0], published_at=results[0].published_at - timedelta(days=config.MAX_HIT_AGE_DAYS + 1))
    monkeypatch.setattr(youtube, "search", lambda query: [too_old] + results[1:])
    monkeypatch.setattr(config, "MIN_HIT_VIEWS", 450)
    hits = find_hits("query", my_channel_id="UCme", my_median=100)
    assert [hit.video.id for hit in hits] == ["UCb-hit"]  # UCa-hit is too old, UCc-hit has only 400 views


def test_top_ideas_needs_enough_channels_and_score(fake_youtube, monkeypatch):
    topic = Topic(name="topic", search_query="query", video_ids=[])
    [idea] = score_topics([topic], my_channel_id="UCme", my_median=100)
    monkeypatch.setattr(config, "MIN_HITS", 3)
    assert top_ideas([idea]) == [idea]

    one_channel = replace(idea, hits=[replace(idea.hits[0], video=replace(idea.hits[0].video, id=str(n))) for n in range(3)])
    assert (len(one_channel.hits), one_channel.hit_channels) == (3, 1)
    assert top_ideas([one_channel]) == []  # three hits, but all from the same channel

    monkeypatch.setattr(config, "MIN_SCORE", 3.5)
    assert top_ideas([idea]) == []  # enough channels, but the score is only 3.0


def test_autocomplete_variants_are_scored_and_repeats_dropped(fake_youtube, monkeypatch):
    monkeypatch.setattr(youtube, "autocomplete", lambda query: ["Query", "query for beginners", "query free", "query 2026"])
    monkeypatch.setattr(llm, "ask", lambda prompt, schema: schema(queries=["query free", "made up", "query for beginners", "query 2026"]))
    monkeypatch.setattr(config, "QUERY_VARIANTS", 2)
    monkeypatch.setattr(config, "MIN_HITS", 3)
    topic = Topic(name="topic", search_query="query", video_ids=[])
    scored = score_topics([topic], my_channel_id="UCme", my_median=100)
    assert [idea.search_query for idea in scored] == ["query", "query free", "query for beginners"]  # LLM picks only: real suggestions, capped
    assert top_ideas(scored) == scored[:1]  # the fake search returns the same hits for every query


def test_read_queries_scores_each_line_as_written(fake_youtube, monkeypatch, tmp_path):
    monkeypatch.setattr(youtube, "autocomplete", lambda query: ["ai agents for beginners"])
    monkeypatch.setattr(config, "QUERY_VARIANTS", 3)
    queries_file = tmp_path / "queries.txt"
    queries_file.write_text("ai agents\n\n  claude code  \nai agents\n")
    topics = main.read_queries(str(queries_file))
    assert [topic.search_query for topic in topics] == ["ai agents", "claude code"]  # blanks and repeats dropped
    scored = score_topics(topics, my_channel_id="UCme", my_median=100)
    assert {idea.search_query for idea in scored} == {"ai agents", "claude code"}  # no autocomplete variants added


def test_top_ideas_keeps_ideas_with_different_hits(fake_youtube, monkeypatch):
    monkeypatch.setattr(config, "MIN_HITS", 1)
    topic = Topic(name="topic", search_query="query", video_ids=[])
    [idea] = score_topics([topic], my_channel_id="UCme", my_median=100)
    first, second = replace(idea, hits=idea.hits[:2]), replace(idea, hits=idea.hits[1:])
    assert hit_overlap(second, first) == 0.5
    assert top_ideas([first, second]) == [first, second]  # half shared is still within MAX_HIT_OVERLAP
    monkeypatch.setattr(config, "MAX_HIT_OVERLAP", 0.4)
    assert top_ideas([first, second]) == [first]


def test_cache_reuses_until_expired_or_refreshed(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path))
    calls = []

    def fetch():
        calls.append(1)
        return {"call": len(calls)}

    assert cache.get_or_fetch({"q": "a"}, fetch) == {"call": 1}
    assert cache.get_or_fetch({"q": "a"}, fetch) == {"call": 1}  # served from cache
    assert cache.get_or_fetch({"q": "b"}, fetch) == {"call": 2}  # different key

    monkeypatch.setattr(cache, "refresh", True)
    assert cache.get_or_fetch({"q": "a"}, fetch) == {"call": 3}  # --refresh bypasses the cache...
    monkeypatch.setattr(cache, "refresh", False)
    assert cache.get_or_fetch({"q": "a"}, fetch) == {"call": 3}  # ...and re-caches the latest

    monkeypatch.setattr(config, "CACHE_HOURS", 0)
    assert cache.get_or_fetch({"q": "a"}, fetch) == {"call": 4}  # expired


def test_checkpoint_roundtrip(fake_youtube, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CHECKPOINT_DIR", str(tmp_path))
    run_id = checkpoints.new_run_id()
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{4}", run_id)

    topic = Topic(name="topic", search_query="query", video_ids=[])
    path = checkpoints.save(run_id, 3, score_topics([topic], my_channel_id="UCme", my_median=100))
    assert path.name == f"{run_id}_step_3.json"
    [idea] = json.loads(path.read_text())
    assert idea["topic"]["search_query"] == "query" and idea["score"] == 3.0 and len(idea["hits"]) == 3


def test_final_output_is_saved_as_json(fake_youtube, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(config, "MIN_HITS", 3)
    topic = Topic(name="topic", search_query="query", video_ids=[])
    scored = score_topics([topic], my_channel_id="UCme", my_median=100)

    path = final_output.save("20260920-143022-a3f9", 100, scored, top_ideas(scored), subscribers={"UCa": 1200})
    assert path.name == "final_output_20260920-143022-a3f9.json"
    results = json.loads(path.read_text())
    assert results["run_id"] == "20260920-143022-a3f9" and results["queries_scored"][0]["in_top_ideas"]

    [idea] = results["ideas"]
    assert (idea["rank"], idea["search_query"], idea["score"], idea["hit_channels"]) == (1, "query", 3.0, 3)
    best = idea["hits"][0]
    assert (best["label"], best["multiple"], best["url"]) == ("1.1", 10.0, "https://www.youtube.com/watch?v=UCa-hit")
    assert best["channel_subscribers"] == 1200 and idea["hits"][1]["channel_subscribers"] is None


def make_keyword(keyword, monthly_searches, history=None):
    return {"keyword": keyword, "monthly_searches": monthly_searches, "history": history or f"2026-08:{monthly_searches} {keyword}"}


def test_find_topics_keeps_variants_together_and_drops_invented_keywords(monkeypatch):
    keywords = [make_keyword("ai agents", 500, "same"), make_keyword("ai agency", 500, "same"), make_keyword("claude code", 900)]
    answer = keyword_topics.KeywordTopics(topics=[
        keyword_topics.KeywordTopic(name="AI agents", search_query="ai agents", keywords=["ai agents", "made up"], skip=""),
        keyword_topics.KeywordTopic(name="Claude Code", search_query="claude code", keywords=["claude code", "ai agents"], skip=""),
        keyword_topics.KeywordTopic(name="Nothing", search_query="nothing", keywords=["also made up"], skip=""),
    ])  # fmt: skip
    prompts = []
    monkeypatch.setattr(llm, "ask", lambda prompt, schema: prompts.append(prompt) or answer)

    topics = keyword_topics.find_topics(keywords, about="ai agents")

    assert "- ai agents | 500 a month | also searched as: ai agency" in prompts[0]  # the LLM sees one line per variant group
    assert [(topic.name, topic.keywords) for topic in topics] == [("AI agents", ["ai agents", "ai agency"]), ("Claude Code", ["claude code"])]


def test_pick_keywords_judges_each_topic_on_its_own_candidates(monkeypatch):
    given = [
        {"name": "PDF to text", "search_query": "convert pdf to text", "phrasings": ["convert scanned pdf to text"], "candidates": [make_keyword("ocr pdf", 300), make_keyword("edit pdf", 9000)]},
        {"name": "Unknown to Google", "search_query": "gpt-6 vs fable", "candidates": []},
    ]  # fmt: skip
    prompts = []
    monkeypatch.setattr(llm, "ask", lambda prompt, schema: prompts.append(prompt) or keyword_topics.Picks(keywords=["ocr pdf"]))

    topics = keyword_topics.pick_keywords(given)

    assert len(prompts) == 1 and "- convert scanned pdf to text" in prompts[0]  # a topic without candidates costs no LLM call
    assert [(topic.name, topic.keywords) for topic in topics] == [("PDF to text", ["ocr pdf"]), ("Unknown to Google", [])]


def test_google_seeds_fall_back_to_the_search_query(monkeypatch):
    given = [{"name": "A", "search_query": "query a", "phrasings": ["long phrasing a"]}, {"name": "B", "search_query": "query b", "phrasings": ["long phrasing b"]}]
    answer = keyword_topics.Seeds(topics=[keyword_topics.TopicSeeds(topic_number=1, seeds=["one", "two", "three", "four"])])
    monkeypatch.setattr(llm, "ask", lambda prompt, schema: answer)

    seeded = keyword_topics.google_seeds(given)

    assert [topic["seeds"] for topic in seeded] == [["one", "two", "three"], ["query b"]]
