# Repeatability analysis

Finds the video topics that have worked again and again for channels like yours. It is the YouTube half of [content ideation](../README.md), and it also runs on its own.

## How it works

The full walkthrough, with every formula and what each setting does when you turn it up or down: [pipeline-overview.pdf](READMEs/pipeline-overview.pdf). Every number below is a setting in `config.py`, in the project root.

One number drives everything: a channel's **median views** over its recent uploads, in one format (long-form or Shorts, never mixed). Every video is judged against its own channel's median, so 20,000 views on a small channel count for more than 200,000 on a huge one.

- **STEP 1: outliers.** Every channel in `CHANNELS_TO_SCAN` is scanned. An upload with at least `OUTLIER_MULTIPLE` times its channel's median is an outlier. The `TOP_CANDIDATES` biggest go on.
- **STEP 2: topics.** An LLM groups the outliers that are about the same topic and writes, for each topic, the search query a viewer would type into YouTube. Each query is then sent to YouTube's search autocomplete (free, no quota) to get the phrasings viewers really type, and the LLM picks up to `QUERY_VARIANTS` of them: same language, still on topic, a distinct angle. Every pick is scored in step 3 as an idea of its own.
- **STEP 3: repeatability.** Each query is searched on YouTube (`search.list`, 100 quota units per search). Your own channel is left out, and the first `CHANNELS_PER_QUERY` different channels are kept. A result is a **hit** when it has at least `HIT_MULTIPLE` times its own channel's median. It must also be at most `MAX_HIT_AGE_DAYS` old and have `MIN_HIT_VIEWS`+ views: an old video's lifetime views can't be fairly compared with its channel's current median, and a handful of views on a dead channel proves nothing. Recent hits, and hits from channels near your size, weigh the most:

```txt
hit_weight_i = (1 / (1 + |log10(median_views_i) − log10(median_views_mine)|)) × 0.5 ^ (age_i / AGE_HALF_LIFE_DAYS)
repeatability_score = Σ hit_weight_i
```

- **Top ideas.** An idea qualifies with hits from `MIN_HITS`+ different channels and a score of `MIN_SCORE`+. An idea that shares more than `MAX_HIT_OVERLAP` of its hits with a higher-scoring idea is the same idea again and is skipped. The best `TOP_IDEAS` are presented.

A full run with 10 topics uses roughly 1,500 of the 10,000 YouTube quota units you get per day, plus 100 per autocomplete variant. Responses are cached for 24 hours, so repeating a run costs nothing.

## Usage

```sh
cp ../.env.example ../.env              # then fill in YOUTUBE_API_KEY and OPENAI_API_KEY
cp ../config.py.example ../config.py    # then set MY_CHANNEL and CHANNELS_TO_SCAN
uv run main.py              # installs the packages on the first run
```

Getting the YouTube API key: [READMEs/youtube_api.md](READMEs/youtube_api.md).

The top ideas are printed, and each run saves its results to `output/final_output_<run_id>.json`. To walk through a run step by step, run `python3 run_viewer.py` in the parent folder and open its [index.html](../index.html).

To score search queries of your own, put one per line in a text file and run `uv run main.py --queries my_queries.txt`. Steps 1 and 2 are skipped and each query is scored as written. [ideate.py](../ideate.py) uses this to score the topics found by the keyword analysis, and passes `--run-id` so both tools save their checkpoints under one run ID.

Set `MY_CHANNEL`, `CHANNELS_TO_SCAN`, `FORMAT` and every tunable parameter in `../config.py`.

| File | Purpose |
| --- | --- |
| [config.py](config.py) | Reads the settings from `../config.py` and the API key from `../.env` |
| [youtube.py](youtube.py) | YouTube Data API wrapper |
| [stats.py](stats.py) | Format filter, channel median, hit weight |
| [llm.py](llm.py) | LLM access; provider (`openai` or `anthropic`) is chosen by `LLM_PROVIDER` in ../config.py |
| [cache.py](cache.py) | 24h disk cache of YouTube + LLM responses; `uv run main.py --refresh` pulls the latest |
| [checkpoints.py](checkpoints.py) | Run ID + per-step JSON dumps in `checkpoints/<run_id>_step_<n>.json` for debugging |
| [step1_outliers.py](step1_outliers.py) | STEP 1: outlier candidates |
| [step2_topics.py](step2_topics.py) | STEP 2: LLM topic dedupe + search queries, expanded with autocomplete variants |
| [step3_repeatability.py](step3_repeatability.py) | STEP 3: repeatability scoring |
| [final_output.py](final_output.py) | Dumps the final results to `output/final_output_<run_id>.json` |
| [main.py](main.py) | Runs the pipeline, prints the top ideas and saves the final output |
| [keyword_topics.py](keyword_topics.py) | Not part of the pipeline: sorts Google keywords into video topics with the LLM, for `../ideate.py` |

Tests (offline, no API keys needed, but `../config.py` has to exist): `uv run pytest`
