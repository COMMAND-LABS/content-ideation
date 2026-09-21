"""A run: its ID, its folder, and one readable file per step.

runs/<run id>/run.json            which pipeline, the seeds and every setting the run used
runs/<run id>/01_<step>.json      {"step", "summary", "input", "output"}: the step in numbers, what went in, what came out
runs/<run id>/01_a_<step>.json    a step with two views of its result saves them as parts a and b
runs/<run id>/scoreboard.csv      the final result
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from shared import settings
from shared.settings import config

SAMPLE = 3  # a long input is saved as its first few items: it is the previous step's output, which is saved in full


class Run:
    def __init__(self, pipeline: str, seeds: list[str] = ()):
        self.id = f"{datetime.now():%Y%m%d-%H%M%S}"
        self.folder = Path(settings.RUNS_DIR) / self.id
        self.folder.mkdir(parents=True)
        self.steps = 0
        everything = {name: value for name, value in vars(config).items() if name.isupper()}
        info = {"run": self.id, "pipeline": pipeline, "seeds": list(seeds), "settings": everything}
        (self.folder / "run.json").write_text(json.dumps(info, indent=2, ensure_ascii=False))
        print(f"Run {self.id}: every step is saved in {self.folder.relative_to(settings.ROOT)}/")

    def step(self, title: str):
        """Announce the next step."""
        self.steps += 1
        print(f"\n=== STEP {self.steps}: {title} ===\n", flush=True)

    def save(self, name: str, input, output, summary: dict, part: str = ""):
        """Save what went into the current step and what came out, with a summary in numbers on top. Returns the output.

        A step that saves two views of its result gives each a `part`: 01_a_<name>.json, 01_b_<name>.json.
        """
        path = self.folder / f"{self.steps:02d}_{part + '_' if part else ''}{name}.json"
        path.write_text(json.dumps({"step": name, "summary": summary, "input": sample(input), "output": output}, indent=2, ensure_ascii=False))
        print(f"  saved {path.relative_to(settings.ROOT)}", flush=True)
        for label, number in summary.items():
            print(f"  {number:>8,}   {label}", flush=True)
        return output


def tally(rows: list[dict], key: str) -> dict:
    """How many rows have each value: tally(keywords, "trend") -> {"rising": 12, "flat": 40, ...}"""
    return dict(Counter(row[key] for row in rows))


def sample(data):
    """Long lists cut down to their first items, so a step's file stays readable."""
    if isinstance(data, dict):
        return {key: sample(value) for key, value in data.items()}
    if isinstance(data, list) and len(data) > SAMPLE:
        return [sample(item) for item in data[:SAMPLE]] + [f"... and {len(data) - SAMPLE} more"]
    if isinstance(data, list):
        return [sample(item) for item in data]
    return data
