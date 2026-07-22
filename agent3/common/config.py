"""common/config.py — All settings in one place.

Single source of truth for timeouts, limits, user-agent, and LLM model name.
Every other module imports its knobs from here instead of hardcoding values.
Values can be overridden via environment variables (handy for tests/deploys).

Reference (see Agent3_Architecture.md §9).
"""

import os


def _env_int(name: str, default: int) -> int:
    """Read an int from the environment, falling back to `default` if unset/invalid."""
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


# --- Crawler / fetching (Missions 6-7) ---
REQUEST_TIMEOUT_SECONDS = _env_int("AGENT3_REQUEST_TIMEOUT_SECONDS", 15)
MAX_PAGES_PER_SCAN = _env_int("AGENT3_MAX_PAGES_PER_SCAN", 15)
MAX_CRAWL_DEPTH = _env_int("AGENT3_MAX_CRAWL_DEPTH", 2)
MAX_CONTENT_SIZE_BYTES = _env_int("AGENT3_MAX_CONTENT_SIZE_BYTES", 5_000_000)
USER_AGENT = os.environ.get("AGENT3_USER_AGENT", "Agent3-WebsiteIntelligenceBot/1.0")

# --- Chunking (Mission 10) ---
CHUNK_SIZE_TOKENS = _env_int("AGENT3_CHUNK_SIZE_TOKENS", 600)
CHUNK_OVERLAP_TOKENS = _env_int("AGENT3_CHUNK_OVERLAP_TOKENS", 80)

# --- AI extraction (Mission 11) ---
LLM_MODEL = os.environ.get("AGENT3_LLM_MODEL", "claude-sonnet-4-6")
LLM_TEMPERATURE = 0.0  # deterministic structured extraction
