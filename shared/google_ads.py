"""Google Ads API access: the client, which account to ask, and the one-time login.

    uv run python -m shared.google_ads login     opens a browser and writes google-ads.yaml
    uv run python -m shared.google_ads check     verifies the login and lists your Ads account IDs
"""

import json
import os
import sys

import yaml

from shared import settings

ADS_SCOPE = "https://www.googleapis.com/auth/adwords"


def is_set_up() -> bool:
    return settings.GOOGLE_ADS_YAML.exists()


def client():
    from google.ads.googleads.client import GoogleAdsClient

    if not is_set_up():
        raise SystemExit("google-ads.yaml not found. Run `uv run python -m shared.google_ads login` first (see the README).")
    return GoogleAdsClient.load_from_storage(str(settings.GOOGLE_ADS_YAML))


def customer_id() -> str:
    """The Ads account keyword requests run against: GOOGLE_ADS_CUSTOMER_ID in .env, else login_customer_id."""
    saved = yaml.safe_load(settings.GOOGLE_ADS_YAML.read_text()) or {}
    digits = str(os.getenv("GOOGLE_ADS_CUSTOMER_ID") or saved.get("login_customer_id") or "").replace("-", "").strip()
    if not digits.isdigit():
        raise SystemExit("No customer ID. Set GOOGLE_ADS_CUSTOMER_ID in .env, or login_customer_id in google-ads.yaml.")
    return digits


def login():
    """One-time OAuth flow: get a refresh token and write google-ads.yaml."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets = sorted(settings.ROOT.glob("client_secret*.json"))
    if len(secrets) != 1:
        raise SystemExit(f"Put exactly one client_secret*.json (the Desktop app OAuth client from the Cloud Console) in {settings.ROOT}.")
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets[0]), scopes=[ADS_SCOPE])
    # offline + consent forces Google to issue a refresh token even if this client was authorized before.
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not credentials.refresh_token:
        raise SystemExit("Google returned no refresh token; run it again and approve the consent screen.")

    installed = json.loads(secrets[0].read_text())["installed"]
    saved = (yaml.safe_load(settings.GOOGLE_ADS_YAML.read_text()) or {}) if is_set_up() else {}
    saved.update(client_id=installed["client_id"], client_secret=installed["client_secret"], refresh_token=credentials.refresh_token, use_proto_plus=True)
    settings.GOOGLE_ADS_YAML.write_text(yaml.safe_dump(saved, sort_keys=False))
    settings.GOOGLE_ADS_YAML.chmod(0o600)
    print("Refresh token saved to google-ads.yaml")
    if not saved.get("login_customer_id"):
        print('Next: run `uv run python -m shared.google_ads check`, then add\n  login_customer_id: "1234567890"\nto google-ads.yaml.')


def check():
    """Verify the login by listing the Ads accounts it can reach."""
    names = client().get_service("CustomerService").list_accessible_customers().resource_names
    print("Credentials OK. Accessible accounts:")
    for name in names:
        print(f"  {name.split('/')[-1]}")
    if not names:
        print("  (none - is this Google login attached to an Ads account?)")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("login", "check"):
        raise SystemExit(__doc__)
    login() if command == "login" else check()
