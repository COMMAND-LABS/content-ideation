# Setting up the Google Ads API

The Google side of the pipelines asks Google Ads Keyword Planner how often keywords are searched. The API is free to use. You do need a Google Ads account and API access that Google approves, so start this early.

Still waiting for the approval? `uv run pipeline2_from_youtube.py` works without it: it runs the YouTube half and stops with the repeatability scores.

## 1. Get access

You will need a Google Workspace account to follow along.

1. **Enable the Google Ads API** in a Google Cloud project (the project of your YouTube API key is fine): https://console.cloud.google.com/marketplace/product/google/googleads.googleapis.com
2. **Configure the OAuth consent screen** of that project. The OAuth client has to be verified, so fill out the "Branding" form.
3. **Create an OAuth client ID** at https://console.cloud.google.com/apis/credentials: Create credentials → OAuth client ID → application type `Desktop app`. Download its JSON file.
4. **Apply for "Basic Access"** to the Google Ads API. Until it is granted, the API only answers for test accounts and returns no real keyword data (see Troubleshooting).

## 2. Log in

Put the downloaded `client_secret_*.json` in the project folder (it is gitignored), then:

```sh
uv run python -m shared.google_ads login    # opens a browser; writes the refresh token to google-ads.yaml
uv run python -m shared.google_ads check    # verifies the login and lists your Ads account IDs
```

Add the account ID you log in through (the manager account, if you use one) to `google-ads.yaml`:

```yaml
login_customer_id: "1234567890"
```

If keyword requests should run against a different account than `login_customer_id` (e.g. a client account under the manager), set `GOOGLE_ADS_CUSTOMER_ID` in `.env`.

## 3. Check that it works

```sh
uv run python -m steps.keyword_ideas "ai agents"
```

It prints the 10 most searched keywords Google suggests around the seed.

Other markets: set `GEO_IDS` and `LANGUAGE_ID` in `config.py` (default: United States, English). Geo target IDs: https://developers.google.com/google-ads/api/data/geotargets

## Troubleshooting

- **Refresh token stops working after 7 days** – the OAuth consent screen is `External` + `Testing`. Set the user type to `Internal` (Workspace) or publish the app, then log in again.
- **`DEVELOPER_TOKEN_NOT_APPROVED` / only test accounts allowed** – the project is still on Test Account access, which cannot query production accounts and returns no real keyword data. Wait for Explorer or Basic access.
- **`USER_PERMISSION_DENIED`** – `login_customer_id` is missing or is not the manager account that the request's customer ID sits under.
