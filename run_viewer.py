"""Collects every run's checkpoints into output/viewer/ for index.html to display.

    python3 run_viewer.py

ideate.py does this after every run, so you only need the command above after running one of the
tools on its own. Browsers don't let a page opened from disk read JSON files, so the data is
written as .js files that index.html loads with <script> tags: runs.js lists the runs and
<run id>.js holds the steps of one run.

A run is a list of steps. Every step has a commentary (`what` the step does, and what it `found`
in this run) and blocks of data (tables, lists, logs) taken from the checkpoint files.
"""

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    import config
except ModuleNotFoundError:
    raise SystemExit("No config.py yet. Run `cp config.py.example config.py`, then set your channel in it.")

HERE = Path(__file__).resolve().parent
REPEATABILITY_TOOL = HERE / "repeatability-analysis"
KEYWORD_TOOL = HERE / "keyword-analysis"
OUTPUT_DIR = HERE / "output"
VIEWER_DIR = OUTPUT_DIR / "viewer"

YOUTUBE, KEYWORDS, IDEATE = "YouTube tool", "Keyword tool", "ideate.py"  # who produced a step
GEO_NAMES = {"2840": "United States"}
LANGUAGE_NAMES = {"1000": "English"}


def build():
    """Write the data files for every run found on disk."""
    VIEWER_DIR.mkdir(parents=True, exist_ok=True)
    runs = find_runs()
    for run in runs:
        text = json.dumps(run, ensure_ascii=False)
        (VIEWER_DIR / f"{run['id']}.js").write_text(f"window.RUN_DATA = window.RUN_DATA || {{}};\nwindow.RUN_DATA[{json.dumps(run['id'])}] = {text};\n")
    summaries = [{key: value for key, value in run.items() if key != "steps"} | {"step_count": len(run["steps"])} for run in runs]
    (VIEWER_DIR / "runs.js").write_text(f"window.RUNS = {json.dumps(summaries, ensure_ascii=False)};\n")
    return runs


# --- Finding the runs ---


def find_runs() -> list[dict]:
    """Every ideate.py run, then every run of a single tool that is not part of one. Newest first.

    ideate.py gives both tools its own run ID, so the checkpoints of a run carry the same ID everywhere.
    """
    ideate_ids = {path.name.removesuffix("_run.json") for path in OUTPUT_DIR.glob("*_run.json")}
    repeatability_ids = {path.name.split("_step_")[0] for path in (REPEATABILITY_TOOL / "checkpoints").glob("*_step_*.json")}
    keyword_ids = {path.name for path in (KEYWORD_TOOL / "checkpoints").glob("*") if path.is_dir()}

    runs = [ideate_run(run_id) for run_id in ideate_ids]
    runs += [youtube_only_run(run_id) for run_id in repeatability_ids - ideate_ids]
    runs += [keywords_only_run(run_id) for run_id in keyword_ids if run_id.split("_topic")[0] not in ideate_ids]
    return sorted(runs, key=lambda run: run["id"], reverse=True)


def keyword_log(keyword_id: str) -> str:
    path = KEYWORD_TOOL / "checkpoints" / keyword_id / "run.log"
    return path.read_text() if path.exists() else ""


# --- The kinds of run ---


def ideate_run(run_id: str) -> dict:
    info = read_json(OUTPUT_DIR / f"{run_id}_run.json")
    ideate_settings = Settings(info["settings"])
    scored, settings = load_scored(run_id)

    if info["direction"] == "from-keywords":
        keywords = read_csv(OUTPUT_DIR / f"{run_id}_keywords.csv")
        steps = [
            *keyword_steps(run_id),
            rising_keywords_step(run_id, keywords, ideate_settings),
            found_topics_step(run_id, keywords, ideate_settings),
            *repeatability_steps(run_id, from_phrases=True),
        ]
        subtitle = "Seeds: " + ", ".join(info["seeds"])
    else:
        keywords = [row for path in sorted(OUTPUT_DIR.glob(f"{run_id}_topic*_keywords.csv")) for row in read_csv(path)]
        steps = [
            *repeatability_steps(run_id, from_phrases=False),
            google_seeds_step(run_id),
            topic_ideas_step(run_id, ideate_settings),
            picked_keywords_step(run_id, keywords),
        ]
        subtitle = "From the scanned channels' outlier videos"
    steps.append(scoreboard_step(run_id, scored, settings, keywords, ideate_settings))
    return finish_run(run_id, info["direction"], subtitle, steps)


def youtube_only_run(run_id: str) -> dict:
    from_phrases = not (REPEATABILITY_TOOL / "checkpoints" / f"{run_id}_step_1.json").exists()
    steps = [*repeatability_steps(run_id, from_phrases), top_ideas_step(run_id)]
    subtitle = "Search queries given with --queries" if from_phrases else "From the scanned channels' outlier videos"
    return finish_run(run_id, "youtube-only", subtitle, steps)


def keywords_only_run(run_id: str) -> dict:
    inputs = read_json(KEYWORD_TOOL / "checkpoints" / run_id / "01_inputs.json") or {}
    steps = keyword_steps(run_id)
    steps[-1]["title"] = "Final Results"
    terms = inputs.get("terms") or []
    subtitle = f"kwa {inputs.get('command', '?')}: " + ", ".join(terms[:4]) + (f" and {len(terms) - 4} more" if len(terms) > 4 else "")
    return finish_run(run_id, "keywords-only", subtitle, steps)


def finish_run(run_id: str, direction: str, subtitle: str, steps: list[dict]) -> dict:
    stopped_at = next((number for number, step in enumerate(steps, start=1) if step["status"] == "missing"), None)
    return {
        "id": run_id,
        "direction": direction,
        "started_at": datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").isoformat(),
        "subtitle": subtitle,
        "headline": steps[-1].get("headline", ""),
        "stopped_at": stopped_at,  # None when every step has its data
        "steps": steps,
    }


# --- The YouTube tool's steps (repeatability-analysis) ---


def load_scored(run_id: str) -> tuple[list[dict], "Settings"]:
    """The step 3 checkpoint (every scored query with its hits) and the settings the run used."""
    scored = read_json(REPEATABILITY_TOOL / "checkpoints" / f"{run_id}_step_3.json") or []
    final_output = read_json(REPEATABILITY_TOOL / "output" / f"final_output_{run_id}.json")
    # A run that did not get to its final output explains its steps with the settings config.py has now.
    return scored, Settings(final_output["settings"] if final_output else vars(config))


def repeatability_steps(run_id: str, from_phrases: bool) -> list[dict]:
    scored, s = load_scored(run_id)
    checkpoint = lambda number: REPEATABILITY_TOOL / "checkpoints" / f"{run_id}_step_{number}.json"  # noqa: E731
    run_time = datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").astimezone()
    steps = []

    if not from_phrases:
        what = (
            f"Every channel in CHANNELS_TO_SCAN is scanned. A channel's median is taken over its last {s['UPLOADS_FOR_MEDIAN']} "
            f"{s['FORMAT']} uploads, and an upload with at least {s['OUTLIER_MULTIPLE']}x that median is an outlier: a video that "
            f"did far better than the channel normally does. The {s['TOP_CANDIDATES']} biggest outliers go on to the next step."
        )
        candidates = read_json(checkpoint(1))
        if candidates is None:
            steps.append(missing_step("Outlier videos", YOUTUBE, what))
        else:
            found = [f"{count(len(candidates), 'outlier')} from {count(len({c['video']['channel_id'] for c in candidates}), 'channel')}."]
            if candidates:
                best, last = candidates[0], candidates[-1]
                found.append(
                    f"The biggest is \"{best['video']['title']}\" by {best['video']['channel_title']}: {best['video']['views']:,} views, "
                    f"{best['multiple']:.0f}x the channel's median of {best['channel_median']:,.0f}."
                )
                found.append(f"The smallest multiple that made the cut is {last['multiple']:.1f}x.")
                busiest, videos = Counter(c["video"]["channel_title"] for c in candidates).most_common(1)[0]
                if videos > 1:
                    found.append(f"{busiest} alone has {videos} of them, so its subjects weigh heavily on the topics of the next step.")
            rows = [video_row(c["video"], c["channel_median"], run_time) | {"multiple": c["multiple"]} for c in candidates]
            columns = [column("multiple", "Multiple", "multiple"), *VIDEO_COLUMNS]
            steps.append(step("Outlier videos", YOUTUBE, what, found, [table(columns, rows)], [checkpoint(1)]))

        what = (
            f"An LLM ({s['LLM_PROVIDER']}) groups the outliers that are about the same subject into one topic, and writes for each "
            "topic the search query a viewer would type into YouTube to find such videos. Queries are kept short and generic: "
            "no channel names, no clickbait."
        )
        topics = read_json(checkpoint(2))
        if topics is None:
            steps.append(missing_step("Topics", YOUTUBE, what))
        else:
            titles = {c["video"]["id"]: c["video"]["title"] for c in candidates or []}
            merged = [topic for topic in topics if len(topic["video_ids"]) > 1]
            found = [f"{count(len(titles), 'outlier')} became {count(len(topics), 'topic')}."]
            if merged:
                found.append(f"{count(len(merged), 'topic')} merged more than one video: " + ", ".join(topic["name"] for topic in merged) + ".")
            unused = [title for video_id, title in titles.items() if not any(video_id in topic["video_ids"] for topic in topics)]
            if unused:
                found.append(f"The LLM left {count(len(unused), 'outlier')} out of every topic: " + "; ".join(unused) + ".")
            rows = [
                {"name": topic["name"], "search_query": topic["search_query"], "videos": [titles.get(v, v) for v in topic["video_ids"]]}
                for topic in topics
            ]
            columns = [column("name", "Topic"), column("search_query", "Search query"), column("videos", "Outliers it came from", "lines")]
            steps.append(step("Topics", YOUTUBE, what, found, [table(columns, rows)], [checkpoint(2)]))

    if from_phrases:
        source = "Steps 1 and 2 of the YouTube tool are skipped: the phrases in the hand-off file are scored exactly as written, without autocomplete variants. "
    else:
        source = (
            f"Each topic's query is first expanded with up to {s['QUERY_VARIANTS']} YouTube autocomplete suggestions picked by the LLM "
            "(the phrasings viewers really type). Every query is scored as an idea of its own. "
        )
    what = (
        f"{source}A query is searched on YouTube ({s['SEARCH_RESULTS_PER_QUERY']} results). Results in the wrong format, older than "
        f"{s['MAX_HIT_AGE_DAYS']} days or under {s['MIN_HIT_VIEWS']:,} views are dropped, and the first {s['CHANNELS_PER_QUERY']} "
        f"different channels are kept. A result is a hit when it has at least {s['HIT_MULTIPLE']}x its own channel's median views. "
        f"A hit weighs more when it is recent (the weight halves every {s['AGE_HALF_LIFE_DAYS']} days) and when the channel is "
        "close to yours in size. The repeatability score is the sum of the weights: 1.0 is one brand-new hit from a channel your size."
    )
    if not scored and not checkpoint(3).exists():
        steps.append(missing_step("Repeatability scores", YOUTUBE, what))
        return steps

    verdicts = judge_ideas(scored, s)
    variants = [idea for idea in scored if idea["search_query"] != idea["topic"]["search_query"]]
    found = [f"{count(len(scored), 'search query', 'search queries')} scored" + (f", {len(variants)} of them autocomplete variants." if variants else ".")]
    if scored:
        best = scored[0]
        found.append(
            f"The best is \"{best['search_query']}\" with {best['score']:.2f}: {count(len(best['hits']), 'hit')} on {count(hit_channels(best), 'channel')}."
        )
        passing = [idea for idea in scored if is_repeatable(idea, s)]
        found.append(
            f"{len(passing)} of {len(scored)} pass the bar for repeatable (hits on {s['MIN_HITS']}+ channels and a score of {s['MIN_SCORE']}+)."
        )
        hitless = [idea["search_query"] for idea in scored if not idea["hits"]]
        if hitless:
            found.append(f"No hits at all for: {', '.join(hitless)}.")
    found.append("Open a row to see the hit videos behind its score.")
    rows = [
        {
            "score": idea["score"],
            "search_query": idea["search_query"],
            "topic": idea["topic"]["name"],
            "hits": len(idea["hits"]),
            "hit_channels": hit_channels(idea),
            "verdict": verdict_cell(verdicts[idea["search_query"]]),
            "children": hits_table(idea, run_time),
        }
        for idea in scored
    ]
    columns = [
        column("score", "Repeatability", "score"), column("search_query", "Search query"), column("topic", "Topic"),
        column("hits", "Hits", "number"), column("hit_channels", "Channels", "number"), column("verdict", "Top idea?", "verdict"),
    ]  # fmt: skip
    if from_phrases:
        columns = [c for c in columns if c["key"] != "topic"]  # without step 2 the topic is the query itself
    steps.append(step("Repeatability scores", YOUTUBE, what, found, [table(columns, rows)], [checkpoint(3)]))
    return steps


def top_ideas_step(run_id: str) -> dict:
    """The final results of the YouTube tool on its own."""
    scored, s = load_scored(run_id)
    what = (
        f"The best ideas, skipping the unrepeatable ones (hits on fewer than {s['MIN_HITS']} channels, or a score under {s['MIN_SCORE']}) "
        f"and the repeats: an idea sharing more than {s['MAX_HIT_OVERLAP']:.0%} of its hits with a better idea is the same idea in other "
        f"words. At most {s['TOP_IDEAS']} are presented."
    )
    if not scored:
        return missing_step("Final Results", YOUTUBE, what)
    verdicts = judge_ideas(scored, s)
    ideas = [idea for idea in scored if verdicts[idea["search_query"]] == "top idea"]
    run_time = datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").astimezone()
    found = [f"{count(len(ideas), 'top idea')} out of {count(len(scored), 'scored query', 'scored queries')}."]
    if ideas:
        found.append(f"Number 1 is \"{ideas[0]['search_query']}\": repeatability {ideas[0]['score']:.2f} from hits on {count(hit_channels(ideas[0]), 'channel')}.")
    reasons = Counter(re.sub(r'".*"', "a better idea", verdict) for verdict in verdicts.values() if verdict != "top idea")
    if reasons:
        found.append("Left out: " + ", ".join(f"{n} x {reason}" for reason, n in reasons.most_common()) + ".")
    rows = [
        {
            "rank": rank,
            "search_query": idea["search_query"],
            "topic": idea["topic"]["name"],
            "score": idea["score"],
            "hits": len(idea["hits"]),
            "hit_channels": hit_channels(idea),
            "children": hits_table(idea, run_time),
        }
        for rank, idea in enumerate(ideas, start=1)
    ]
    columns = [
        column("rank", "#", "number"), column("search_query", "Idea"), column("topic", "Topic"),
        column("score", "Repeatability", "score"), column("hits", "Hits", "number"), column("hit_channels", "Channels", "number"),
    ]  # fmt: skip
    files = [REPEATABILITY_TOOL / "output" / f"final_output_{run_id}.json"]
    result = step("Final Results", YOUTUBE, what, found, [table(columns, rows)], files)
    result["headline"] = f"Top idea: {ideas[0]['search_query']}" if ideas else "No idea passed the bar"
    return result


def judge_ideas(scored: list[dict], s: "Settings") -> dict[str, str]:
    """Why each scored query is a top idea or not: the rules of top_ideas() in step3_repeatability.py."""
    chosen, verdicts = [], {}
    for idea in scored:  # best first
        video_ids = {hit["video"]["id"] for hit in idea["hits"]}
        repeat_of = next((better for better in chosen if overlap(video_ids, better) > s.get("MAX_HIT_OVERLAP", 1)), None)
        if hit_channels(idea) < s.get("MIN_HITS", 0):
            verdict = f"hits on under {s['MIN_HITS']} channels"
        elif idea["score"] < s.get("MIN_SCORE", 0):
            verdict = f"score under {s['MIN_SCORE']}"
        elif repeat_of:
            verdict = f"repeats \"{repeat_of['search_query']}\""
        else:
            chosen.append(idea)
            verdict = "top idea" if len(chosen) <= s.get("TOP_IDEAS", len(scored)) else f"outside the top {s['TOP_IDEAS']}"
        verdicts[idea["search_query"]] = verdict
    return verdicts


def overlap(video_ids: set[str], other: dict) -> float:
    """The share of an idea's hits that are also hits of the other idea."""
    other_ids = {hit["video"]["id"] for hit in other["hits"]}
    return len(video_ids & other_ids) / len(video_ids) if video_ids else 0.0


def hit_channels(idea: dict) -> int:
    return len({hit["video"]["channel_id"] for hit in idea["hits"]})


def is_repeatable(idea: dict, s: "Settings") -> bool:
    return hit_channels(idea) >= s.get("MIN_HITS", 0) and idea["score"] >= s.get("MIN_SCORE", 0)


def verdict_cell(verdict: str) -> dict:
    return {"text": verdict, "tone": "good" if verdict == "top idea" else "muted"}


def hits_table(idea: dict, run_time: datetime) -> dict:
    hits = sorted(idea["hits"], key=lambda hit: hit["weight"], reverse=True)
    rows = [
        video_row(hit["video"], hit["channel_median"], run_time) | {"weight": hit["weight"], "multiple": hit["video"]["views"] / hit["channel_median"]}
        for hit in hits
    ]
    return table([column("weight", "Weight", "score"), column("multiple", "Multiple", "multiple"), *VIDEO_COLUMNS], rows)


def video_row(video: dict, channel_median: float, run_time: datetime) -> dict:
    published = datetime.fromisoformat(video["published_at"])
    return {
        "video": {"id": video["id"], "title": video["title"]},
        "channel": {"id": video["channel_id"], "title": video["channel_title"]},
        "views": video["views"],
        "channel_median": channel_median,
        "age_days": (run_time.astimezone(timezone.utc) - published).days,
        "published": video["published_at"][:10],
    }


# --- The keyword tool's steps (keyword-analysis) ---


def keyword_steps(run_id: str) -> list[dict]:
    """The keyword tool's checkpoints as four steps. Its run.log says what happened in each."""
    folder = KEYWORD_TOOL / "checkpoints" / run_id
    find = lambda name: next(iter(sorted(folder.glob(f"*_{name}.*"))), None)  # noqa: E731
    log = split_log(keyword_log(run_id))
    inputs = read_json(find("inputs")) or {}
    asks_for_ideas = inputs.get("command", "ideas") == "ideas"  # ideate.py always asks for ideas; `kwa metrics` is a single tool run
    steps = []

    if asks_for_ideas:
        what = (
            "The seed keywords are sent to Google Ads Keyword Planner (GenerateKeywordIdeas), which answers with the related "
            "keywords people search for on Google, each with its search volume month by month."
        )
    else:
        what = (
            "The phrases are sent to Google Ads Keyword Planner (GenerateKeywordHistoricalMetrics), which answers with how often "
            "exactly those phrases are searched on Google, month by month."
        )
    if not inputs:
        steps.append(missing_step("Keyword request", KEYWORDS, what, log.get("failure")))
    else:
        request = read_json(find("request"))
        facts = [
            ["Command", f"kwa {inputs.get('command')}"],
            ["Seed keywords" if asks_for_ideas else "Phrases", ", ".join(inputs.get("terms") or []) or "none"],
            ["Location", ", ".join(GEO_NAMES.get(geo, geo) for geo in inputs.get("geo_ids") or [])],
            ["Language", LANGUAGE_NAMES.get(inputs.get("language_id"), inputs.get("language_id"))],
            ["History", f"last {inputs['months']} completed months" if inputs.get("months") else "not recorded"],
        ]
        blocks = [{"type": "facts", "facts": facts}]
        if request:
            blocks.append({"type": "json", "label": "The request sent to Google", "value": request})
        blocks.append(log_block(log, "request"))
        steps.append(step("Keyword request", KEYWORDS, what, log_findings(log, "request"), blocks, [find("inputs"), find("request")]))

    what = (
        "Google's answer, saved untouched before anything is done with it. Keyword Planner rounds volumes into buckets "
        "(10, 20, ... 49,500, 60,500 ...), so these are magnitudes, not exact counts. A phrase nobody searches still comes back, with no volume."
    )
    response = read_json(find("raw_response"))
    if response is None:
        steps.append(missing_step("Keyword Planner response", KEYWORDS, what, log.get("failure") if inputs else None))
    else:
        blocks = [
            {"type": "json", "label": f"The first of {count(len(response), 'result')}, with its monthly volumes cut short", "value": shorten(response[0]) if response else None},
            log_block(log, "response"),
        ]
        steps.append(step("Keyword Planner response", KEYWORDS, what, log_findings(log, "response"), blocks, [find("raw_response")]))

    what = (
        "The response is flattened into one row per keyword: average monthly searches, how hard advertisers compete for it "
        "(competition and its 0-100 index), what they bid for the top of the page, and the monthly history."
    )
    parsed = read_csv(find("parsed_rows"))
    if not parsed:
        steps.append(missing_step("Parsed keywords", KEYWORDS, what))
    else:
        columns = [c for c in KEYWORD_COLUMNS if c["key"] in ("keyword", "avg_monthly_searches", "history", "competition", "competition_index", "bids")]
        blocks = [table(columns, [keyword_row(row) for row in parsed], limit=25), log_block(log, "parse")]
        steps.append(step("Parsed keywords", KEYWORDS, what, log_findings(log, "parse"), blocks, [find("parsed_rows")]))

    what = (
        "Search demand is seasonal, so every comparison is year over year: the last 12 months against the 12 before. The trend comes "
        "from the floor, the mean of the 3 quietest months of a window: the demand that is there even in the slow season. "
        "Rising is a floor up 20% or more, shrinking is down 20% or more, flat is in between (a smaller change can be a single "
        "rounding bucket), and new means there was no floor a year ago. The rows are then sorted by search volume and saved."
    )
    rows = read_csv(find("final_sorted"))
    if not rows:
        steps.append(missing_step("Search trends", KEYWORDS, what))
    else:
        found = log_findings(log, "trend")
        rising = [row for row in rows if row.get("floor_trend") == "rising"]
        if rising:
            found.append(f"The biggest rising keyword is \"{rising[0]['keyword']}\" with {number(rising[0]['avg_monthly_searches']):,} searches a month.")
        blocks = [table(KEYWORD_COLUMNS, [keyword_row(row) for row in rows], limit=25), log_block(log, "trend")]
        files = [find("trend_metrics"), find("final_sorted"), find("monthly_wide")]
        result = step("Search trends", KEYWORDS, what, found, blocks, files)
        result["headline"] = f"{count(len(rows), 'keyword')}, {len(rising)} rising"
        steps.append(result)
    stopped = next((step for step in steps if step["status"] == "missing"), None)
    if stopped and not stopped["blocks"] and keyword_log(run_id):
        stopped["blocks"] = [{"type": "log", "label": "The tool's log up to where it stopped", "text": keyword_log(run_id).strip()}]
    return steps


def split_log(text: str) -> dict[str, list[str]]:
    """The lines of run.log per step of the viewer, and the lines of a failure if there was one."""
    groups = {"request": ["resolve inputs", "build the"], "response": ["call Keyword"], "parse": ["parse the"], "trend": ["measure the trend", "sort by"]}
    log, current = {}, None
    for line in text.splitlines():
        message = re.sub(r"^\d\d:\d\d:\d\d \[[^\]]+\] ", "", line)
        if "run failed" in message or "failure" in log:  # a traceback follows on the next lines
            log.setdefault("failure", []).append(line)
        elif match := re.match(r"step \d+: (.*)", message):
            current = next((group for group, starts in groups.items() if any(match[1].startswith(start) for start in starts)), None)
        if current and "failure" not in log:
            log.setdefault(current, []).append(line)
    return log


def log_findings(log: dict, group: str) -> list[str]:
    """The details the tool logged during a step, as sentences."""
    details = [re.sub(r"^\d\d:\d\d:\d\d \[[^\]]+\] {4,}", "", line) for line in log.get(group, []) if re.search(r"\] {4,}", line)]
    details = [detail for detail in details if not detail.startswith(("checkpoint ->", "output ->", "customer "))]
    return [detail[0].upper() + detail[1:] + ("" if detail.endswith(".") else ".") for detail in details]


def log_block(log: dict, group: str) -> dict:
    return {"type": "log", "label": "What the tool logged during this step", "text": "\n".join(log.get(group, []))}


def shorten(value):
    """Long lists cut down to their first item, to show the shape of a big response."""
    if isinstance(value, dict):
        return {key: shorten(item) for key, item in value.items()}
    if isinstance(value, list) and len(value) > 1:
        return [shorten(value[0]), f"... and {len(value) - 1} more"]
    return value


def keyword_row(row: dict) -> dict:
    low, high = number(row.get("low_top_of_page_bid")), number(row.get("high_top_of_page_bid"))
    return {
        "keyword": row["keyword"],
        "avg_monthly_searches": number(row.get("avg_monthly_searches")),
        "history": monthly(row.get("monthly_searches", "")),
        "yoy_change_pct": number(row.get("yoy_change_pct")),
        "floor_change_pct": number(row.get("floor_change_pct")),
        "floor_trend": row.get("floor_trend", ""),
        "competition": (row.get("competition") or "").lower(),
        "competition_index": number(row.get("competition_index")),
        "bids": f"${low:.2f} - ${high:.2f}" if low is not None and high is not None else "",
    }


def monthly(packed: str) -> dict | None:
    """'2026-07:2900 2026-08:2400' -> {"start": "2026-07", "values": [2900, 2400]}"""
    pairs = sorted(item.split(":") for item in packed.split())
    return {"start": pairs[0][0], "values": [int(n) for _, n in pairs]} if pairs else None


# --- ideate.py's own steps: a topic is judged as a whole, whatever phrasing YouTube or Google knows it under ---


def rising_rule(s: "Settings") -> str:
    return (
        f"its trend is {' or '.join(s.get('KEEP_TRENDS', []))} (measured on the quiet months of the year), it has at least "
        f"{s['MIN_MONTHLY_SEARCHES']} searches a month, and its searches over the whole year are not down {abs(s.get('YOY_FALLING_PCT', 0))}% or more: "
        "a rising floor under a falling year is a keyword past its peak"
    )


def keywords_table(rows: list[dict], label: str = "", limit: int | None = None) -> dict:
    columns = [c for c in KEYWORD_COLUMNS if c["key"] not in ("competition", "competition_index", "bids")]
    return table(columns, [keyword_row(row) for row in rows], limit=limit) | {"label": label}


def rising_keywords_step(run_id: str, keywords: list[dict], s: "Settings") -> dict:
    what = (
        f"ideate.py keeps the keywords that are rising. A keyword is rising when {rising_rule(s)}. At most {s['MAX_GROUPED_KEYWORDS']} "
        "go on to the next step, the biggest first. The others stay out: a topic built on them would not be rising either."
    )
    verdicts_file = OUTPUT_DIR / f"{run_id}_keyword_verdicts.json"
    reasons = read_json(verdicts_file)  # ideate.py records why each keyword goes on or not
    if not reasons:
        return missing_step("Rising keywords", IDEATE, what)
    kept = [keyword for keyword, reason in reasons.items() if reason == "goes on"]
    dropped = Counter(reason for reason in reasons.values() if reason != "goes on")
    found = [f"{len(kept)} of {count(len(keywords), 'keyword')} are rising and go on to be grouped into topics."]
    if dropped:
        found.append("Dropped: " + ", ".join(f"{n} x {reason}" for reason, n in dropped.most_common()) + ".")
    rows = [
        keyword_row(row) | {"verdict": {"text": reasons[row["keyword"]], "tone": "good" if row["keyword"] in kept else "muted"}}
        for row in sorted(keywords, key=lambda row: row["keyword"] not in kept)
    ]
    columns = [KEYWORD_COLUMNS[0], column("verdict", "Verdict", "verdict"), *[c for c in KEYWORD_COLUMNS[1:] if c["key"] not in ("competition", "competition_index", "bids")]]
    return step("Rising keywords", IDEATE, what, found, [table(columns, rows, limit=25)], [verdicts_file])


def found_topics_step(run_id: str, keywords: list[dict], s: "Settings") -> dict:
    what = (
        "The LLM of the YouTube tool groups the rising keywords that are about the same video topic. It names each topic and writes the search "
        "query a viewer would type into YouTube to find it. Keywords with exactly the same search history go together as one: Google counts "
        "them as variants of each other. The LLM also marks the topics a YouTube search would say nothing about: unrelated to your seeds, too "
        f"broad to be one video, or a bare brand name. ideate.py then sends the {s['MAX_TOPICS']} topics that gained the most searches on to "
        "YouTube. That is one search per topic, not one per phrasing, and each search costs 100 of your 10,000 daily quota units."
    )
    topics_file, phrases_file = OUTPUT_DIR / f"{run_id}_topics.json", OUTPUT_DIR / f"{run_id}_phrases.txt"
    topics = read_json(topics_file)
    if topics is None:
        return missing_step("Topics", YOUTUBE, what)
    phrases = phrases_file.read_text().split("\n")[:-1] if phrases_file.exists() else []
    by_keyword = {row["keyword"]: row for row in keywords}
    rows = []
    for topic in topics:
        biggest = max((by_keyword[k] for k in topic["keywords"] if k in by_keyword), key=lambda row: number(row["avg_monthly_searches"]) or 0, default={})
        goes_on = topic["search_query"] in phrases
        verdict = "goes on to YouTube" if goes_on else f"skipped: {topic['skip']}" if topic["skip"] else f"not in the top {s['MAX_TOPICS']}"
        rows.append({
            "name": topic["name"],
            "verdict": {"text": verdict, "tone": "good" if goes_on else "muted"},
            "search_query": topic["search_query"],
            "keyword": biggest.get("keyword"),
            "avg_monthly_searches": number(biggest.get("avg_monthly_searches")),
            "gained": (number(biggest.get("last_12m_avg")) or 0) - (number(biggest.get("prior_12m_avg")) or 0),
            "keywords": topic["keywords"],
            "children": keywords_table([by_keyword[k] for k in topic["keywords"] if k in by_keyword]),
        })  # fmt: skip
    rows.sort(key=lambda row: (row["verdict"]["tone"] == "good", row["gained"]), reverse=True)
    grouped = sum(len(topic["keywords"]) for topic in topics)
    found = [f"{count(grouped, 'rising keyword')} became {count(len(topics), 'topic')}."]
    largest = max(topics, key=lambda topic: len(topic["keywords"]), default=None)
    if largest and len(largest["keywords"]) > 1:
        found.append(f"\"{largest['name']}\" alone holds {len(largest['keywords'])} phrasings. Searched one by one, they would cost {len(largest['keywords'])} YouTube searches for one idea.")
    skipped = [f"{topic['name']} ({topic['skip']})" for topic in topics if topic["skip"]]
    if skipped:
        found.append(f"Skipped: {', '.join(skipped)}.")
    found.append(f"{count(len(phrases), 'topic goes', 'topics go')} on to YouTube: {', '.join(phrases)}." if phrases else "No topic went on to YouTube.")
    found.append("Open a row to see the keywords of a topic with their trends.")
    columns = [
        column("name", "Topic"), column("verdict", "Verdict", "verdict"), column("search_query", "YouTube search"),
        column("keyword", "Biggest keyword"), column("avg_monthly_searches", "Searches / mo", "number"),
        column("gained", "Searches gained", "number"), column("keywords", "Keywords", "lines"),
    ]  # fmt: skip
    blocks = [table(columns, rows), {"type": "list", "label": "The hand-off file: one YouTube search per topic", "items": phrases}]
    return step("Topics", YOUTUBE, what, found, blocks, [topics_file, phrases_file])


def google_seeds_step(run_id: str) -> dict:
    what = (
        "Google rarely knows a YouTube phrasing: nobody types \"build and sell ai agent 6 hours course\" into Google. So for each topic of "
        "step 2, the LLM of the YouTube tool reads the phrasings that were scored on YouTube and writes 3 short seed keywords, the way people "
        "would type the topic into Google. The keyword tool starts from these in the next step."
    )
    given_file = OUTPUT_DIR / f"{run_id}_given_topics.json"
    given = read_json(given_file)
    if not given or "seeds" not in given[0]:
        return missing_step("Google seeds per topic", YOUTUBE, what)
    rows = [{"name": topic["name"], "phrasings": topic["phrasings"], "seeds": topic["seeds"]} for topic in given]
    found = [f"{count(len(given), 'topic')} got {count(sum(len(topic['seeds']) for topic in given), 'seed keyword')}."]
    columns = [column("name", "Topic"), column("phrasings", "What viewers type into YouTube", "lines"), column("seeds", "Seed keywords for Google", "lines")]
    return step("Google seeds per topic", YOUTUBE, what, found, [table(columns, rows)], [given_file])


def topic_ideas_step(run_id: str, s: "Settings") -> dict:
    what = (
        "The keyword tool asks Google Ads Keyword Planner for keyword ideas around the seeds, once per topic: in one shared request, the "
        "suggestions for one topic crowd out the rest. Every suggestion comes with 48 months of searches, and its trend is measured year over "
        "year on the quiet months: rising is a floor up 20% or more, shrinking is down 20% or more. Of each topic's suggestions, the biggest "
        f"{s['MAX_TOPIC_KEYWORDS']} with at least {s['MIN_MONTHLY_SEARCHES']} searches a month become its candidates."
    )
    given = read_json(OUTPUT_DIR / f"{run_id}_given_topics.json") or []
    files = sorted(OUTPUT_DIR.glob(f"{run_id}_topic*_keywords.csv"))
    if not files:
        return missing_step("Keyword ideas per topic", KEYWORDS, what)
    rows, found = [], []
    for number_, topic in enumerate(given, start=1):
        ideas = read_csv(OUTPUT_DIR / f"{run_id}_topic{number_}_keywords.csv")
        candidates = {row["keyword"] for row in topic.get("candidates", [])}
        rows.append({
            "name": topic["name"],
            "seeds": topic["seeds"],
            "returned": len(ideas),
            "candidates": len(candidates),
            "tool_run": f"{run_id}_topic{number_}",
            "children": keywords_table([row for row in ideas if row["keyword"] in candidates]) if candidates else None,
        })  # fmt: skip
        if not candidates:
            found.append(f"Google suggested nothing with {s['MIN_MONTHLY_SEARCHES']}+ searches a month for \"{topic['name']}\".")
    found.insert(0, f"{count(sum(row['returned'] for row in rows), 'keyword')} suggested for {count(len(rows), 'topic')}, {sum(row['candidates'] for row in rows)} of them candidates.")
    found.append("Open a row to see a topic's candidates. Each request is a run of the keyword tool, with its own checkpoints in keyword-analysis/checkpoints/.")
    columns = [
        column("name", "Topic"), column("seeds", "Seeds", "lines"), column("returned", "Suggested", "number"),
        column("candidates", "Candidates", "number"), column("tool_run", "Keyword tool run"),
    ]  # fmt: skip
    return step("Keyword ideas per topic", KEYWORDS, what, found, [table(columns, rows)], files)


def picked_keywords_step(run_id: str, keywords: list[dict]) -> dict:
    what = (
        "Google's suggestions are only loosely related to the seeds. For each topic, the LLM of the YouTube tool keeps the candidates of people "
        "who want the same thing as the viewers typing the topic's YouTube phrasings. A keyword that is broader (it would fit many other videos "
        "too) or only loosely related is left out, because one big loose keyword would decide the whole topic. Keywords with exactly the same "
        "search history go together, and a keyword two topics claim stays with the first."
    )
    topics_file = OUTPUT_DIR / f"{run_id}_topics.json"
    topics, given = read_json(topics_file), read_json(OUTPUT_DIR / f"{run_id}_given_topics.json") or []
    if topics is None:
        return missing_step("Keywords picked per topic", YOUTUBE, what)
    by_keyword = {row["keyword"]: row for row in keywords}
    candidates = {topic["name"]: len(topic.get("candidates", [])) for topic in given}
    rows = [
        {
            "name": topic["name"],
            "candidates": candidates.get(topic["name"]),
            "picked": len(topic["keywords"]),
            "keywords": topic["keywords"],
            "children": keywords_table([by_keyword[k] for k in topic["keywords"] if k in by_keyword]) if topic["keywords"] else None,
        }
        for topic in topics
    ]
    found = [f"{sum(row['picked'] for row in rows)} of {sum(row['candidates'] or 0 for row in rows)} candidates were kept."]
    empty = [topic["name"] for topic in topics if not topic["keywords"]]
    if empty:
        found.append(f"No keyword was kept for: {', '.join(empty)}. Google knows no phrasing of these topics, so their search trend stays unknown.")
    found.append("Open a row to see the keywords of a topic with their trends.")
    columns = [column("name", "Topic"), column("candidates", "Candidates", "number"), column("picked", "Kept", "number"), column("keywords", "Keywords", "lines")]
    return step("Keywords picked per topic", YOUTUBE, what, found, [table(columns, rows)], [topics_file])


def scoreboard_step(run_id: str, scored: list[dict], s: "Settings", keywords: list[dict], ideate_settings: "Settings") -> dict:
    what = (
        "ideate.py judges every topic as a whole. On YouTube, the best-scoring phrasing of the topic counts: it is repeatable with hits on "
        f"{s['MIN_HITS']}+ channels and a score of {s['MIN_SCORE']}+. On Google, the most searched keyword of the topic stands for it: it is "
        f"rising when {rising_rule(ideate_settings)}. A topic to make passes both. \"Rising keywords\" says how many of the topic's keywords "
        "are rising: when that is only a few, the verdict rests on the biggest keyword alone, so open the row and check it really is the topic."
    )
    scoreboard_file = OUTPUT_DIR / f"{run_id}_scoreboard.csv"
    if not scoreboard_file.exists():
        return missing_step("Final Results", IDEATE, what)
    by_query = {idea["search_query"]: idea for idea in scored}
    by_keyword = {row["keyword"]: row for row in keywords}
    run_time = datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").astimezone()
    rows = []
    for row in read_csv(scoreboard_file):
        idea = by_query.get(row["youtube_query"])
        topic_keywords = [by_keyword[k] for k in row["keywords"].split("; ") if k in by_keyword]
        tone = "good" if row["verdict"] == "make it" else "warn" if row["verdict"].startswith(("repeatable, but", "rising, but")) else "muted"
        children = []
        if topic_keywords:
            children.append(keywords_table(topic_keywords, "The Google keywords of this topic"))
        if idea and idea["hits"]:
            children.append(hits_table(idea, run_time) | {"label": f"The hit videos behind its repeatability (YouTube search: {row['youtube_query']})"})
        rows.append({
            "topic": row["topic"],
            "verdict": {"text": row["verdict"], "tone": tone},
            "repeatability": number(row["repeatability"]),
            "hit_channels": number(row["hit_channels"]),
            "keyword": row["keyword"],
            "monthly_searches": number(row["monthly_searches"]),
            "history": monthly(by_keyword.get(row["keyword"], {}).get("monthly_searches", "")),
            "yoy_change_pct": number(row["yoy_change_pct"]),
            "search_trend": row["search_trend"],
            "searches_gained": number(row["searches_gained"]),
            "rising_keywords": row.get("rising_keywords", ""),
            "children": children or None,
        })  # fmt: skip

    named = lambda *starts: [f"\"{row['topic']}\"" for row in rows if row["verdict"]["text"].startswith(starts)]  # noqa: E731
    found = [f"{count(len(rows), 'topic')} judged."]
    found.append(f"Make these, repeatable on YouTube and rising on Google: {', '.join(named('make it'))}." if named("make it") else "No topic is both repeatable on YouTube and rising on Google this time.")
    for starts, sentence in [
        (("repeatable, but",), "Repeatable on YouTube, but not rising on Google: {}."),
        (("rising, but",), "Rising on Google, but not repeatable on YouTube: {}."),
        (("not repeatable",), "Neither repeatable nor rising: {}."),
        (("skipped", "not searched"), "Never searched on YouTube: {}."),
    ]:
        if named(*starts):
            found.append(sentence.format(", ".join(named(*starts))))
    for row in rows:
        rising, total = (int(n) for n in (row["rising_keywords"] or "0 of 0").split(" of "))
        if row["verdict"]["text"] == "make it" and total > 2 and rising * 2 < total:
            found.append(f"Check \"{row['topic']}\": only {rising} of its {total} keywords are rising, so its verdict rests on \"{row['keyword']}\" alone.")
    found.append("Open a row to see the topic's Google keywords and the hit videos behind its repeatability.")

    columns = [
        column("topic", "Topic"), column("verdict", "Verdict", "verdict"), column("repeatability", "Repeatability", "score"),
        column("hit_channels", "Channels", "number"), column("keyword", "Biggest keyword"), column("monthly_searches", "Searches / mo", "number"),
        column("history", "Last 48 months", "spark"), column("yoy_change_pct", "YoY", "percent"), column("search_trend", "Search trend", "trend"),
        column("searches_gained", "Searches gained", "number"), column("rising_keywords", "Rising keywords"),
    ]  # fmt: skip
    result = step("Final Results", IDEATE, what, found, [table(columns, rows)], [scoreboard_file])
    winners = [name[1:-1] for name in named("make it")]
    result["headline"] = f"Make: {winners[0]}" + (f" and {len(winners) - 1} more" if len(winners) > 1 else "") if winners else "No topic both repeatable and rising"
    return result


# --- Building blocks ---

VIDEO_COLUMNS = [
    {"key": "video", "label": "Video", "kind": "video"},
    {"key": "channel", "label": "Channel", "kind": "channel"},
    {"key": "views", "label": "Views", "kind": "number"},
    {"key": "channel_median", "label": "Channel median", "kind": "number"},
    {"key": "age_days", "label": "Published", "kind": "age"},
]
KEYWORD_COLUMNS = [
    {"key": "keyword", "label": "Keyword", "kind": "text"},
    {"key": "avg_monthly_searches", "label": "Searches / mo", "kind": "number"},
    {"key": "history", "label": "Last 48 months", "kind": "spark"},
    {"key": "yoy_change_pct", "label": "YoY", "kind": "percent"},
    {"key": "floor_change_pct", "label": "Floor", "kind": "percent"},
    {"key": "floor_trend", "label": "Search trend", "kind": "trend"},
    {"key": "competition", "label": "Competition", "kind": "text"},
    {"key": "competition_index", "label": "Index", "kind": "number"},
    {"key": "bids", "label": "Top of page bid", "kind": "text"},
]


class Settings(dict):
    """A tool's settings. A setting the run did not record reads as "?" in the commentary."""

    def __missing__(self, name):
        return "?"


def step(title: str, tool: str, what: str, found: list[str], blocks: list[dict], files: list) -> dict:
    return {
        "title": title,
        "tool": tool,
        "status": "done",
        "what": what,
        "found": found,
        "blocks": [block for block in blocks if block.get("text", True)],  # no empty logs
        "files": [str(path.relative_to(HERE)) for path in files if path and path.exists()],
    }


def missing_step(title: str, tool: str, what: str, failure: list[str] | None = None) -> dict:
    found = ["No checkpoint for this step: the run stopped before it, or is still going."]
    blocks = [{"type": "log", "label": "The failure in the tool's log", "text": "\n".join(failure)}] if failure else []
    return {"title": title, "tool": tool, "status": "missing", "what": what, "found": found, "blocks": blocks, "files": []}


def table(columns: list[dict], rows: list[dict], limit: int | None = None) -> dict:
    return {"type": "table", "columns": columns, "rows": rows, "limit": limit}


def column(key: str, label: str, kind: str = "text") -> dict:
    return {"key": key, "label": label, "kind": kind}


def count(n: int, singular: str, plural: str | None = None) -> str:
    return f"{n} {singular if n == 1 else plural or singular + 's'}"


def number(text):
    """CSV cells are text: '' -> None, '12' -> 12, '3.5' -> 3.5."""
    if text in ("", None):
        return None
    value = float(text)
    return int(value) if value.is_integer() else value


def read_json(path: Path | None):
    return json.loads(path.read_text()) if path and path.exists() else None


def read_csv(path: Path | None) -> list[dict]:
    if not path or not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    runs = build()
    print(f"{len(runs)} runs collected in {VIEWER_DIR.relative_to(HERE)}/")
    print(f"View them: {(HERE / 'index.html').as_uri()}")
