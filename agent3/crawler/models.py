"""crawler/models.py — Shared data contracts for the crawl layer.

Defines FetchStatus + FetchResult, the typed objects `fetcher.py` produces and
everyone downstream (link_discovery, text_extractor, orchestrator) consumes.
See Agent3_Architecture.md §4.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FetchStatus(str, Enum):
    """Outcome of a single fetch attempt.

    Failures are *data*, not exceptions — the fetcher always returns one of
    these instead of raising, so one bad page never crashes a scan.
    """

    SUCCESS = "success"            # 2xx, no redirect
    REDIRECTED = "redirected"      # 2xx, but reached after one or more redirects
    TIMEOUT = "timeout"            # request took longer than the configured timeout
    BLOCKED = "blocked"            # 401 / 403 / 429 — site refused us
    NOT_FOUND = "not_found"        # 404 / 410 — page does not exist
    SERVER_ERROR = "server_error"  # 5xx — the site itself errored
    FAILED = "failed"              # connection error / unexpected error / other

    @property
    def is_ok(self) -> bool:
        """True when the fetch produced usable HTML (SUCCESS or REDIRECTED)."""
        return self in (FetchStatus.SUCCESS, FetchStatus.REDIRECTED)

    @property
    def is_retryable(self) -> bool:
        """Transient failures Agent 1 could retry later (timeouts, 5xx, conn errors)."""
        return self in (FetchStatus.TIMEOUT, FetchStatus.SERVER_ERROR, FetchStatus.FAILED)


@dataclass
class FetchResult:
    """Everything the rest of the pipeline needs to know about one fetch.

    Attributes:
        url: The URL we were asked to fetch.
        final_url: Where we actually ended up (differs from `url` after redirects).
        status: A FetchStatus describing the outcome.
        http_status_code: The HTTP status code, or None if we never got a response.
        html: The page HTML, only populated when `status.is_ok`.
        elapsed_ms: How long the fetch took, in milliseconds.
        error_reason: Human-readable reason when the fetch was not OK, else None.
    """

    url: str
    final_url: str
    status: FetchStatus
    http_status_code: Optional[int] = None
    html: Optional[str] = None
    elapsed_ms: int = 0
    error_reason: Optional[str] = None
