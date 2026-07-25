"""common/config.py — All settings in one place.

Single source of truth for timeouts, limits, user-agent, and LLM model name.
Every other module imports its knobs from here instead of hardcoding values.

Reference (see Agent3_Architecture.md §9):
    REQUEST_TIMEOUT_SECONDS, MAX_PAGES_PER_SCAN, MAX_CRAWL_DEPTH,
    MAX_CONTENT_SIZE_BYTES, CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS,
    USER_AGENT, LLM_MODEL, LLM_TEMPERATURE
"""

import os

# Mission 7 may return at most 15 internal pages per company.
#
# The assignment recommends a system-controlled limit between 10 and 20.
# The value is fixed by the application and is not accepted from the user.
MAX_PAGES_PER_SCAN = 15