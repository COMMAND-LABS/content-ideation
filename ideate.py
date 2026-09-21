"""Content ideation: find the video topics that are repeatable on YouTube AND rising in Google search.

    python3 ideate.py "ai agents" "claude code"     start from search: what are people looking for around these seeds?
    python3 ideate.py                               start from YouTube: what is working for the channels in config.py?

It runs the two research tools back to back, in either direction. A topic has many phrasings, and
YouTube and Google know it under different ones, so an LLM puts the phrasings of a topic together
and the topic is judged as a whole. Both directions end with the same scoreboard of topics, the
ones to make first.

Both tools save their checkpoints under this run's ID, and everything the tools hand each other
lands in output/<run>_*: open index.html to follow a run step by step.
"""

import argparse
import csv
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

try:
    from config import KEEP_TRENDS, MAX_GROUPED_KEYWORDS, MAX_TOPIC_KEYWORDS, MAX_TOPICS, MIN_MONTHLY_SEARCHES, YOY_FALLING_PCT
except ModuleNotFoundError:
    raise SystemExit("No config.py yet. Run `cp config.py.example config.py`, then set your channel in it.")

import run_viewer

HERE = Path(__file__).resolve().parent
REPEATABILITY_TOOL = HERE / "repeatability-analysis"
KEYWORD_TOOL = HERE / "keyword-analysis"
OUTPUT_DIR = HERE / "output"

SCOREBOARD_COLUMNS = [
    "topic", "verdict", "youtube_query", "repeatability", "hit_channels",
    "keyword", "monthly_searches", "yoy_change_pct", "search_trend", "searches_gained", "rising_keywords", "keywords",
]  # fmt: skip


def topics_from_keywords(run: str, seeds: list[str]):
    print("\n=== 1 of 3: what do people search for more and more? ===\n", flush=True)
    keywords = search_volume(run, ["ideas", *seeds])  # sorted by search volume, biggest first
    verdicts = {row["keyword"]: why_not_rising(row) or "goes on" for row in keywords}
    rising = [row for row in keywords if verdicts[row["keyword"]] == "goes on"]
    for row in rising[MAX_GROUPED_KEYWORDS:]:
        verdicts[row["keyword"]] = "not among the biggest"
    rising = rising[:MAX_GROUPED_KEYWORDS]
    (OUTPUT_DIR / f"{run}_keyword_verdicts.json").write_text(json.dumps(verdicts, indent=2, ensure_ascii=False))  # for the run viewer
    if not rising:
        raise SystemExit(f"None of the {len(keywords)} keywords is rising with {MIN_MONTHLY_SEARCHES}+ searches a month. Try other seeds.")
    print(f"\n{len(rising)} of {len(keywords)} keywords are rising", flush=True)

    print("\n=== 2 of 3: which topics are they about? ===\n", flush=True)
    topics = group_keywords(run, rising, seeds)
    by_keyword = {row["keyword"]: row for row in keywords}
    worth_a_search = [topic for topic in topics if not topic["skip"]]
    worth_a_search.sort(key=lambda topic: searches_gained(biggest_keyword(topic, by_keyword)), reverse=True)
    if not worth_a_search:
        raise SystemExit("The rising keywords are all too broad or brand names. Try more specific seeds.")

    print("\n=== 3 of 3: is it repeatable on YouTube? ===\n", flush=True)
    queries = [topic["search_query"].strip() for topic in worth_a_search[:MAX_TOPICS]]  # one YouTube search per topic, not per phrasing
    results = score_repeatability(run, write_phrases(run, queries))

    save_scoreboard(run, topics, keywords, results)


def topics_from_youtube(run: str):
    print("\n=== 1 of 3: what is repeatable on YouTube? ===\n", flush=True)
    results = score_repeatability(run)
    found_topics = json.loads((REPEATABILITY_TOOL / "checkpoints" / f"{run}_step_2.json").read_text())

    print("\n=== 2 of 3: what do people search for around each topic? ===\n", flush=True)
    # Google rarely knows a YouTube phrasing ("build and sell ai agent 6 hours course"): the LLM writes short seed keywords for each topic.
    given = [
        {
            "name": topic["name"],
            "search_query": topic["search_query"],
            "phrasings": [query["search_query"] for query in results["queries_scored"] if query["topic"] == topic["name"]] or [topic["search_query"]],
        }
        for topic in found_topics
    ]
    given_file = OUTPUT_DIR / f"{run}_given_topics.json"
    given_file.write_text(json.dumps(given, indent=2, ensure_ascii=False))
    run_tool(REPEATABILITY_TOOL, ["keyword_topics.py", "--google-seeds", str(given_file), "--out", str(given_file)])
    given = json.loads(given_file.read_text())

    keywords = {}
    for number, topic in enumerate(given, start=1):
        # One request per topic: in a shared request, one topic's suggestions crowd out the rest.
        print(f"\n--- {topic['name']}: {', '.join(topic['seeds'])} ---\n", flush=True)
        ideas = search_volume(f"{run}_topic{number}", ["ideas", *topic["seeds"]])
        topic["candidates"] = [as_candidate(row) for row in ideas if int(row["avg_monthly_searches"]) >= MIN_MONTHLY_SEARCHES][:MAX_TOPIC_KEYWORDS]
        keywords |= {row["keyword"]: row for row in ideas if row["keyword"] not in keywords}

    print("\n=== 3 of 3: which of those keywords are really about the topic? ===\n", flush=True)
    given_file.write_text(json.dumps(given, indent=2, ensure_ascii=False))
    topics = sort_keywords(run, ["--topics", str(given_file)])

    save_scoreboard(run, topics, list(keywords.values()), results)


def group_keywords(run: str, keywords: list[dict], about: list[str]) -> list[dict]:
    """Have the LLM of the repeatability tool find the topics the keywords are about."""
    keywords_file = OUTPUT_DIR / f"{run}_topic_keywords.json"
    keywords_file.write_text(json.dumps([as_candidate(row) for row in keywords], indent=2, ensure_ascii=False))
    return sort_keywords(run, ["--keywords", str(keywords_file), "--about", ", ".join(about)])


def sort_keywords(run: str, options: list[str]) -> list[dict]:
    """Run the topic step of the repeatability tool. Returns the topics, each with the Google keywords about it."""
    topics_file = OUTPUT_DIR / f"{run}_topics.json"
    run_tool(REPEATABILITY_TOOL, ["keyword_topics.py", *options, "--out", str(topics_file)])
    return json.loads(topics_file.read_text())


def as_candidate(keyword: dict) -> dict:
    """What the topic step needs to know about a keyword."""
    return {"keyword": keyword["keyword"], "monthly_searches": int(keyword["avg_monthly_searches"]), "history": keyword["monthly_searches"]}


def why_not_rising(keyword: dict) -> str:
    """Empty when the searches for a keyword are rising, otherwise the reason they are not."""
    if int(keyword["avg_monthly_searches"]) < MIN_MONTHLY_SEARCHES:
        return f"under {MIN_MONTHLY_SEARCHES} searches a month"
    if keyword["floor_trend"] not in KEEP_TRENDS:
        return f"search is {keyword['floor_trend']}"
    if keyword["yoy_change_pct"] and float(keyword["yoy_change_pct"]) <= YOY_FALLING_PCT:
        return "the quiet months rose, but searches over the whole year fell"
    return ""


def searches_gained(keyword: dict | None) -> int:
    """Searches a month in the last 12 months, minus the 12 months before: big AND rising keywords come first."""
    return int(keyword["last_12m_avg"] or 0) - int(keyword["prior_12m_avg"] or 0) if keyword else 0


def biggest_keyword(topic: dict, by_keyword: dict[str, dict]) -> dict | None:
    """The most searched of a topic's keywords stands for the topic on Google (None when Google knows no phrasing of it)."""
    return max((by_keyword[keyword] for keyword in topic["keywords"]), key=lambda row: int(row["avg_monthly_searches"]), default=None)


def score_repeatability(run: str, phrases_file: Path | None = None) -> dict:
    """Run the repeatability tool and return its results: under "queries_scored", every search query it scored, best first.

    Without a phrases file it finds its own queries, from the outlier videos of the channels it scans.
    """
    command = ["main.py", "--run-id", run]
    if phrases_file:
        command += ["--queries", str(phrases_file)]
    run_tool(REPEATABILITY_TOOL, command)
    return json.loads((REPEATABILITY_TOOL / "output" / f"final_output_{run}.json").read_text())


def search_volume(run: str, command: list[str]) -> list[dict]:
    """Run the keyword tool and return one row per keyword: monthly searches and the trend."""
    keywords_csv = OUTPUT_DIR / f"{run}_keywords.csv"
    run_tool(KEYWORD_TOOL, ["kwa", *command, "--run-id", run, "--out", str(keywords_csv)])
    with keywords_csv.open(newline="") as f:
        return list(csv.DictReader(f))


def run_tool(tool: Path, command: list[str]):
    """Run a command in a tool's folder with `uv run`, which uses the tool's own packages (and installs them first if needed)."""
    # A virtual environment activated in your shell belongs to some other project: uv would warn about it on every run.
    environment = {name: value for name, value in os.environ.items() if name != "VIRTUAL_ENV"}
    subprocess.run(["uv", "run", *command], cwd=tool, env=environment, check=True)


def write_phrases(run: str, phrases: list[str]) -> Path:
    """The hand-off between the tools: one search phrase per line."""
    phrases_file = OUTPUT_DIR / f"{run}_phrases.txt"
    phrases_file.write_text("\n".join(phrases) + "\n")
    return phrases_file


def save_run_info(run: str, direction: str, seeds: list[str]):
    """What the run viewer can't read from the tools' own files: the direction, the seeds and the settings."""
    names = ["KEEP_TRENDS", "MIN_MONTHLY_SEARCHES", "YOY_FALLING_PCT", "MAX_TOPICS", "MAX_GROUPED_KEYWORDS", "MAX_TOPIC_KEYWORDS"]
    settings = {name: globals()[name] for name in names}
    info = {"run": run, "direction": direction, "seeds": seeds, "settings": settings}
    (OUTPUT_DIR / f"{run}_run.json").write_text(json.dumps(info, indent=2))


def save_scoreboard(run: str, topics: list[dict], keywords: list[dict], results: dict):
    """One row per topic. A topic to make is repeatable on YouTube AND rising on Google."""
    by_keyword = {row["keyword"]: row for row in keywords}
    settings = results["settings"]
    scoreboard = []
    for topic in topics:
        # Starting from YouTube scores several phrasings of a topic, starting from search only the topic's own query: the best one counts.
        scored = [
            query for query in results["queries_scored"]
            if query["topic"] == topic["name"] or query["search_query"] == topic["search_query"].strip()
        ]  # fmt: skip
        best = max(scored, key=lambda query: query["score"], default=None)
        searches = biggest_keyword(topic, by_keyword)
        repeatable = best and best["hit_channels"] >= settings["MIN_HITS"] and best["score"] >= settings["MIN_SCORE"]
        not_rising = why_not_rising(searches) if searches else "Google knows no phrasing of it"

        if topic["skip"]:
            verdict = f"skipped: {topic['skip']}"
        elif not best:
            verdict = f"not searched on YouTube: outside the {MAX_TOPICS} biggest"
        elif repeatable:
            verdict = f"repeatable, but {not_rising}" if not_rising else "make it"
        else:
            verdict = "not repeatable" if not_rising else "rising, but not repeatable"
        scoreboard.append({
            "topic": topic["name"],
            "verdict": verdict,
            "youtube_query": best["search_query"] if best else topic["search_query"],
            "repeatability": best["score"] if best else "",
            "hit_channels": best["hit_channels"] if best else "",
            "keyword": searches["keyword"] if searches else "",
            "monthly_searches": searches["avg_monthly_searches"] if searches else "",
            "yoy_change_pct": searches["yoy_change_pct"] if searches else "",
            "search_trend": searches["floor_trend"] if searches else "",
            "searches_gained": searches_gained(searches) if searches else "",
            "rising_keywords": f"{sum(not why_not_rising(by_keyword[keyword]) for keyword in topic['keywords'])} of {len(topic['keywords'])}",
            "keywords": "; ".join(topic["keywords"]),
        })  # fmt: skip
    scoreboard.sort(key=lambda row: (row["verdict"] == "make it", row["repeatability"] or 0), reverse=True)

    scoreboard_csv = OUTPUT_DIR / f"{run}_scoreboard.csv"
    with scoreboard_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SCOREBOARD_COLUMNS)
        writer.writeheader()
        writer.writerows(scoreboard)

    print("\n=== TOPICS ===\n")
    print(f"{'repeatability':>13}  {'channels':>8}  {'searches/mo':>11}  {'YoY %':>7}  {'verdict':<44}  topic")
    for row in scoreboard:
        print(
            f"{row['repeatability'] or '-':>13}  {row['hit_channels'] or '-':>8}  {row['monthly_searches'] or '-':>11}  "
            f"{row['yoy_change_pct'] or '-':>7}  {row['verdict'][:44]:<44}  {row['topic']}"
        )
    to_make = [row["topic"] for row in scoreboard if row["verdict"] == "make it"]
    print(f"\nTopics to make: {', '.join(to_make) or 'none this time'}")
    print(f"Saved to {scoreboard_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find video topics that are repeatable on YouTube and rising in search.")
    parser.add_argument("seeds", nargs="*", help="seed keywords to start from search; without seeds it starts from the channels in config.py")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    run = f"{datetime.now():%Y%m%d-%H%M%S}"
    save_run_info(run, "from-keywords" if args.seeds else "from-youtube", args.seeds)
    try:
        if args.seeds:
            topics_from_keywords(run, args.seeds)
        else:
            topics_from_youtube(run)
    finally:
        run_viewer.build()  # also after a failed run: the viewer shows how far it got
        print(f"\nInspect every step: {(HERE / 'index.html').as_uri()}#{run}")
