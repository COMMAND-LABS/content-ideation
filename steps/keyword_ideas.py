"""STEP: seed keywords -> the keywords people search for on Google, each with 48 months of search history.

Asks Google Ads Keyword Planner (GenerateKeywordIdeas) for keywords related to the seeds.

    in:   ["ai agents", "claude code"]
    out:  [{"keyword": "claude code", "avg_monthly_searches": 550000,
            "monthly_searches": {"2022-09": 320, ..., "2026-08": 301000}, ...}, ...]

Try it:   uv run python -m steps.keyword_ideas "ai agents"
"""

import sys
from datetime import date

from shared import google_ads
from shared.settings import config

MONTHS = 48  # Keyword Planner keeps 4 years of monthly history; the API default is only 12 months


def keyword_ideas(seeds: list[str]) -> list[dict]:
    from google.ads.googleads.errors import GoogleAdsException

    client = google_ads.client()
    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = google_ads.customer_id()
    request.keyword_seed.keywords.extend(seeds)
    request.language = client.get_service("GoogleAdsService").language_constant_path(config.LANGUAGE_ID)
    geo_service = client.get_service("GeoTargetConstantService")
    request.geo_target_constants.extend(geo_service.geo_target_constant_path(geo_id) for geo_id in config.GEO_IDS)
    request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    _set_history_window(client, request)

    try:
        ideas = list(client.get_service("KeywordPlanIdeaService").generate_keyword_ideas(request=request))
    except GoogleAdsException as error:
        messages = "; ".join(e.message for e in error.failure.errors)
        raise SystemExit(f"Google Ads API request failed (request ID {error.request_id}): {messages}")
    return [_row(idea.text, idea.keyword_idea_metrics) for idea in ideas]


def _set_history_window(client, request):
    """The last MONTHS completed months. The API clamps dates outside what it has instead of rejecting them."""
    today = date.today()
    end = today.year * 12 + today.month - 2  # previous month, as a 0-based month count
    start = end - (MONTHS - 1)
    month_enum = client.enums.MonthOfYearEnum
    window = request.historical_metrics_options.year_month_range
    window.start.year, window.start.month = start // 12, month_enum(start % 12 + 2)
    window.end.year, window.end.month = end // 12, month_enum(end % 12 + 2)


def _row(text: str, metrics) -> dict:
    return {
        "keyword": text,
        "avg_monthly_searches": metrics.avg_monthly_searches,
        "competition": metrics.competition.name,
        "competition_index": metrics.competition_index,
        "low_top_of_page_bid": metrics.low_top_of_page_bid_micros / 1_000_000,
        "high_top_of_page_bid": metrics.high_top_of_page_bid_micros / 1_000_000,
        "monthly_searches": {f"{v.year}-{v.month.value - 1:02d}": v.monthly_searches for v in metrics.monthly_search_volumes},
    }


if __name__ == "__main__":
    rows = keyword_ideas(sys.argv[1:] or ["ai agents"])
    print(f"{len(rows)} keywords. The 10 most searched:")
    for row in sorted(rows, key=lambda row: row["avg_monthly_searches"], reverse=True)[:10]:
        print(f"  {row['avg_monthly_searches']:>10,} a month   {row['keyword']}")
