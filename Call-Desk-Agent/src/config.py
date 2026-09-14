"""Shared configuration + environment loading for the call-center agent.

Every tool/agent/UI module imports from here so that ``.env`` and ``config.json``
are loaded exactly once, from the repo root, regardless of the current working
directory. Import this module before anything that needs an API key.

    from src.config import CONFIG, REPO_ROOT
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# src/config.py -> parents[0] = src/, parents[1] = repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"
CONFIG_PATH = REPO_ROOT / "config.json"

# Load .env explicitly by path — find_dotenv's frame walk is unreliable under
# `python -m ...` and heredocs.
load_dotenv(dotenv_path=ENV_PATH)

# One root logging config for the whole app (tools, graph, UI). Every module
# uses ``logging.getLogger(__name__)``; set LOG_LEVEL=DEBUG/INFO/WARNING in .env
# or the shell to change verbosity (default INFO, so the [tool] dev logs show).
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)


def load_config() -> dict:
    """Read and return config.json."""
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


# Loaded once at import; shared by every module. ACTIVE_PROVIDER in the env
# overrides config.json's "active_provider" so you can switch providers for one
# run without editing the file (e.g. ACTIVE_PROVIDER=gemini streamlit run ...).
CONFIG: dict = load_config()
CONFIG["active_provider"] = os.environ.get("ACTIVE_PROVIDER", CONFIG["active_provider"])
