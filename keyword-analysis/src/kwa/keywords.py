"""Keyword Planner lookups via KeywordPlanIdeaService."""

import time
from datetime import date

from google.ads.googleads.client import GoogleAdsClient
from google.protobuf.json_format import MessageToDict

from kwa.run import Run

# Geo target / language constant IDs:
# https://developers.google.com/google-ads/api/data/geotargets
# https://developers.google.com/google-ads/api/data/codes-formats#languages
GEO_US = "2840"
LANG_ENGLISH = "1000"
# Keyword Planner keeps 4 years of monthly history; the API default is only 12 months.
MAX_MONTHS = 48

FIELDS = [
    "keyword",
    "avg_monthly_searches",
    "competition",
    "competition_index",
    "low_top_of_page_bid",
    "high_top_of_page_bid",
    "monthly_searches",
]


def _targeting(client: GoogleAdsClient, request, geo_ids: list[str], language_id: str, months: int) -> None:
    request.language = client.get_service("GoogleAdsService").language_constant_path(language_id)
    geo_service = client.get_service("GeoTargetConstantService")
    request.geo_target_constants.extend(geo_service.geo_target_constant_path(g) for g in geo_ids)
    request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH

    # History window: the last `months` completed months. The API clamps
    # dates outside what it has instead of rejecting them.
    today = date.today()
    end = today.year * 12 + today.month - 2  # previous month, as a 0-based month count
    start = end - (months - 1)
    month_enum = client.enums.MonthOfYearEnum
    window = request.historical_metrics_options.year_month_range
    window.start.year, window.start.month = start // 12, month_enum(start % 12 + 2)
    window.end.year, window.end.month = end // 12, month_enum(end % 12 + 2)


def _row(text: str, metrics) -> dict:
    monthly = [
        f"{v.year}-{v.month.value - 1:02d}:{v.monthly_searches}"
        for v in metrics.monthly_search_volumes
    ]
    return {
        "keyword": text,
        "avg_monthly_searches": metrics.avg_monthly_searches,
        "competition": metrics.competition.name,
        "competition_index": metrics.competition_index,
        "low_top_of_page_bid": metrics.low_top_of_page_bid_micros / 1_000_000,
        "high_top_of_page_bid": metrics.high_top_of_page_bid_micros / 1_000_000,
        "monthly_searches": " ".join(monthly),
    }


def _to_dict(message) -> dict:
    return MessageToDict(message._pb, preserving_proto_field_name=True)


def _parse(run: Run | None, results: list, metrics_attr: str) -> list[dict]:
    """Flatten raw API results into rows, checkpointing both sides."""
    if run:
        run.checkpoint("raw_response", [_to_dict(r) for r in results])
        run.step("parse the response into flat rows")
    rows = [_row(r.text, getattr(r, metrics_attr)) for r in results]
    if run:
        no_volume = sum(1 for r in rows if not r["avg_monthly_searches"])
        run.info("%d rows, %d with no search volume", len(rows), no_volume)
        run.info("total avg monthly searches: %s", f"{sum(r['avg_monthly_searches'] for r in rows):,}")
        run.checkpoint("parsed_rows", rows)
    return rows


def keyword_ideas(
    client: GoogleAdsClient,
    customer_id: str,
    seeds: list[str],
    url: str | None = None,
    geo_ids: list[str] = (GEO_US,),
    language_id: str = LANG_ENGLISH,
    limit: int | None = None,
    months: int = MAX_MONTHS,
    run: Run | None = None,
) -> list[dict]:
    """Expand seed keywords and/or a URL into related keyword ideas with metrics."""
    if run:
        run.step("build the GenerateKeywordIdeas request")
    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    _targeting(client, request, list(geo_ids), language_id, months)

    if seeds and url:
        request.keyword_and_url_seed.url = url
        request.keyword_and_url_seed.keywords.extend(seeds)
        seed_type = "keywords + URL"
    elif seeds:
        request.keyword_seed.keywords.extend(seeds)
        seed_type = "keywords"
    elif url:
        request.url_seed.url = url
        seed_type = "URL"
    else:
        raise ValueError("Provide at least one seed keyword or a URL.")
    if run:
        run.info("seed type: %s", seed_type)
        run.checkpoint("request", _to_dict(request))
        run.step("call KeywordPlanIdeaService (Keyword Planner)")

    service = client.get_service("KeywordPlanIdeaService")
    started = time.monotonic()
    results = []
    for idea in service.generate_keyword_ideas(request=request):
        results.append(idea)
        if limit and len(results) >= limit:
            break
    if run:
        run.info("%d ideas returned in %.1fs", len(results), time.monotonic() - started)
        if limit and len(results) >= limit:
            run.info("stopped at --limit %d; more ideas may exist", limit)
    return _parse(run, results, "keyword_idea_metrics")


def keyword_metrics(
    client: GoogleAdsClient,
    customer_id: str,
    keywords: list[str],
    geo_ids: list[str] = (GEO_US,),
    language_id: str = LANG_ENGLISH,
    months: int = MAX_MONTHS,
    run: Run | None = None,
) -> list[dict]:
    """Historical metrics for an exact list of keywords (no expansion)."""
    if run:
        run.step("build the GenerateKeywordHistoricalMetrics request")
    request = client.get_type("GenerateKeywordHistoricalMetricsRequest")
    request.customer_id = customer_id
    request.keywords.extend(keywords)
    _targeting(client, request, list(geo_ids), language_id, months)
    if run:
        run.checkpoint("request", _to_dict(request))
        run.step("call KeywordPlanIdeaService (Keyword Planner)")

    service = client.get_service("KeywordPlanIdeaService")
    started = time.monotonic()
    response = service.generate_keyword_historical_metrics(request=request)
    results = list(response.results)
    if run:
        run.info("%d of %d keywords returned in %.1fs", len(results), len(keywords), time.monotonic() - started)
        # Google folds close variants (plurals, misspellings) into one result
        returned = {r.text for r in results} | {v for r in results for v in r.close_variants}
        missing = [k for k in keywords if k.lower() not in returned]
        if missing:
            run.info("no exact match returned for: %s", ", ".join(missing))
    return _parse(run, results, "keyword_metrics")
