# Content ideation

Find video topics that are repeatable on YouTube and rising in Google search.

- Repeatable means many different channels have had a hit with the topic, recently, and ideally channels about your size. One viral video proves little. The same topic working for 20 channels proves a lot.
- Rising means more people search Google for it than a year ago.

New here? Read the guide for the pipeline you want: [pipeline 1](docs/pipeline1-youtube-repeatable-outliers.pdf), [pipeline 2](docs/pipeline2-google-search-keyword-analysis.pdf), [pipeline 3](docs/pipeline3-youtube-repeatability-plus-google-search-confirmation.pdf) or [pipeline 4](docs/pipeline4-google-search-keyword-research-plus-youtube-confirmation.pdf). Each walks through one pipeline step by step, with a real example, why the step works, and where it falls short.

A topic that passes both tests gets the verdict "make it":

```txt
repeatability  channels  searches/mo    YoY%   verdict               topic
        3.441        14       550000    405.6  make it               Claude Code
        2.797        14        49500     -3.4  make it               AI Agents
```

## Four pipelines, one scoreboard

Pipelines 1 and 2 each answer one question. Pipelines 3 and 4 answer it and then confirm the answer on the other side. All four end with the same scoreboard.

| | Asks | Needs | Run it |
| --- | --- | --- | --- |
| [Pipeline 1](pipeline_1_youtube_repeatable_outliers.py) · YouTube repeatable outliers | What is working for the channels in your niche, and for how many of them? | YouTube key, LLM key | `uv run pipeline_1_youtube_repeatable_outliers.py` |
| [Pipeline 2](pipeline_2_google_search_keyword_analysis.py) · Google search keyword analysis | What are people googling around your seed keywords, and which of it is rising? | Google Ads, LLM key | `uv run pipeline_2_google_search_keyword_analysis.py "ai agents" "claude code"` |
| [Pipeline 3](pipeline_3_youtube_repeatability_plus_google_search_confirmation.py) · YouTube repeatability + Google search confirmation | Pipeline 1, then: is each repeatable topic also rising on Google? | all three | `uv run pipeline_3_youtube_repeatability_plus_google_search_confirmation.py` |
| [Pipeline 4](pipeline_4_google_search_keyword_research_plus_youtube_confirmation.py) · Google search keyword research + YouTube confirmation | Pipeline 2, then: is each rising topic also repeatable on YouTube? | all three | `uv run pipeline_4_google_search_keyword_research_plus_youtube_confirmation.py "ai agents"` |

```txt
Pipeline 1:  channels -> outliers -> topics -> YouTube suggestions -> search queries -> repeatability -> SCOREBOARD
Pipeline 2:  seeds -> keyword ideas -> trends -> rising keywords -> topics -> topics that gained the most -> SCOREBOARD
Pipeline 3:  pipeline 1 -> Google seeds -> keyword ideas -> keywords about the topic -> SCOREBOARD
Pipeline 4:  pipeline 2 -> repeatability -> SCOREBOARD
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
3. **Google Ads.** Follow [docs/setup/google_ads.md](docs/setup/google_ads.md). Still waiting for the approval? Pipeline 1 needs no Google Ads access.
4. Configure your search.
  - Pipelines 2 and 4: provide seed keywords on the command line.
  - At the top of `config.py`, set `MY_CHANNEL` to your channel and `CHANNELS_TO_SCAN` to the channels in your niche. Pipelines 1 and 3 only find topics these channels have made, so this list decides how relevant their results are.

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
| `pipeline_1_…py` to `pipeline_4_…py` | The four pipelines: the steps in order, nothing else. Pipelines 3 and 4 repeat the steps of 1 and 2, then add the other side |
| [steps/](steps/) | One small module per step |
| [shared/](shared/) | The plumbing the steps share: the YouTube API, Google Ads, the LLM, the cache, the run folder |
| [viewer/](viewer/) | The run viewer |
| `config.py`, `.env` | Every setting, and your API keys. Yours: copied from [config.py.example](config.py.example) and [.env.example](.env.example), not committed |
| [docs/](docs/) | The four pipeline guides (PDF) and the setup guides for the YouTube and Google Ads APIs |
| [tests/](tests/) | Offline tests, no API keys needed: `uv run pytest` |
| `runs/`, `cache/` | Your runs and cached API responses (not committed) |

Your `config.py`, API keys, `google-ads.yaml`, `client_secret*.json` and everything the pipelines produce are in [.gitignore](.gitignore): they stay on your machine.
