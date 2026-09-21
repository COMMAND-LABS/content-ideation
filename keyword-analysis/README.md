# Keyword analysis

How many people search Google for a keyword, month by month for the last four years, and is that number rising? The data comes from Google Ads Keyword Planner, through the Google Ads API. It is the search half of [content ideation](../README.md), and it also runs on its own as `kwa`.

The API is free to use. You do need a Google Ads account and API access that Google approves, so start this early.

## Get access to the Google Ads API

You will need a Google Workspace account to follow along.

1. **Enable the Google Ads API** in a Google Cloud project (the project of your YouTube API key is fine): https://console.cloud.google.com/marketplace/product/google/googleads.googleapis.com
2. **Configure the OAuth consent screen** of that project. The OAuth client has to be verified, so fill out the "Branding" form.
3. **Create an OAuth client ID** at https://console.cloud.google.com/apis/credentials: Create credentials → OAuth client ID → application type `Desktop app`. Download its JSON file.
4. **Apply for "Basic Access"** to the Google Ads API. Until it is granted, the API only answers for test accounts and returns no real keyword data (see [Troubleshooting](#troubleshooting)).

## Authenticate

Requires [uv](https://docs.astral.sh/uv/). Put the downloaded `client_secret_*.json` in the project root (it is gitignored), then:

```sh
uv sync
uv run kwa auth     # opens a browser; writes the refresh token to google-ads.yaml
uv run kwa check    # verifies the credentials and lists your Ads account IDs
```

Add the account ID you log in through (the manager account, if you use one) to `google-ads.yaml`:

```yaml
login_customer_id: "1234567890"
```

If keyword requests should run against a different account than `login_customer_id` (e.g. a client account under the manager), set `GOOGLE_ADS_CUSTOMER_ID` in the `.env` of the project root.

## Run analyses

```sh
# Expand seeds (and/or a URL) into keyword ideas with search volume
uv run kwa ideas "youtube automation" "faceless channel"
uv run kwa ideas --url https://example.com --limit 200

# Search volume for an exact keyword list
uv run kwa metrics "how to edit videos" "best video editor"
uv run kwa metrics --file keywords.txt

# Other markets: geo target + language IDs (default 2840 = US, 1000 = English)
uv run kwa ideas "video editing" --geo 2826 2124 --lang 1000
```

Results print to the terminal (top 25 by volume) and are saved as CSV in `data/`. For custom analyses, import the functions directly:

```python
from kwa.config import ads_client, customer_id
from kwa.keywords import keyword_ideas

rows = keyword_ideas(ads_client(), customer_id(), ["youtube automation"])
```

Geo target IDs: https://developers.google.com/google-ads/api/data/geotargets

## Search history and trends

Each lookup fetches 48 months of monthly search volume, the most Keyword Planner keeps (`--months N` for less). Two files are written per run:

- `data/<cmd>-<run_id>.csv` – one row per keyword with the trend measures below.
- `data/<cmd>-<run_id>-monthly.csv` – one row per keyword, one column per month. Open it in a spreadsheet and chart a row to see the shape.

Trends compare the last 12 months with the 12 before, so seasonality cancels out:

| Column | Meaning |
| --- | --- |
| `yoy_change_pct` | Change in average monthly volume: is overall demand growing? |
| `floor_last_12m`, `floor_prior_12m` | The floor: mean of the 3 lowest months in each window |
| `floor_change_pct` | Change in the floor: is baseline demand growing, even in the quiet months? |
| `floor_trend` | `rising` at +20% or more, `shrinking` at -20% or less, otherwise `flat` |

The 20% threshold exists because Keyword Planner rounds volumes into buckets about 20-25% apart; a smaller change can be a single bucket step. Treat keywords under ~200 searches/month as noisy. When YoY and the floor disagree (YoY up, floor down), the growth came from a spike, not from a higher baseline.

## Logs and checkpoints

Every `ideas` / `metrics` run gets an ID made of a timestamp plus 6 hex digits (`20260920-182648-d02466`), or the one given with `--run-id`: [ideate.py](../ideate.py) passes its own, so both tools save a run under one ID. Each step is logged to the terminal as it happens, and the data at each step is saved under `checkpoints/<run_id>/`:

| File | What it holds |
| --- | --- |
| `01_inputs.json` | Resolved terms, URL, customer ID, geo, language, limit |
| `02_request.json` | The exact request sent to the Ads API |
| `03_raw_response.json` | Google's unmodified response, including per-month volumes |
| `04_parsed_rows.csv` | The response flattened into rows, in the order Google returned them |
| `05_trend_metrics.csv` | Rows plus the year-over-year and floor measures |
| `06_final_sorted.csv` | Rows sorted by volume (same content as the file in `data/`) |
| `06_monthly_wide.csv` | One row per keyword, one column per month |
| `run.log` | The step log, including any API error |

The final CSV in `data/` carries the same run ID, so you can trace any output back to its checkpoints. Logs go to stderr; add `2>/dev/null` to see only the results table.

## Troubleshooting

- **Refresh token stops working after 7 days** – the OAuth consent screen is `External` + `Testing`. Set the user type to `Internal` (Workspace) or publish the app, then re-run `uv run kwa auth`.
- **`DEVELOPER_TOKEN_NOT_APPROVED` / only test accounts allowed** – the project is still on Test Account access, which cannot query production accounts and returns no real keyword data. Wait for Explorer or Basic access.
- **`USER_PERMISSION_DENIED`** – `login_customer_id` is missing or is not the manager account that the request's customer ID sits under.

