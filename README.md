# Content ideation

Find video topics that are **repeatable on YouTube** and **rising in Google search**.

- **Repeatable** means many different channels have had a hit with the topic, recently, and ideally channels about your size. One viral video proves little. The same topic working for 13 channels proves a lot.
- **Rising** means more people search Google for it than a year ago.

**New here? Read [the explainer (PDF)](docs/content-ideation-explained.pdf):** how every step works, and the first principles behind why it works.

A topic that passes both gets the verdict **make it**:

```txt
repeatability  channels  searches/mo    YoY %  verdict               topic
        3.447        13       550000    405.6  make it               Claude Code
        2.803        13        49500     -3.4  make it               AI Agents
            -         -       135000     15.9  skipped: unrelated    Code Geass
```

## How it works

This folder holds no research logic. [ideate.py](ideate.py) runs the two tools inside it, one after the other, and an LLM connects what they find:

| Tool | The question it answers | Data from |
| --- | --- | --- |
| [repeatability-analysis](repeatability-analysis/) | Has this topic worked for many different channels? | YouTube Data API v3 |
| [keyword-analysis](keyword-analysis/) | Are more people searching for this than a year ago? | Google Ads API (Keyword Planner) |

YouTube and Google know the same topic under different phrasings: YouTube knows "build and sell ai agent 6 hours course", Google knows "ai agent course". So the LLM puts the phrasings of a topic together, and the topic is judged **as a whole**. You can start from either side:

```txt
From keywords:  seeds    -> rising keywords   -> LLM groups them into topics -> ONE YouTube search per topic -> scoreboard
From YouTube:   channels -> repeatable topics -> LLM writes Google seeds     -> keyword ideas per topic
                         -> LLM keeps the keywords that are about the topic  -> scoreboard
```

## What you need

| | For | Cost |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | Running the tools. It installs Python and each tool's packages on the first run | Free |
| Python 3.10+ | The two scripts in this folder (they use no packages) | Free |
| YouTube Data API key | The YouTube tool | Free: 10,000 quota units a day, and a search costs 100 |
| OpenAI API key | Grouping phrasings into topics. Anthropic works too: set `LLM_PROVIDER` in `config.py` | A few small calls per run (`gpt-4o-mini` by default) |
| Google Ads account with API access | The keyword tool | Free, but Google has to approve the access, which takes a while |

## Setup

1. **API keys.** Create the YouTube API key ([steps](repeatability-analysis/READMEs/youtube_api.md)), then:

    ```sh
    cp .env.example .env        # fill in YOUTUBE_API_KEY and OPENAI_API_KEY
    ```

2. **Your niche.**

    ```sh
    cp config.py.example config.py
    ```

    At the top of `config.py`, set `MY_CHANNEL` to your channel and `CHANNELS_TO_SCAN` to the channels in your niche. The YouTube tool only finds topics these channels have made, so this list decides how relevant the results are.

3. **Keyword tool.** Follow [keyword-analysis/README.md](keyword-analysis/README.md) to get Google Ads API access and log in with `uv run kwa auth`.

Still waiting for the Google Ads approval? The YouTube tool works on its own in the meantime: `cd repeatability-analysis && uv run main.py`.

## Usage

```sh
# Start from search: what are people looking for around these seed keywords?
python3 ideate.py "ai agents" "claude code"

# Start from YouTube: what is working for the channels in config.py?
python3 ideate.py
```

YouTube and LLM responses are cached for 24 hours, so repeating a run the same day costs no YouTube quota.

## The scoreboard

Printed at the end of a run and saved to `output/<run>_scoreboard.csv`, topics to make first.

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

How the repeatability score is calculated: [pipeline-overview.pdf](repeatability-analysis/READMEs/pipeline-overview.pdf). How the search trend is measured: [keyword-analysis/README.md](keyword-analysis/README.md#search-history-and-trends).

## Inspecting a run

Open [index.html](index.html) in a browser. It lists every run and shows each step of the pipeline in order, from the first checkpoint to the **Final Results**. Every step comes with a commentary: what the step does, and what it found in this run.

A run has one ID (its start time, like `20260921-073628`), and `ideate.py` gives it to both tools, so everything a run produced is found under that ID:

| Written by | Where |
| --- | --- |
| YouTube tool | `repeatability-analysis/checkpoints/<run>_step_<n>.json` and `repeatability-analysis/output/final_output_<run>.json` |
| Keyword tool | `keyword-analysis/checkpoints/<run>/` with its `run.log` (starting from YouTube: one folder per topic, `<run>_topic<n>/`) |
| ideate.py | `output/<run>_*`: the settings of the run, what the tools handed each other, and the scoreboard |

`ideate.py` refreshes the page's data after every run, also after a failed one, so you can see how far it got. Runs of a single tool are listed too (under "Single tool"); after one of those, refresh by hand:

```sh
python3 run_viewer.py
```

A page opened from disk can't read JSON files, so [run_viewer.py](run_viewer.py) copies the checkpoints into `output/viewer/` as `.js` files that the page loads. The commentary is written there too.

## Settings

Every setting is in `config.py` (your copy of [config.py.example](config.py.example)): your niche first, then these settings of `ideate.py`, then the YouTube tool's (what each of those does when you turn it up or down is in [pipeline-overview.pdf](repeatability-analysis/READMEs/pipeline-overview.pdf)).

| Setting | Meaning |
| --- | --- |
| `KEEP_TRENDS` | The search trends that count as rising |
| `MIN_MONTHLY_SEARCHES` | Keywords under this many searches a month are too noisy to trust |
| `YOY_FALLING_PCT` | A rising trend is measured on the quiet months of the year. It does not count when searches over the whole year fell this much: that is a keyword past its peak |
| `MAX_TOPICS` | From keywords: at most this many topics go on to YouTube. Each costs one YouTube search: 100 of the 10,000 quota units you get per day |
| `MAX_GROUPED_KEYWORDS` | From keywords: at most this many rising keywords are grouped into topics |
| `MAX_TOPIC_KEYWORDS` | From YouTube: at most this many of Google's suggestions per topic are judged |

## What is in this folder

| | |
| --- | --- |
| `config.py`, `.env` | Every setting, and your API keys. Yours: copied from [config.py.example](config.py.example) and [.env.example](.env.example), not committed |
| [ideate.py](ideate.py) | Runs the two tools back to back and writes the scoreboard |
| [run_viewer.py](run_viewer.py), [index.html](index.html) | The run viewer |
| [repeatability-analysis/](repeatability-analysis/) | The YouTube tool, and the LLM steps |
| [keyword-analysis/](keyword-analysis/) | The keyword tool |
| [docs/](docs/) | The explainer: the PDF, and the `explainer.html` it is printed from |
| `output/` | Your runs (not committed) |

Your `config.py`, API keys, `google-ads.yaml`, `client_secret*.json` and everything the tools produce are in [.gitignore](.gitignore): they stay on your machine.
