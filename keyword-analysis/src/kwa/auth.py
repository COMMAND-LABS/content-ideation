"""One-time OAuth flow: obtain a refresh token and write google-ads.yaml."""

import json

import yaml
from google_auth_oauthlib.flow import InstalledAppFlow

from kwa.config import ADS_CONFIG_PATH, ADS_SCOPE, find_client_secret, load_ads_config


def run_auth(login_customer_id: str | None = None) -> None:
    secret_path = find_client_secret()
    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), scopes=[ADS_SCOPE])
    # offline + consent forces Google to issue a refresh token even if this
    # client was authorized before.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        raise SystemExit("Google returned no refresh token; re-run and approve the consent screen.")

    installed = json.loads(secret_path.read_text())["installed"]
    config = load_ads_config()
    config.update(
        client_id=installed["client_id"],
        client_secret=installed["client_secret"],
        refresh_token=creds.refresh_token,
        use_proto_plus=True,
    )
    if login_customer_id:
        config["login_customer_id"] = login_customer_id.replace("-", "")

    ADS_CONFIG_PATH.write_text(yaml.safe_dump(config, sort_keys=False))
    ADS_CONFIG_PATH.chmod(0o600)
    print(f"Refresh token saved to {ADS_CONFIG_PATH.name}")
    if not config.get("login_customer_id"):
        print(
            "Next: run `uv run kwa check` to list your account IDs, then add\n"
            '  login_customer_id: "1234567890"\n'
            f"to {ADS_CONFIG_PATH.name}."
        )
