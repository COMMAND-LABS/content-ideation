"""Loads your settings (config.py) and your API keys (.env), and says where things are saved."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT))  # so `import config` finds the config.py in the project folder
try:
    import config  # noqa: E402,F401  (every module gets the settings with: from shared.settings import config)
except ModuleNotFoundError:
    raise SystemExit("No config.py yet. Run `cp config.py.example config.py`, then set your channel in it.")

CACHE_DIR = ROOT / "cache"  # YouTube and LLM responses, kept for CACHE_HOURS
RUNS_DIR = ROOT / "runs"  # one folder per run, one file per step
GOOGLE_ADS_YAML = ROOT / "google-ads.yaml"  # written by `uv run python -m shared.google_ads login`


def api_key(name: str) -> str:
    key = os.environ.get(name, "")
    if not key:
        raise SystemExit(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return key
