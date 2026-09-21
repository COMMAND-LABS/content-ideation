"""Disk cache for API responses, so repeat runs don't spend YouTube quota or LLM tokens.

Entries live in config.CACHE_DIR for config.CACHE_HOURS. Run `main.py --refresh` to
ignore what's cached and pull (and re-cache) the latest data.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Callable

import config

refresh = False  # set by `main.py --refresh`


def get_or_fetch(key: dict, fetch: Callable[[], dict]) -> dict:
    """The cached value for `key` if it is fresh, otherwise the result of fetch() (which is then cached)."""
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]
    path = Path(config.CACHE_DIR) / f"{digest}.json"

    if not refresh and path.exists() and _age_hours(path) < config.CACHE_HOURS:
        return json.loads(path.read_text())["value"]

    value = fetch()
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"key": key, "value": value}, indent=2, ensure_ascii=False))
    return value


def _age_hours(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 3600
