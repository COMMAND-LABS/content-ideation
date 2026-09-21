"""Paths, settings, and client construction."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADS_CONFIG_PATH = PROJECT_ROOT / "google-ads.yaml"
DATA_DIR = PROJECT_ROOT / "data"
CHECKPOINT_DIR = PROJECT_ROOT / "checkpoints"

ADS_SCOPE = "https://www.googleapis.com/auth/adwords"

load_dotenv(PROJECT_ROOT.parent / ".env")  # the one .env of the whole project


def find_client_secret() -> Path:
    matches = sorted(PROJECT_ROOT.glob("client_secret*.json"))
    if not matches:
        raise SystemExit(
            f"No client_secret*.json found in {PROJECT_ROOT}. Download the "
            "Desktop app OAuth client JSON from the Cloud Console."
        )
    if len(matches) > 1:
        raise SystemExit(
            "Multiple client_secret*.json files found; keep only one:\n"
            + "\n".join(f"  {m.name}" for m in matches)
        )
    return matches[0]


def load_ads_config() -> dict:
    if not ADS_CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(ADS_CONFIG_PATH.read_text()) or {}


def ads_client() -> GoogleAdsClient:
    if not ADS_CONFIG_PATH.exists():
        raise SystemExit("google-ads.yaml not found. Run `uv run kwa auth` first.")
    return GoogleAdsClient.load_from_storage(str(ADS_CONFIG_PATH))


def _digits(value) -> str:
    return str(value or "").replace("-", "").strip()


def customer_id(override: str | None = None) -> str:
    """Account keyword requests run against: flag > .env > login_customer_id."""
    cid = (
        _digits(override)
        or _digits(os.getenv("GOOGLE_ADS_CUSTOMER_ID"))
        or _digits(load_ads_config().get("login_customer_id"))
    )
    if not cid.isdigit():
        raise SystemExit(
            "No customer ID. Pass --customer-id, set GOOGLE_ADS_CUSTOMER_ID in "
            "../.env, or set login_customer_id in google-ads.yaml."
        )
    return cid
