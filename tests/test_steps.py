"""Offline tests: YouTube and the LLM are replaced by in-memory fakes. No API keys needed (config.py has to exist)."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from shared import cache, channel_stats, llm, settings, youtube_api
from shared.run import Run, sample, tally
from shared.settings import config
from shared.youtube_api import Video
from steps import group_into_topics as grouping
from steps import pick_topic_keywords as picking
from steps.choose_topics import choose_topics
from steps.find_outliers import find_outliers
from steps.google_seeds import Seeds, TopicSeeds, google_seeds, with_phrasings
from steps.keyword_ideas import by_seed
from steps.query_variants import query_variants
from steps.rising_keywords import rising_keywords
from steps.score_repeatability import find_hits, first_distinct, is_repeatable, score_repeatability
from steps.scoreboard import scoreboard
from steps.search_trends import measure, search_trends
from steps.youtube_suggestions import youtube_suggestions


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
    monkeypatch.setattr(youtube_api, "resolve_channel_id", lambda channel: channel)
    monkeypatch.setattr(youtube_api, "recent_uploads", lambda channel_id: tuple(channels[channel_id]))
    monkeypatch.setattr(youtube_api, "autocomplete", lambda query: [])
    monkeypatch.setattr(youtube_api, "search", lambda query: [uploads[0] for uploads in channels.values()])
    monkeypatch.setattr(config, "MY_CHANNEL", "UCme")
    monkeypatch.setattr(config, "FORMAT", "longform")
    monkeypatch.setattr(config, "MIN_HIT_VIEWS", 0)
    monkeypatch.setattr(config, "MIN_SCORE", 0)


def make_keyword(keyword, searches, history=None, **trend):
    return {"keyword": keyword, "avg_monthly_searches": searches, "monthly_searches": history or {"2026-08": searches, "note": keyword}} | trend


# --- The YouTube side ---


def test_parse_duration():
    assert youtube_api.parse_duration("PT45S") == 45
    assert youtube_api.parse_duration("PT1H2M3S") == 3723
    assert youtube_api.parse_duration("P1DT1S") == 86401
    assert youtube_api.parse_duration("P0D") == 0


def test_matches_format(monkeypatch):
    short, long = make_video("s", "UCa", 1, duration_seconds=59), make_video("l", "UCa", 1, duration_seconds=61)
    monkeypatch.setattr(config, "FORMAT", "shorts")
    assert channel_stats.matches_format(short) and not channel_stats.matches_format(long)
    monkeypatch.setattr(config, "FORMAT", "longform")
    assert channel_stats.matches_format(long) and not channel_stats.matches_format(short)


def test_hit_weight(monkeypatch):
    monkeypatch.setattr(config, "AGE_HALF_LIFE_DAYS", 180)
    assert channel_stats.hit_weight(1000, 1000, age_days=0) == 1.0  # same size, brand new
    assert channel_stats.hit_weight(1000, 1000, age_days=180) == 0.5  # one half-life old
    assert channel_stats.hit_weight(10_000, 1000, age_days=0) == 0.5  # 10x bigger channel
    assert channel_stats.hit_weight(100, 1000, age_days=0) == 0.5  # 10x smaller channel


def test_first_distinct():
    assert first_distinct(["a", "b", "a", "c"], 2) == {"a", "b"}


def test_find_outliers_sorts_and_limits(fake_youtube, monkeypatch):
    monkeypatch.setattr(config, "OUTLIER_MULTIPLE", 5.0)
    monkeypatch.setattr(config, "TOP_CANDIDATES", 2)
    outliers = find_outliers(["UCa", "UCb", "UCc", "UCflat"])
    assert [(o["video_id"], o["channel_median"], o["multiple"]) for o in outliers] == [("UCa-hit", 100, 10.0), ("UCb-hit", 100, 5.0)]


def test_score_repeatability_excludes_my_channel_and_scores_hits(fake_youtube, monkeypatch):
    monkeypatch.setattr(config, "HIT_MULTIPLE", 4.0)
    [idea] = score_repeatability([{"search_query": "query", "topic": "topic"}])
    assert sorted(hit["video_id"] for hit in idea["hits"]) == ["UCa-hit", "UCb-hit", "UCc-hit"]
    assert (idea["score"], idea["hit_channels"], idea["topic"]) == (3.0, 3, "topic")  # three same-size, brand-new hits


def test_find_hits_skips_videos_too_old_or_too_little_watched(fake_youtube, monkeypatch):
    results = youtube_api.search("query")
    too_old = replace(results[0], published_at=results[0].published_at - timedelta(days=config.MAX_HIT_AGE_DAYS + 1))
    monkeypatch.setattr(youtube_api, "search", lambda query: [too_old] + results[1:])
    monkeypatch.setattr(config, "MIN_HIT_VIEWS", 450)
    hits = find_hits("query", my_channel_id="UCme", my_median=100)
    assert [hit["video_id"] for hit in hits] == ["UCb-hit"]  # UCa-hit is too old, UCc-hit has only 400 views


def test_repeatable_needs_enough_channels_and_score(monkeypatch):
    monkeypatch.setattr(config, "MIN_HITS", 3)
    monkeypatch.setattr(config, "MIN_SCORE", 1.0)
    assert is_repeatable({"hit_channels": 3, "score": 3.0})
    assert not is_repeatable({"hit_channels": 1, "score": 3.0})  # three hits, but all from the same channel
    assert not is_repeatable({"hit_channels": 3, "score": 0.9})  # enough channels, but old hits from giant channels


def test_query_variants_keep_real_suggestions_only(fake_youtube, monkeypatch):
    monkeypatch.setattr(youtube_api, "autocomplete", lambda query: ["Query", "query for beginners", "query free", "query 2026"])
    monkeypatch.setattr(llm, "ask", lambda prompt, schema: schema(queries=["query free", "made up", "query for beginners", "query 2026"]))
    monkeypatch.setattr(config, "QUERY_VARIANTS", 2)
    topics = [{"name": "topic", "search_query": "query"}, {"name": "other", "search_query": "query"}]
    suggested = youtube_suggestions(topics)
    assert suggested[0] == {"name": "topic", "search_query": "query", "suggestions": ["query for beginners", "query free", "query 2026"]}  # without the query itself
    queries = query_variants(suggested)
    assert [q["search_query"] for q in queries] == ["query", "query free", "query for beginners"]  # LLM picks only: real suggestions, capped
    assert {q["topic"] for q in queries} == {"topic"}  # a query two topics share is only scored once

    monkeypatch.setattr(config, "QUERY_VARIANTS", 0)
    assert [q["search_query"] for q in query_variants(suggested[:1])] == ["query"]


# --- The Google side ---


def test_search_trends_measure_the_floor_not_the_average():
    prior = [100, 100, 100, 900, 200, 200, 200, 200, 200, 200, 200, 200]
    last = [200, 200, 200, 300, 250, 250, 250, 250, 250, 250, 250, 250]
    months = {f"{2024 + n // 12}-{n % 12 + 1:02d}": searches for n, searches in enumerate(prior + last)}
    measured = measure(months)
    assert (measured["floor_prior_12m"], measured["floor_last_12m"], measured["floor_change_pct"], measured["trend"]) == (100, 200, 100.0, "rising")
    assert measured["yoy_change_pct"] == 3.6  # the spike a year ago hides the growth from the average

    assert measure({month: 0 for month in months})["trend"] == "no volume"
    assert measure({month: (0 if n < 12 else 50) for n, month in enumerate(months)})["trend"] == "new"
    assert measure({"2026-08": 100})["trend"] == "needs 24+ months"
    assert [k["keyword"] for k in search_trends([make_keyword("small", 10, months), make_keyword("big", 900, months)])] == ["big", "small"]


def test_rising_keywords_give_the_reason(monkeypatch):
    monkeypatch.setattr(config, "MIN_MONTHLY_SEARCHES", 200)
    monkeypatch.setattr(config, "YOY_FALLING_PCT", -20)
    monkeypatch.setattr(config, "MAX_GROUPED_KEYWORDS", 1)
    keywords = [
        make_keyword("biggest", 9000, trend="rising", yoy_change_pct=50.0),
        make_keyword("second", 800, trend="new", yoy_change_pct=None),
        make_keyword("past its peak", 700, trend="rising", yoy_change_pct=-40.0),
        make_keyword("flat", 600, trend="flat", yoy_change_pct=1.0),
        make_keyword("tiny", 50, trend="rising", yoy_change_pct=90.0),
    ]
    verdicts = {k["keyword"]: k["verdict"] for k in rising_keywords(keywords)}
    assert verdicts == {
        "biggest": "goes on",
        "second": "not among the biggest",
        "past its peak": "the quiet months rose, but searches over the whole year fell",
        "flat": "search is flat",
        "tiny": "under 200 searches a month",
    }


def test_group_into_topics_keeps_variants_together_and_drops_invented_keywords(monkeypatch):
    same = {"2026-08": 500}
    keywords = [make_keyword("ai agents", 500, same), make_keyword("ai agency", 500, same), make_keyword("claude code", 900)]
    answer = grouping.KeywordTopics(topics=[
        grouping.KeywordTopic(name="AI agents", search_query="ai agents", keywords=["ai agents", "made up"], skip=""),
        grouping.KeywordTopic(name="Claude Code", search_query="claude code", keywords=["claude code", "ai agents"], skip=""),
        grouping.KeywordTopic(name="Nothing", search_query="nothing", keywords=["also made up"], skip=""),
    ])  # fmt: skip
    prompts = []
    monkeypatch.setattr(llm, "ask", lambda prompt, schema: prompts.append(prompt) or answer)

    topics = grouping.group_into_topics(keywords, about=["ai agents"])

    assert "around: ai agents" in prompts[0]
    assert "- ai agents | 500 a month | also searched as: ai agency" in prompts[0]  # the LLM sees one line per variant group
    assert [(topic["name"], topic["keywords"]) for topic in topics] == [("AI agents", ["ai agents", "ai agency"]), ("Claude Code", ["claude code"])]


def test_choose_topics_prefers_the_biggest_gains_and_never_a_skipped_topic(monkeypatch):
    monkeypatch.setattr(config, "MAX_TOPICS", 1)
    keywords = [
        make_keyword("a", 100, last_12m_avg=100, prior_12m_avg=90),
        make_keyword("b", 900, last_12m_avg=900, prior_12m_avg=100),
        make_keyword("c", 5000, last_12m_avg=5000, prior_12m_avg=10),
    ]
    topics = [{"name": name.upper(), "search_query": name, "keywords": [name], "skip": "brand name" if name == "c" else ""} for name in "abc"]
    chosen = {t["name"]: (t["biggest_keyword"], t["searches_gained"], t["goes_on"]) for t in choose_topics(topics, keywords)}
    assert chosen == {"A": ("a", 10, False), "B": ("b", 800, True), "C": ("c", 4990, False)}


def test_google_seeds_fall_back_to_the_search_query(monkeypatch):
    topics = [{"name": "A", "search_query": "query a"}, {"name": "B", "search_query": "query b"}]
    scored = [{"search_query": "long phrasing a", "topic": "A"}]
    phrased = with_phrasings(topics, scored)
    assert [topic["phrasings"] for topic in phrased] == [["long phrasing a"], ["query b"]]

    answer = Seeds(topics=[TopicSeeds(topic_number=1, seeds=["one", "two", "three", "four"])])
    monkeypatch.setattr(llm, "ask", lambda prompt, schema: answer)
    assert [topic["seeds"] for topic in google_seeds(phrased)] == [["one", "two", "three"], ["query b"]]


def test_pick_topic_keywords_judges_each_topic_on_its_own_candidates(monkeypatch):
    monkeypatch.setattr(config, "MIN_MONTHLY_SEARCHES", 200)
    topics = [
        {"name": "PDF to text", "search_query": "convert pdf to text", "phrasings": ["convert scanned pdf to text"]},
        {"name": "Unknown to Google", "search_query": "gpt-6 vs fable"},
    ]
    candidates = {"PDF to text": picking.biggest_candidates([make_keyword("edit pdf", 9000), make_keyword("ocr pdf", 300), make_keyword("too small", 50)])}
    prompts = []
    monkeypatch.setattr(llm, "ask", lambda prompt, schema: prompts.append(prompt) or picking.Picks(keywords=["ocr pdf"]))

    picked = picking.pick_topic_keywords(topics, candidates)

    assert len(prompts) == 1 and "- convert scanned pdf to text" in prompts[0] and "too small" not in prompts[0]  # a topic without candidates costs no LLM call
    assert [(t["name"], t["keywords"], t["candidates"]) for t in picked] == [("PDF to text", ["ocr pdf"], 2), ("Unknown to Google", [], 0)]


# --- The verdict ---


def test_scoreboard_verdicts(monkeypatch):
    monkeypatch.setattr(config, "MIN_HITS", 3)
    monkeypatch.setattr(config, "MIN_SCORE", 1.0)
    monkeypatch.setattr(config, "MIN_MONTHLY_SEARCHES", 200)
    monkeypatch.setattr(config, "YOY_FALLING_PCT", -20)
    rising = dict(trend="rising", yoy_change_pct=50.0, last_12m_avg=900, prior_12m_avg=600)
    keywords = [make_keyword("both", 900, **rising), make_keyword("fading", 900, **(rising | {"trend": "shrinking"})), make_keyword("wanted", 900, **rising), make_keyword("brand", 900, **rising)]
    topics = [{"name": name.title(), "search_query": name, "keywords": [name], "skip": ""} for name in ("both", "fading", "wanted")]
    topics += [{"name": "Brand", "search_query": "brand", "keywords": ["brand"], "skip": "brand name"}, {"name": "Unknown", "search_query": "unknown", "keywords": [], "skip": ""}]
    good, weak = {"score": 3.0, "hit_channels": 3, "hits": []}, {"score": 0.2, "hit_channels": 1, "hits": []}
    scored = [
        {"search_query": "both", "topic": "Both"} | weak,
        {"search_query": "both for beginners", "topic": "Both"} | good,  # the best phrasing of a topic counts
        {"search_query": "fading", "topic": "Fading"} | good,
        {"search_query": "wanted", "topic": "Wanted"} | weak,
        {"search_query": "unknown", "topic": "Unknown"} | good,
    ]
    rows = scoreboard(topics, keywords, scored)
    assert rows[0]["topic"] == "Both" and rows[0]["youtube_query"] == "both for beginners"  # topics to make come first
    assert {row["topic"]: row["verdict"] for row in rows} == {
        "Both": "make it",
        "Fading": "repeatable, but search is shrinking",
        "Wanted": "rising, but not repeatable",
        "Brand": "skipped: brand name",
        "Unknown": "repeatable, but Google knows no phrasing of it",
    }


# --- The plumbing ---


def test_cache_reuses_until_expired_or_refreshed(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_HOURS", 24)
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


def test_run_saves_each_steps_input_and_output(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(settings, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(settings, "ROOT", tmp_path)
    run = Run("from-keywords", ["ai agents"])
    run.step("First")
    assert run.save("keyword_ideas", input=["ai agents"], output=[{"keyword": n} for n in range(10)], summary={"keywords": 10}) == [{"keyword": n} for n in range(10)]

    info = json.loads((run.folder / "run.json").read_text())
    assert (info["pipeline"], info["seeds"]) == ("from-keywords", ["ai agents"]) and "MIN_HITS" in info["settings"]
    saved = json.loads((run.folder / "01_keyword_ideas.json").read_text())
    assert saved["input"] == ["ai agents"] and len(saved["output"]) == 10  # the output is saved in full
    assert list(saved)[:2] == ["step", "summary"] and saved["summary"] == {"keywords": 10}  # the step in numbers, on top
    assert tally([{"trend": "rising"}, {"trend": "flat"}, {"trend": "rising"}], "trend") == {"rising": 2, "flat": 1}
    assert sample(list(range(10))) == [0, 1, 2, "... and 7 more"]  # a long input is only sampled

    run.save("seeds_to_keywords", part="a", input=["ai agents"], output={}, summary={})  # two views of one step: parts a and b
    assert (run.folder / "01_a_seeds_to_keywords.json").exists()


def test_by_seed_shows_which_keywords_each_seed_brought_in():
    ideas = [
        {"keyword": "codex astartes", "avg_monthly_searches": 2400},
        {"keyword": "claudecode", "avg_monthly_searches": 1000},
        {"keyword": "cursor ai", "avg_monthly_searches": 90500},
        {"keyword": "codex cli", "avg_monthly_searches": 8100},
    ]
    found = by_seed(["codex", "claude code"], ideas)
    assert found["keywords"] == {
        "codex": {"codex cli": 8100, "codex astartes": 2400},  # most searched first
        "claude code": {"claudecode": 1000},  # spaces don't matter
        "related": {"cursor ai": 90500},  # Google's related ideas, without a seed in them
    }
    assert found["summary"] == {"seed keywords": 2, "keywords found": 4, 'with "codex" in them': 2, 'with "claude code" in them': 1, "related, without a seed in them": 1}
