"""Dumps the data produced by each step to checkpoints/<run_id>_step_<n>.json for debugging."""

import json
import secrets
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

import config


def new_run_id() -> str:
    """Timestamp + 4 character hex code, e.g. "20260919-143022-a3f9"."""
    return f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def save(run_id: str, step: int, data) -> Path:
    path = Path(config.CHECKPOINT_DIR) / f"{run_id}_step_{step}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, default=_to_jsonable, indent=2, ensure_ascii=False))
    return path


def _to_jsonable(value):
    """Called by json.dumps for anything it can't serialize itself."""
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Cannot checkpoint {type(value).__name__}")
