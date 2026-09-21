"""Collects every run in runs/ into runs/viewer/ for viewer/index.html to display.

    uv run python -m viewer.build_viewer

The pipelines do this after every run. Browsers don't let a page opened from disk read JSON files,
so the data is written as .js files that index.html loads with <script> tags: runs.js lists the
runs and <run id>.js holds the steps of one run.

A run in the viewer is the pipeline's steps, one to one. Every step has a commentary (`what` the
step does, and what it `found` in this run) and blocks of data taken from the step's file.
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
VIEWER_DIR = RUNS_DIR / "viewer"

YOUTUBE, GOOGLE, LLM, RULE = "YouTube", "Google", "LLM", "Rule"  # where a step gets its answer from
GEO_NAMES = {"2840": "United States"}
LANGUAGE_NAMES = {"1000": "English"}
MAKE_IT, GOES_ON = "make it", "goes on"


def build(open_run: str | None = None) -> list[dict]:
    """Write the data files for every run found on disk."""
    VIEWER_DIR.mkdir(parents=True, exist_ok=True)
    runs = [read_run(folder) for folder in sorted(RUNS_DIR.glob("*/run.json"), reverse=True)]
    for run in runs:
        text = json.dumps(run, ensure_ascii=False)
        (VIEWER_DIR / f"{run['id']}.js").write_text(f"window.RUN_DATA = window.RUN_DATA || {{}};\nwindow.RUN_DATA[{json.dumps(run['id'])}] = {text};\n")
    summaries = [{key: value for key, value in run.items() if key != "steps"} | {"step_count": len(run["steps"])} for run in runs]
    (VIEWER_DIR / "runs.js").write_text(f"window.RUNS = {json.dumps(summaries, ensure_ascii=False)};\n")
    if open_run:
        print(f"\nInspect every step: {(ROOT / 'viewer' / 'index.html').as_uri()}#{open_run}")
    return runs


def read_run(info_file: Path) -> dict:
    info = json.loads(info_file.read_text())
    s = Settings(info["settings"])
    outputs = Outputs(info_file.parent)
    if info["pipeline"] == "from-keywords":
        steps = [keyword_ideas_step, search_trends_step, rising_keywords_step, group_into_topics_step, choose_topics_step, repeatability_step, scoreboard_step]
        subtitle = "Seeds: " + ", ".join(info["seeds"])
    else:
        steps = [outliers_step, outlier_topics_step, query_variants_step, repeatability_step, google_seeds_step, topic_keyword_ideas_step, picked_keywords_step, scoreboard_step]
        subtitle = "From the scanned channels' outlier videos"
    steps = [make_step(outputs, s) for make_step in steps]
    return {
        "id": info["run"],
        "direction": info["pipeline"],
        "started_at": datetime.strptime(info["run"], "%Y%m%d-%H%M%S").isoformat(),
        "subtitle": subtitle,
        "headline": steps[-1].get("headline", ""),
        "stopped_at": next((number for number, step in enumerate(steps, start=1) if step["status"] == "missing"), None),  # None when every step has its data
        "steps": steps,
    }


class Outputs:
    """The step files of one run: outputs.get("search_trends") is that step's output, or None if the run did not get there."""

    def __init__(self, folder: Path):
        self.folder = folder

    def file(self, name: str) -> Path | None:
        return next(iter(self.folder.glob(f"*_{name}.json")), None)

    def get(self, name: str, part: str = "output"):
        path = self.file(name)
        return json.loads(path.read_text()).get(part) if path else None


class Settings(dict):
    """The settings the run used. A setting the run did not record reads as "?" in the commentary."""

    def __missing__(self, name):
        return "?"


# --- Pipeline 2, from keywords ---


def keyword_ideas_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        "The seed keywords are sent to Google Ads Keyword Planner (GenerateKeywordIdeas), which answers with the related keywords people "
        "search for on Google, each with its search volume month by month for the last 48 months. Keyword Planner rounds volumes into "
        "buckets (10, 20, ... 49,500, 60,500 ...), so these are magnitudes, not exact counts."
    )
    rows = outputs.get("keyword_ideas")
    if rows is None:
        return missing_step("Keyword ideas", GOOGLE, what)
    facts = [
        ["Seed keywords", ", ".join(outputs.get("keyword_ideas", "input"))],
        ["Location", ", ".join(GEO_NAMES.get(geo, geo) for geo in s["GEO_IDS"])],
        ["Language", LANGUAGE_NAMES.get(s["LANGUAGE_ID"], s["LANGUAGE_ID"])],
    ]
    found = [f"{count(len(rows), 'keyword')} returned, {sum(1 for row in rows if not row['avg_monthly_searches'])} with no search volume."]
    by_seed = outputs.get("seeds_to_keywords", "summary")  # the short version of this step, saved by runs since the a/b files
    if by_seed:
        parts = [f"{number:,} {label}" for label, number in by_seed.items() if label not in ("seed keywords", "keywords found")]
        found.append("Which seed brought them in: " + "; ".join(parts) + ". A seed with few keywords of its own was crowded out by the others.")
    columns = [c for c in KEYWORD_COLUMNS if c["key"] in ("keyword", "avg_monthly_searches", "history", "competition", "competition_index", "bids")]
    ordered = sorted(rows, key=lambda row: row["avg_monthly_searches"], reverse=True)
    return step("Keyword ideas", GOOGLE, what, found, [{"type": "facts", "facts": facts}, table(columns, [keyword_row(row) for row in ordered], limit=25)], outputs.file("keyword_ideas"))


def search_trends_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        "Search demand is seasonal, so every comparison is year over year: the last 12 months against the 12 before. The trend comes "
        "from the floor, the mean of the 3 quietest months of a window: the demand that is there even in the slow season. "
        "Rising is a floor up 20% or more, shrinking is down 20% or more, flat is in between (a smaller change can be a single "
        "rounding bucket), and new means there was no floor a year ago. The keywords are then sorted by search volume."
    )
    rows = outputs.get("search_trends")
    if rows is None:
        return missing_step("Search trends", RULE, what)
    trends = Counter(row["trend"] for row in rows)
    found = ["Trends: " + ", ".join(f"{n} {trend}" for trend, n in sorted(trends.items())) + "."]
    rising = [row for row in rows if row["trend"] == "rising"]
    if rising:
        found.append(f"The biggest rising keyword is \"{rising[0]['keyword']}\" with {rising[0]['avg_monthly_searches']:,} searches a month.")
    return step("Search trends", RULE, what, found, [keywords_table(rows, limit=25, full=True)], outputs.file("search_trends"))


def rising_keywords_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        f"The pipeline keeps the keywords that are rising. A keyword is rising when {rising_rule(s)}. At most {s['MAX_GROUPED_KEYWORDS']} "
        "go on to the next step, the biggest first. The others stay out: a topic built on them would not be rising either."
    )
    rows = outputs.get("rising_keywords")
    if rows is None:
        return missing_step("Rising keywords", RULE, what)
    kept = [row for row in rows if row["verdict"] == GOES_ON]
    dropped = Counter(row["verdict"] for row in rows if row["verdict"] != GOES_ON)
    found = [f"{len(kept)} of {count(len(rows), 'keyword')} are rising and go on to be grouped into topics."]
    if dropped:
        found.append("Dropped: " + ", ".join(f"{n} x {reason}" for reason, n in dropped.most_common()) + ".")
    ordered = sorted(rows, key=lambda row: row["verdict"] != GOES_ON)
    table_rows = [keyword_row(row) | {"verdict": {"text": row["verdict"], "tone": "good" if row["verdict"] == GOES_ON else "muted"}} for row in ordered]
    columns = [KEYWORD_COLUMNS[0], column("verdict", "Verdict", "verdict"), *[c for c in KEYWORD_COLUMNS[1:] if c["key"] not in ADVERTISER_COLUMNS]]
    return step("Rising keywords", RULE, what, found, [table(columns, table_rows, limit=25)], outputs.file("rising_keywords"))


def group_into_topics_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        "An LLM groups the rising keywords that are about the same video topic. It names each topic and writes the search query a viewer "
        "would type into YouTube to find it. Keywords with exactly the same search history go together as one: Google counts them as "
        "variants of each other. The LLM also marks the topics a YouTube search would say nothing about: unrelated to your seeds, too "
        "broad to be one video, or a bare brand name. It may only use the keywords it was given: an invented keyword is thrown away."
    )
    topics = outputs.get("group_into_topics")
    if topics is None:
        return missing_step("Topics", LLM, what)
    found = [f"{count(sum(len(topic['keywords']) for topic in topics), 'rising keyword')} became {count(len(topics), 'topic')}."]
    largest = max(topics, key=lambda topic: len(topic["keywords"]), default=None)
    if largest and len(largest["keywords"]) > 1:
        found.append(f"\"{largest['name']}\" alone holds {len(largest['keywords'])} phrasings. Searched one by one, they would cost {len(largest['keywords'])} YouTube searches for one idea.")
    skipped = [f"{topic['name']} ({topic['skip']})" for topic in topics if topic["skip"]]
    if skipped:
        found.append(f"Marked to skip: {', '.join(skipped)}.")
    rows = [{"name": t["name"], "search_query": t["search_query"], "skip": t["skip"], "keywords": t["keywords"]} for t in topics]
    columns = [column("name", "Topic"), column("search_query", "YouTube search"), column("skip", "Skip?"), column("keywords", "Keywords", "lines")]
    return step("Topics", LLM, what, found, [table(columns, rows)], outputs.file("group_into_topics"))


def choose_topics_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        f"A YouTube search costs 100 of your 10,000 daily quota units, so at most {s['MAX_TOPICS']} topics go on to YouTube: the ones whose "
        "most searched keyword gained the most searches on the year before, which favours topics that are both big and growing. "
        "That is one search per topic, not one per phrasing. Topics the LLM marked to skip never go on."
    )
    topics, keywords = outputs.get("choose_topics"), outputs.get("search_trends") or []
    if topics is None:
        return missing_step("Topics worth a search", RULE, what)
    by_keyword = {row["keyword"]: row for row in keywords}
    rows = []
    for topic in topics:
        verdict = "goes on to YouTube" if topic["goes_on"] else f"skipped: {topic['skip']}" if topic["skip"] else f"not in the top {s['MAX_TOPICS']}"
        rows.append({
            "name": topic["name"],
            "verdict": {"text": verdict, "tone": "good" if topic["goes_on"] else "muted"},
            "search_query": topic["search_query"],
            "keyword": topic["biggest_keyword"],
            "avg_monthly_searches": by_keyword.get(topic["biggest_keyword"], {}).get("avg_monthly_searches"),
            "gained": topic["searches_gained"],
            "children": keywords_table([by_keyword[k] for k in topic["keywords"] if k in by_keyword]),
        })  # fmt: skip
    going = [topic["search_query"] for topic in topics if topic["goes_on"]]
    found = [f"{count(len(going), 'topic goes', 'topics go')} on to YouTube: {', '.join(going)}." if going else "No topic went on to YouTube."]
    found.append("Open a row to see the keywords of a topic with their trends.")
    columns = [
        column("name", "Topic"), column("verdict", "Verdict", "verdict"), column("search_query", "YouTube search"),
        column("keyword", "Biggest keyword"), column("avg_monthly_searches", "Searches / mo", "number"), column("gained", "Searches gained", "number"),
    ]  # fmt: skip
    return step("Topics worth a search", RULE, what, found, [table(columns, rows)], outputs.file("choose_topics"))


# --- Pipeline 1, from YouTube ---


def outliers_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        f"Every channel in CHANNELS_TO_SCAN is scanned. A channel's median is taken over its last {s['UPLOADS_FOR_MEDIAN']} "
        f"{s['FORMAT']} uploads, and an upload with at least {s['OUTLIER_MULTIPLE']}x that median is an outlier: a video that "
        f"did far better than the channel normally does. The {s['TOP_CANDIDATES']} biggest outliers go on to the next step."
    )
    outliers = outputs.get("find_outliers")
    if outliers is None:
        return missing_step("Outlier videos", YOUTUBE, what)
    found = [f"{count(len(outliers), 'outlier')} from {count(len({o['channel_id'] for o in outliers}), 'channel')}."]
    if outliers:
        best, last = outliers[0], outliers[-1]
        found.append(f"The biggest is \"{best['title']}\" by {best['channel']}: {best['views']:,} views, {best['multiple']:.0f}x the channel's median of {best['channel_median']:,.0f}.")
        found.append(f"The smallest multiple that made the cut is {last['multiple']:.1f}x.")
        busiest, videos = Counter(o["channel"] for o in outliers).most_common(1)[0]
        if videos > 1:
            found.append(f"{busiest} alone has {videos} of them, so its subjects weigh heavily on the topics of the next step.")
    columns = [column("multiple", "Multiple", "multiple"), *VIDEO_COLUMNS]
    return step("Outlier videos", YOUTUBE, what, found, [table(columns, [video_row(o) for o in outliers])], outputs.file("find_outliers"))


def outlier_topics_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        f"An LLM ({s['LLM_PROVIDER']}) groups the outliers that are about the same subject into one topic, and writes for each "
        "topic the search query a viewer would type into YouTube to find such videos. Queries are kept short and generic: "
        "no channel names, no clickbait."
    )
    topics, outliers = outputs.get("outliers_to_topics"), outputs.get("find_outliers") or []
    if topics is None:
        return missing_step("Topics", LLM, what)
    titles = {o["video_id"]: o["title"] for o in outliers}
    found = [f"{count(len(titles), 'outlier')} became {count(len(topics), 'topic')}."]
    merged = [topic["name"] for topic in topics if len(topic["video_ids"]) > 1]
    if merged:
        found.append(f"{count(len(merged), 'topic')} merged more than one video: {', '.join(merged)}.")
    unused = [title for video_id, title in titles.items() if not any(video_id in topic["video_ids"] for topic in topics)]
    if unused:
        found.append(f"The LLM left {count(len(unused), 'outlier')} out of every topic: " + "; ".join(unused) + ".")
    rows = [{"name": t["name"], "search_query": t["search_query"], "videos": [titles.get(v, v) for v in t["video_ids"]]} for t in topics]
    columns = [column("name", "Topic"), column("search_query", "Search query"), column("videos", "Outliers it came from", "lines")]
    return step("Topics", LLM, what, found, [table(columns, rows)], outputs.file("outliers_to_topics"))


def query_variants_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        "Each topic's query is sent to YouTube's search autocomplete, which answers with the phrasings viewers really type, most popular "
        f"first. It costs no API quota. An LLM picks up to {s['QUERY_VARIANTS']} of them per topic: same language, still on topic, a distinct "
        "angle. A pick that is not in YouTube's list is thrown away. Every query is scored in the next step as an idea of its own."
    )
    queries, topics = outputs.get("query_variants"), outputs.get("outliers_to_topics") or []
    if queries is None:
        return missing_step("Search queries", YOUTUBE, what)
    own = {topic["search_query"] for topic in topics}
    found = [f"{count(len(queries), 'search query', 'search queries')} to score: {len(own & {q['search_query'] for q in queries})} written by the LLM, {sum(q['search_query'] not in own for q in queries)} picked from autocomplete."]
    suggested = {t["name"]: t["suggestions"] for t in outputs.get("youtube_suggestions") or []}  # part a of the step, saved by runs since the a/b files
    rows = [{"name": t["name"], "suggestions": suggested.get(t["name"], []), "queries": [q["search_query"] for q in queries if q["topic"] == t["name"]]} for t in topics]
    columns = [column("name", "Topic"), column("suggestions", "a. YouTube suggests", "lines"), column("queries", "b. Search queries to score", "lines")]
    if suggested:
        found.insert(0, f"YouTube suggested {count(sum(map(len, suggested.values())), 'phrasing')} for the {count(len(suggested), 'topic')}.")
    else:
        columns.pop(1)
    return step("Search queries", YOUTUBE, what, found, [table(columns, rows)], outputs.file("query_variants"))


def google_seeds_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        "Google rarely knows a YouTube phrasing: nobody types \"build and sell ai agent 6 hours course\" into Google. So for each topic, "
        "an LLM reads the phrasings that were scored on YouTube and writes 3 short seed keywords, the way people would type the topic "
        "into Google. Keyword Planner starts from these in the next step."
    )
    topics = outputs.get("google_seeds")
    if topics is None:
        return missing_step("Google seeds per topic", LLM, what)
    found = [f"{count(len(topics), 'topic')} got {count(sum(len(topic['seeds']) for topic in topics), 'seed keyword')}."]
    columns = [column("name", "Topic"), column("phrasings", "What viewers type into YouTube", "lines"), column("seeds", "Seed keywords for Google", "lines")]
    return step("Google seeds per topic", LLM, what, found, [table(columns, topics)], outputs.file("google_seeds"))


def topic_keyword_ideas_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        "Google Ads Keyword Planner is asked for keyword ideas around the seeds, once per topic: in one shared request, the suggestions for "
        "one topic crowd out the rest. Every suggestion comes with 48 months of searches, and its trend is measured year over year on the "
        f"quiet months: rising is a floor up 20% or more, shrinking is down 20% or more. Of each topic's suggestions, the biggest "
        f"{s['MAX_TOPIC_KEYWORDS']} with at least {s['MIN_MONTHLY_SEARCHES']} searches a month go on as its candidates."
    )
    candidates, topics = outputs.get("keyword_ideas_per_topic"), outputs.get("google_seeds") or []
    if candidates is None:
        return missing_step("Keyword ideas per topic", GOOGLE, what)
    rows = []
    for topic in topics:
        mine = candidates.get(topic["name"], [])
        rows.append({"name": topic["name"], "seeds": topic["seeds"], "candidates": len(mine), "children": keywords_table(mine) if mine else None})
    found = [f"{count(sum(row['candidates'] for row in rows), 'candidate')} for {count(len(rows), 'topic')}."]
    found += [f"Google suggested nothing with {s['MIN_MONTHLY_SEARCHES']}+ searches a month for \"{row['name']}\"." for row in rows if not row["candidates"]]
    found.append("Open a row to see a topic's candidates.")
    columns = [column("name", "Topic"), column("seeds", "Seeds", "lines"), column("candidates", "Candidates", "number")]
    return step("Keyword ideas per topic", GOOGLE, what, found, [table(columns, rows)], outputs.file("keyword_ideas_per_topic"))


def picked_keywords_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        "Google's suggestions are only loosely related to the seeds. For each topic, an LLM keeps the keywords of people who want the same "
        f"thing as the viewers typing the topic's YouTube phrasings. It judges at most {s['MAX_TOPIC_KEYWORDS']} candidates per topic, the "
        "biggest. A keyword that is broader (it would fit many other videos too) or only loosely related is left out, because one big "
        "loose keyword would decide the whole topic. Keywords with exactly the same search history go together, and a keyword two "
        "topics claim stays with the first."
    )
    topics = outputs.get("pick_topic_keywords")
    if topics is None:
        return missing_step("Keywords picked per topic", LLM, what)
    by_keyword = {row["keyword"]: row for rows in (outputs.get("keyword_ideas_per_topic") or {}).values() for row in rows}
    rows = [
        {
            "name": topic["name"],
            "candidates": topic["candidates"],
            "picked": len(topic["keywords"]),
            "keywords": topic["keywords"],
            "children": keywords_table([by_keyword[k] for k in topic["keywords"] if k in by_keyword]) if topic["keywords"] else None,
        }
        for topic in topics
    ]
    found = [f"{sum(row['picked'] for row in rows)} of {sum(row['candidates'] for row in rows)} candidates were kept."]
    empty = [topic["name"] for topic in topics if not topic["keywords"]]
    if empty:
        found.append(f"No keyword was kept for: {', '.join(empty)}. Google knows no phrasing of these topics, so their search trend stays unknown.")
    found.append("Open a row to see the keywords of a topic with their trends.")
    columns = [column("name", "Topic"), column("candidates", "Candidates", "number"), column("picked", "Kept", "number"), column("keywords", "Keywords", "lines")]
    return step("Keywords picked per topic", LLM, what, found, [table(columns, rows)], outputs.file("pick_topic_keywords"))


# --- Both pipelines ---


def repeatability_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        f"Each query is searched on YouTube ({s['SEARCH_RESULTS_PER_QUERY']} results). Results in the wrong format, older than "
        f"{s['MAX_HIT_AGE_DAYS']} days or under {s['MIN_HIT_VIEWS']} views are dropped, and the first {s['CHANNELS_PER_QUERY']} "
        f"different channels are kept. A result is a hit when it has at least {s['HIT_MULTIPLE']}x its own channel's median views. "
        f"A hit weighs more when it is recent (the weight halves every {s['AGE_HALF_LIFE_DAYS']} days) and when the channel is "
        "close to yours in size. The repeatability score is the sum of the weights: 1.0 is one brand-new hit from a channel your size."
    )
    scored = outputs.get("score_repeatability")
    if scored is None:
        return missing_step("Repeatability scores", YOUTUBE, what)
    found = [f"{count(len(scored), 'search query', 'search queries')} scored."]
    if scored:
        best = scored[0]
        found.append(f"The best is \"{best['search_query']}\" with {best['score']:.2f}: {count(len(best['hits']), 'hit')} on {count(best['hit_channels'], 'channel')}.")
        passing = [idea for idea in scored if is_repeatable(idea, s)]
        found.append(f"{len(passing)} of {len(scored)} pass the bar for repeatable (hits on {s['MIN_HITS']}+ channels and a score of {s['MIN_SCORE']}+).")
        hitless = [idea["search_query"] for idea in scored if not idea["hits"]]
        if hitless:
            found.append(f"No hits at all for: {', '.join(hitless)}.")
    found.append("Open a row to see the hit videos behind its score.")
    rows = [
        {
            "score": idea["score"],
            "search_query": idea["search_query"],
            "topic": idea["topic"],
            "hits": len(idea["hits"]),
            "hit_channels": idea["hit_channels"],
            "verdict": {"text": "repeatable", "tone": "good"} if is_repeatable(idea, s) else {"text": "not repeatable", "tone": "muted"},
            "children": hits_table(idea),
        }
        for idea in scored
    ]
    columns = [
        column("score", "Repeatability", "score"), column("search_query", "Search query"), column("topic", "Topic"),
        column("hits", "Hits", "number"), column("hit_channels", "Channels", "number"), column("verdict", "Repeatable?", "verdict"),
    ]  # fmt: skip
    return step("Repeatability scores", YOUTUBE, what, found, [table(columns, rows)], outputs.file("score_repeatability"))


def scoreboard_step(outputs: Outputs, s: Settings) -> dict:
    what = (
        "Every topic is judged as a whole. On YouTube, the best-scoring phrasing of the topic counts: it is repeatable with hits on "
        f"{s['MIN_HITS']}+ channels and a score of {s['MIN_SCORE']}+. On Google, the most searched keyword of the topic stands for it: it is "
        f"rising when {rising_rule(s)}. A topic to make passes both. \"Rising keywords\" says how many of the topic's keywords "
        "are rising: when that is only a few, the verdict rests on the biggest keyword alone, so open the row and check it really is the topic."
    )
    scoreboard = outputs.get("scoreboard")
    if scoreboard is None:
        return missing_step("Final Results", RULE, what)
    by_query = {idea["search_query"]: idea for idea in outputs.get("score_repeatability") or []}
    keywords = outputs.get("search_trends") or [row for rows in (outputs.get("keyword_ideas_per_topic") or {}).values() for row in rows]
    by_keyword = {row["keyword"]: row for row in keywords}
    rows = []
    for row in scoreboard:
        idea = by_query.get(row["youtube_query"])
        topic_keywords = [by_keyword[k] for k in row["keywords"] if k in by_keyword]
        tone = "good" if row["verdict"] == MAKE_IT else "warn" if row["verdict"].startswith(("repeatable, but", "rising, but")) else "muted"
        children = []
        if topic_keywords:
            children.append(keywords_table(topic_keywords, "The Google keywords of this topic"))
        if idea and idea["hits"]:
            children.append(hits_table(idea) | {"label": f"The hit videos behind its repeatability (YouTube search: {row['youtube_query']})"})
        history = by_keyword.get(row["keyword"], {}).get("monthly_searches")
        rows.append(row | {"verdict": {"text": row["verdict"], "tone": tone}, "history": monthly(history) if history else None, "children": children or None})

    named = lambda *starts: [f"\"{row['topic']}\"" for row in rows if row["verdict"]["text"].startswith(starts)]  # noqa: E731
    found = [f"{count(len(rows), 'topic')} judged."]
    found.append(f"Make these, repeatable on YouTube and rising on Google: {', '.join(named(MAKE_IT))}." if named(MAKE_IT) else "No topic is both repeatable on YouTube and rising on Google this time.")
    for starts, sentence in [
        (("repeatable, but",), "Repeatable on YouTube, but not rising on Google: {}."),
        (("rising, but",), "Rising on Google, but not repeatable on YouTube: {}."),
        (("not repeatable",), "Neither repeatable nor rising: {}."),
        (("skipped", "not searched"), "Never searched on YouTube: {}."),
    ]:
        if named(*starts):
            found.append(sentence.format(", ".join(named(*starts))))
    for row in rows:
        rising, total = (int(n) for n in row["rising_keywords"].split(" of "))
        if row["verdict"]["text"] == MAKE_IT and total > 2 and rising * 2 < total:
            found.append(f"Check \"{row['topic']}\": only {rising} of its {total} keywords are rising, so its verdict rests on \"{row['keyword']}\" alone.")
    found.append("Open a row to see the topic's Google keywords and the hit videos behind its repeatability.")

    columns = [
        column("topic", "Topic"), column("verdict", "Verdict", "verdict"), column("repeatability", "Repeatability", "score"),
        column("hit_channels", "Channels", "number"), column("keyword", "Biggest keyword"), column("monthly_searches", "Searches / mo", "number"),
        column("history", "Last 48 months", "spark"), column("yoy_change_pct", "YoY", "percent"), column("search_trend", "Search trend", "trend"),
        column("searches_gained", "Searches gained", "number"), column("rising_keywords", "Rising keywords"),
    ]  # fmt: skip
    result = step("Final Results", RULE, what, found, [table(columns, rows)], outputs.folder / "scoreboard.csv")
    winners = [name[1:-1] for name in named(MAKE_IT)]
    result["headline"] = f"Make: {winners[0]}" + (f" and {len(winners) - 1} more" if len(winners) > 1 else "") if winners else "No topic both repeatable and rising"
    return result


def rising_rule(s: Settings) -> str:
    return (
        f"its trend is {' or '.join(s.get('KEEP_TRENDS', []))} (measured on the quiet months of the year), it has at least "
        f"{s['MIN_MONTHLY_SEARCHES']} searches a month, and its searches over the whole year are not down {abs(s.get('YOY_FALLING_PCT', 0))}% or more: "
        "a rising floor under a falling year is a keyword past its peak"
    )


def is_repeatable(idea: dict, s: Settings) -> bool:
    return idea["hit_channels"] >= s.get("MIN_HITS", 0) and idea["score"] >= s.get("MIN_SCORE", 0)


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
    {"key": "trend", "label": "Search trend", "kind": "trend"},
    {"key": "competition", "label": "Competition", "kind": "text"},
    {"key": "competition_index", "label": "Index", "kind": "number"},
    {"key": "bids", "label": "Top of page bid", "kind": "text"},
]
ADVERTISER_COLUMNS = ("competition", "competition_index", "bids")  # what advertisers pay: only shown where the keywords come in


def step(title: str, source: str, what: str, found: list[str], blocks: list[dict], file: Path | None) -> dict:
    files = [str(file.relative_to(ROOT))] if file and file.exists() else []
    return {"title": title, "tool": source, "status": "done", "what": what, "found": found, "blocks": blocks, "files": files}


def missing_step(title: str, source: str, what: str) -> dict:
    found = ["No file for this step: the run stopped before it, or is still going."]
    return {"title": title, "tool": source, "status": "missing", "what": what, "found": found, "blocks": [], "files": []}


def table(columns: list[dict], rows: list[dict], limit: int | None = None) -> dict:
    return {"type": "table", "columns": columns, "rows": rows, "limit": limit}


def column(key: str, label: str, kind: str = "text") -> dict:
    return {"key": key, "label": label, "kind": kind}


def keywords_table(rows: list[dict], label: str = "", limit: int | None = None, full: bool = False) -> dict:
    columns = [c for c in KEYWORD_COLUMNS if full or c["key"] not in ADVERTISER_COLUMNS]
    return table(columns, [keyword_row(row) for row in rows], limit=limit) | {"label": label}


def keyword_row(row: dict) -> dict:
    low, high = row.get("low_top_of_page_bid"), row.get("high_top_of_page_bid")
    return {
        "keyword": row["keyword"],
        "avg_monthly_searches": row["avg_monthly_searches"],
        "history": monthly(row["monthly_searches"]),
        "yoy_change_pct": row.get("yoy_change_pct"),
        "floor_change_pct": row.get("floor_change_pct"),
        "trend": row.get("trend", ""),
        "competition": (row.get("competition") or "").lower(),
        "competition_index": row.get("competition_index"),
        "bids": f"${low:.2f} - ${high:.2f}" if low is not None and high is not None else "",
    }


def monthly(searches: dict[str, int]) -> dict | None:
    """{"2026-07": 2900, "2026-08": 2400} -> {"start": "2026-07", "values": [2900, 2400]}"""
    months = sorted(searches)
    return {"start": months[0], "values": [searches[month] for month in months]} if months else None


def hits_table(idea: dict) -> dict:
    return table([column("weight", "Weight", "score"), column("multiple", "Multiple", "multiple"), *VIDEO_COLUMNS], [video_row(hit) for hit in idea["hits"]])


def video_row(video: dict) -> dict:
    return video | {"video": {"id": video["video_id"], "title": video["title"]}, "channel": {"id": video["channel_id"], "title": video["channel"]}}


def count(n: int, singular: str, plural: str | None = None) -> str:
    return f"{n} {singular if n == 1 else plural or singular + 's'}"


if __name__ == "__main__":
    runs = build()
    print(f"{len(runs)} runs collected in {VIEWER_DIR.relative_to(ROOT)}/")
    print(f"View them: {(ROOT / 'viewer' / 'index.html').as_uri()}")
