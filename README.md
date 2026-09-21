# Content ideation

Find video topics that are repeatable on YouTube and rising in Google search.

- Repeatable means many different channels have had a hit with the topic, recently, and ideally channels about your size. One viral video proves little. The same topic working for 20 channels proves a lot.
- Rising means more people search Google for it than a year ago.

New here? Read docs/content-ideation-explained.pdf to understand every step of how this project works, how to try each step on its own, and the first principles behind why it works.

A topic that passes both tests gets the verdict "make it":

```txt
repeatability  channels  searches/mo    YoY%   verdict               topic
        3.441        14       550000    405.6  make it               Claude Code
        2.797        14        49500     -3.4  make it               AI Agents
```

## Two pipelines, one scoreboard

You can start from either side. Both end with the same scoreboard.

- pipeline1_from_keywords.py | Google search: what are people looking for around these seed keywords?
  - `uv run pipeline1_from_keywords.py "ai agents" "claude code"`
- pipeline2_from_youtube.py | YouTube: what is working for the channels in your niche? 
  - `uv run pipeline2_from_youtube.py`

```txt
Pipeline 1:  seeds -> keyword ideas -> trends -> rising keywords -> topics -> topics worth a search -> repeatability -> SCOREBOARD
Pipeline 2:  channels -> outliers -> topics -> YouTube suggestions -> search queries -> repeatability -> Google seeds -> keyword ideas -> keywords about the topic -> SCOREBOARD
```

Open a pipeline file and you can read the whole thing top to bottom: each step is one line, with its input and output written above it.

## What you need

- uv (https://docs.astral.sh/uv/)
  - Free tool. It installs Python and the 3rd-party packages by itself.
- YouTube Data API key
  - The YouTube steps
  - Free: 10,000 quota units a day, and a search costs 100
- OpenAI API key
  - The LLM steps (grouping phrasings into topics)
  - Anthropic works too: set `LLM_PROVIDER` in `config.py`
  - A few small calls per run (`gpt-5.4` by default)
- Google Ads account with API access
  - The Google steps
  - Free, but Google has to approve the access, which takes a few hours

## Setup

1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
2. API keys.
  - Create a YouTube API key (docs/setup/youtube_api.md)
  - Create a OpenAI API key (docs/setup/youtube_api.md)
  - Place API keys in the .env file
3. **Google Ads.** Follow [docs/setup/google_ads.md](docs/setup/google_ads.md). Still waiting for the approval? Pipeline 2 works without it: it runs the YouTube half and stops with the repeatability scores.
4. Configure your search.
  - Pipeline 1: Provide keywords. 
  - At the top of `config.py`, set `MY_CHANNEL` to your channel and `CHANNELS_TO_SCAN` to the channels in your niche. Pipeline 2 only finds topics these channels have made, so this list decides how relevant its results are.

YouTube and LLM responses are cached for 24 hours, so repeating a run the same day costs no YouTube quota. Add `--refresh` to pull fresh data.

## The final output 

Printed at the end of a run and saved to `runs/<run>/scoreboard.csv`, topics to make first.

| Column | Meaning |
| --- | --- |
| `topic` | The topic, named by the LLM |
| `verdict` | `make it`, or what is missing |
| `youtube_query`, `repeatability`, `hit_channels` | The topic's best-scoring phrasing on YouTube, its repeatability score, and how many different channels had a hit with it |
| `keyword`, `monthly_searches`, `yoy_change_pct`, `search_trend` | The topic's most searched Google keyword, its average searches a month, the last 12 months against the 12 before, and the trend: `rising`, `flat`, `shrinking` or `new` |
| `searches_gained` | The searches a month the keyword gained on the year before |
| `rising_keywords` | "3 of 8": how many of the topic's keywords are rising. When it is only a few, the verdict rests on the biggest keyword alone, so check that one really is the topic |
| `keywords` | Every Google keyword of the topic |

A topic gets the verdict **make it** when it passes both:

| | The topic is judged by | It passes when |
| --- | --- | --- |
| Repeatable | its best-scoring phrasing on YouTube | hits on `MIN_HITS`+ channels and a score of `MIN_SCORE`+ |
| Rising | its most searched Google keyword | trend `rising` or `new`, `MIN_MONTHLY_SEARCHES`+ searches a month, and the whole year not down `YOY_FALLING_PCT` or more |

## Looking inside a run

Every run gets a folder, and every step saves one readable file in it: a **summary** in numbers on top, then what went **in**, and what came **out**.

```txt
runs/20260921-123241/
    run.json                      which pipeline, the seeds, and every setting the run used
    01_a_seeds_to_keywords.json   {"step": ..., "summary": ..., "input": ..., "output": ...}   the short version: which keywords each seed brought in
    01_b_keyword_ideas.json       the full version: every keyword with its 48 months of searches
    02_search_trends.json
    ...
    07_scoreboard.json
    scoreboard.csv
```

To walk through a run step by step, open [viewer/index.html](viewer/index.html) in a browser. Each step shows what it does, what it found in this run, and its data, down to the thumbnails of the hit videos behind a score. The pipelines refresh the page's data after every run, also after a failed one, so you can see how far it got.

## Try one step on its own

Every step is a small module in [steps/](steps/) with its input and output described at the top, and each one runs by itself:

| Step | Try it | Needs |
| --- | --- | --- |
| [keyword_ideas](steps/keyword_ideas.py) | `uv run python -m steps.keyword_ideas "ai agents"` | Google Ads |
| [search_trends](steps/search_trends.py) | `uv run python -m steps.search_trends` | nothing |
| [rising_keywords](steps/rising_keywords.py) | `uv run python -m steps.rising_keywords` | nothing |
| [group_into_topics](steps/group_into_topics.py) | `uv run python -m steps.group_into_topics` | LLM key |
| [choose_topics](steps/choose_topics.py) | `uv run python -m steps.choose_topics` | nothing |
| [find_outliers](steps/find_outliers.py) | `uv run python -m steps.find_outliers @Fireship` | YouTube key |
| [outliers_to_topics](steps/outliers_to_topics.py) | `uv run python -m steps.outliers_to_topics` | LLM key |
| [youtube_suggestions](steps/youtube_suggestions.py) | `uv run python -m steps.youtube_suggestions "claude code"` | nothing |
| [query_variants](steps/query_variants.py) | `uv run python -m steps.query_variants "claude code"` | LLM key |
| [score_repeatability](steps/score_repeatability.py) | `uv run python -m steps.score_repeatability "claude code"` | YouTube key |
| [google_seeds](steps/google_seeds.py) | `uv run python -m steps.google_seeds` | LLM key |
| [pick_topic_keywords](steps/pick_topic_keywords.py) | `uv run python -m steps.pick_topic_keywords` | LLM key |
| [scoreboard](steps/scoreboard.py) | `uv run python -m steps.scoreboard` | nothing |

## What is in this folder

| | |
| --- | --- |
| [pipeline1_from_keywords.py](pipeline1_from_keywords.py), [pipeline2_from_youtube.py](pipeline2_from_youtube.py) | The two pipelines: the steps in order, nothing else |
| [steps/](steps/) | One small module per step |
| [shared/](shared/) | The plumbing the steps share: the YouTube API, Google Ads, the LLM, the cache, the run folder |
| [viewer/](viewer/) | The run viewer |
| `config.py`, `.env` | Every setting, and your API keys. Yours: copied from [config.py.example](config.py.example) and [.env.example](.env.example), not committed |
| [docs/](docs/) | The explainer PDF, the setup guides, and what every YouTube setting does when you turn it up or down ([PDF](docs/repeatability-settings.pdf), written for an earlier version: its "top ideas" list is now the scoreboard) |
| [tests/](tests/) | Offline tests, no API keys needed: `uv run pytest` |
| `runs/`, `cache/` | Your runs and cached API responses (not committed) |

Your `config.py`, API keys, `google-ads.yaml`, `client_secret*.json` and everything the pipelines produce are in [.gitignore](.gitignore): they stay on your machine.
