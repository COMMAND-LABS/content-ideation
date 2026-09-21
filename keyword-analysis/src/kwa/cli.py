"""Command line entry point: `uv run kwa <command>`."""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from kwa import keywords as kw
from kwa import trends
from kwa.config import DATA_DIR, ads_client, customer_id
from kwa.run import Run


def _read_terms(args) -> list[str]:
    terms = list(args.terms)
    if args.file:
        lines = Path(args.file).read_text().splitlines()
        terms += [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    return terms


def _start_run(args, terms: list[str]) -> tuple[Run, str]:
    """Create the run and checkpoint the resolved inputs as step 1."""
    run = args.run = Run(args.command, args.run_id)
    cid = customer_id(args.customer_id)
    run.step("resolve inputs")
    inputs = {
        "run_id": run.id,
        "command": args.command,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "customer_id": cid,
        "terms": terms,
        "url": getattr(args, "url", None),
        "geo_ids": args.geo,
        "language_id": args.lang,
        "limit": getattr(args, "limit", None),
        "months": args.months,
    }
    run.info("%d terms: %s", len(terms), ", ".join(terms[:8]) + (" ..." if len(terms) > 8 else ""))
    if inputs["url"]:
        run.info("url: %s", inputs["url"])
    run.info("customer %s, geo %s, language %s", cid, " ".join(args.geo), args.lang)
    run.info("history window: last %d completed months", args.months)
    run.checkpoint("inputs", inputs)
    return run, cid


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else kw.FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _pct(value) -> str:
    if value == "":
        return "-"
    # a near-zero baseline makes the exact figure meaningless
    return ">+999%" if value > 999 else f"{value:+.0f}%"


def _write(rows: list[dict], out: str | None, run: Run) -> None:
    run.step("measure the trend: last 12 months vs the 12 before")
    # keep the long monthly_searches column last so the CSV stays readable
    rows = [
        {k: v for k, v in r.items() if k != "monthly_searches"}
        | trends.measure(r["monthly_searches"])
        | {"monthly_searches": r["monthly_searches"]}
        for r in rows
    ]
    counts = {}
    for r in rows:
        counts[r["floor_trend"]] = counts.get(r["floor_trend"], 0) + 1
    run.info("floor trend: %s", ", ".join(f"{n} {label}" for label, n in sorted(counts.items())))
    run.checkpoint("trend_metrics", rows)

    run.step("sort by search volume and write the final CSVs")
    rows.sort(key=lambda r: r["avg_monthly_searches"], reverse=True)
    run.checkpoint("final_sorted", rows)
    monthly = trends.monthly_wide(rows)
    run.checkpoint("monthly_wide", monthly)

    if out:
        path = Path(out)
    else:
        DATA_DIR.mkdir(exist_ok=True)
        path = DATA_DIR / f"{run.command}-{run.id}.csv"
    monthly_path = path.with_name(f"{path.stem}-monthly.csv")
    _write_csv(path, rows)
    _write_csv(monthly_path, monthly)

    print(f"{'avg/mo':>10}  {'YoY':>6}  {'floor':>6}  {'floor trend':<11}  keyword")
    for r in rows[:25]:
        print(
            f"{r['avg_monthly_searches']:>10,}  {_pct(r['yoy_change_pct']):>6}  "
            f"{_pct(r['floor_change_pct']):>6}  {r['floor_trend']:<11}  {r['keyword']}"
        )
    print(f"\n{len(rows)} keywords -> {path}")
    print(f"month-by-month volumes -> {monthly_path}")
    run.info("output -> %s", path)
    run.info("output -> %s", monthly_path)
    run.finish()


def cmd_auth(args) -> None:
    from kwa.auth import run_auth

    run_auth(args.login_customer_id)


def cmd_check(args) -> None:
    """Verify credentials by listing the Ads accounts this login can reach."""
    client = ads_client()
    service = client.get_service("CustomerService")
    names = service.list_accessible_customers().resource_names
    print("Credentials OK. Accessible accounts:")
    for name in names:
        print(f"  {name.split('/')[-1]}")
    if not names:
        print("  (none - is this Google login attached to an Ads account?)")


def cmd_ideas(args) -> None:
    terms = _read_terms(args)
    run, cid = _start_run(args, terms)
    rows = kw.keyword_ideas(
        ads_client(),
        cid,
        terms,
        url=args.url,
        geo_ids=args.geo,
        language_id=args.lang,
        limit=args.limit,
        months=args.months,
        run=run,
    )
    _write(rows, args.out, run)


def cmd_metrics(args) -> None:
    terms = _read_terms(args)
    if not terms:
        raise SystemExit("Provide keywords as arguments or with --file.")
    run, cid = _start_run(args, terms)
    rows = kw.keyword_metrics(
        ads_client(),
        cid,
        terms,
        geo_ids=args.geo,
        language_id=args.lang,
        months=args.months,
        run=run,
    )
    _write(rows, args.out, run)


def _add_lookup_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("terms", nargs="*", help="keywords")
    p.add_argument("-f", "--file", help="text file with one keyword per line")
    p.add_argument("--geo", nargs="+", default=[kw.GEO_US], help="geo target IDs (default 2840 = US)")
    p.add_argument("--lang", default=kw.LANG_ENGLISH, help="language ID (default 1000 = English)")
    p.add_argument(
        "--months",
        type=int,
        default=kw.MAX_MONTHS,
        choices=range(1, kw.MAX_MONTHS + 1),
        metavar="N",
        help="months of search history to fetch (default and max 48; trends need 24+)",
    )
    p.add_argument("--customer-id", help="Ads account to run against")
    p.add_argument("-o", "--out", help="CSV output path (default data/<cmd>-<run_id>.csv)")
    p.add_argument("--run-id", help="save the checkpoints under this ID instead of a new one")


def main() -> None:
    parser = argparse.ArgumentParser(prog="kwa", description="Keyword analysis via the Google Ads API")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("auth", help="run the OAuth flow and write google-ads.yaml")
    p.add_argument("--login-customer-id", help="also store this login_customer_id")
    p.set_defaults(func=cmd_auth)

    p = sub.add_parser("check", help="verify Ads credentials; list accessible accounts")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("ideas", help="expand seed keywords / a URL into keyword ideas")
    _add_lookup_args(p)
    p.add_argument("--url", help="page or site to seed ideas from")
    p.add_argument("--limit", type=int, help="max ideas to fetch")
    p.set_defaults(func=cmd_ideas)

    p = sub.add_parser("metrics", help="search volume for an exact keyword list")
    _add_lookup_args(p)
    p.set_defaults(func=cmd_metrics)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as ex:
        from google.ads.googleads.errors import GoogleAdsException

        run = getattr(args, "run", None)
        if not isinstance(ex, GoogleAdsException):
            if run:
                run.log.exception("run failed")
            raise
        if run:
            for error in ex.failure.errors:
                run.log.error("run failed (request ID %s): %s", ex.request_id, error.message)
        print(f"Google Ads API request failed (request ID {ex.request_id}):", file=sys.stderr)
        for error in ex.failure.errors:
            print(f"  {error.error_code}: {error.message}".replace("\n", " "), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
