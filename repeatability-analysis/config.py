"""The tool's settings: everything in ../config.py, plus the API key from ../.env and where the tool saves its files."""

import os
import runpy
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# --- Every tunable parameter: MY_CHANNEL, CHANNELS_TO_SCAN, OUTLIER_MULTIPLE... ---
if not (ROOT / "config.py").exists():
    raise SystemExit("No config.py yet. In the project root, run `cp config.py.example config.py`, then set your channel in it.")
globals().update({name: value for name, value in runpy.run_path(str(ROOT / "config.py")).items() if name.isupper()})

# --- API keys (set these in ../.env) ---
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
# OPENAI_API_KEY / ANTHROPIC_API_KEY are read from the environment by their SDKs.

# --- Where the tool saves its files ---
CACHE_DIR = "cache"  # YouTube and LLM responses, kept for CACHE_HOURS
CHECKPOINT_DIR = "checkpoints"  # each step's output is dumped here as <run_id>_step_<n>.json
OUTPUT_DIR = "output"  # final results land here as final_output_<run_id>.json
