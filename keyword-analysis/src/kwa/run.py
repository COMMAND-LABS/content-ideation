"""Per-run ID, step logging, and checkpoint files.

Each pipeline run gets a folder `checkpoints/<run_id>/` holding one numbered
file per step (the data as it looked at that step) plus `run.log`.
"""

import csv
import json
import logging
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path

from kwa.config import CHECKPOINT_DIR, PROJECT_ROOT


def new_run_id() -> str:
    """Timestamp plus 6 hex digits, e.g. 20260920-150337-a3f9c1."""
    return f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"


class Run:
    def __init__(self, command: str, run_id: str | None = None):
        self.id = run_id or new_run_id()  # --run-id: ../ideate.py gives both tools its own
        self.command = command
        self.dir = CHECKPOINT_DIR / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self._step = 0
        self._started = time.monotonic()

        self.log = logging.getLogger(f"kwa.{self.id}")
        self.log.setLevel(logging.INFO)
        self.log.propagate = False
        fmt = logging.Formatter(f"%(asctime)s [{self.id}] %(message)s", datefmt="%H:%M:%S")
        # stderr keeps stdout clean for the results table
        for handler in (logging.StreamHandler(sys.stderr), logging.FileHandler(self.dir / "run.log")):
            handler.setFormatter(fmt)
            self.log.addHandler(handler)

        self.log.info("run started: kwa %s", command)

    def step(self, message: str, *args) -> None:
        """Log the start of a pipeline step."""
        self._step += 1
        self.log.info(f"step {self._step}: {message}", *args)

    def info(self, message: str, *args) -> None:
        """Log a detail within the current step."""
        self.log.info(f"    {message}", *args)

    def checkpoint(self, name: str, data) -> Path:
        """Save the data for the current step.

        A list of flat dicts is written as CSV; anything else as JSON.
        """
        tabular = (
            isinstance(data, list)
            and data
            and all(isinstance(r, dict) and not any(isinstance(v, (dict, list)) for v in r.values()) for r in data)
        )
        path = self.dir / f"{self._step:02d}_{name}.{'csv' if tabular else 'json'}"
        if tabular:
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
                writer.writeheader()
                writer.writerows(data)
        else:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

        size = f"{len(data)} rows" if isinstance(data, list) else f"{len(data)} fields"
        self.info("checkpoint -> %s (%s)", path.relative_to(PROJECT_ROOT), size)
        return path

    def finish(self) -> None:
        self.log.info("run finished in %.1fs, checkpoints in %s/", time.monotonic() - self._started, self.dir.relative_to(PROJECT_ROOT))
