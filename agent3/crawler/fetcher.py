"""crawler/fetcher.py — Mission 6.

"Download a page without crashing, ever": safely fetches the homepage or any
internal page and returns a typed FetchResult (never raises for a bad page).

What it handles (Mission 6 acceptance criteria):
  - Sends an HTTP GET with a clear User-Agent and a request timeout.
  - Follows redirects and records the final URL.
  - Detects HTTP status codes and maps them to a FetchStatus.
  - Handles blocked / unavailable / slow / oversized sites gracefully.
  - Always stores the status code and an error reason when the fetch fails.
"""

import time
from typing import Optional

import requests

from agent3.crawler.models import FetchResult, FetchStatus
from agent3.common import config
from agent3.common import logging as log


def fetch_homepage(url: str) -> FetchResult:
    """Fetch a company's homepage. Entry point for the pipeline (Mission 6)."""
    return _fetch(url, page_kind="homepage")


def fetch_page(url: str) -> FetchResult:
    """Fetch any internal page. Reuses the same safe logic as the homepage."""
    return _fetch(url, page_kind="page")


def _fetch(url: str, page_kind: str = "page") -> FetchResult:
    """Perform one safe GET request and translate the outcome into a FetchResult.

    This function never raises for a network/HTTP problem — every failure mode is
    caught and returned as a FetchResult with the appropriate FetchStatus.
    """
    start = time.perf_counter()
    headers = {"User-Agent": config.USER_AGENT}

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        return _failure(
            url,
            FetchStatus.TIMEOUT,
            start,
            f"Request timed out after {config.REQUEST_TIMEOUT_SECONDS}s.",
            page_kind,
        )
    except requests.exceptions.TooManyRedirects:
        return _failure(url, FetchStatus.FAILED, start, "Too many redirects.", page_kind)
    except requests.exceptions.ConnectionError as exc:
        return _failure(url, FetchStatus.FAILED, start, f"Connection error: {exc}", page_kind)
    except requests.exceptions.RequestException as exc:
        return _failure(url, FetchStatus.FAILED, start, f"Request failed: {exc}", page_kind)
    except Exception as exc:  # last-resort guard — a fetch must never crash the scan
        return _failure(url, FetchStatus.FAILED, start, f"Unexpected error: {exc}", page_kind)

    return _from_response(url, response, start, page_kind)


def _from_response(url: str, response: requests.Response, start: float, page_kind: str) -> FetchResult:
    """Turn a completed HTTP response into a FetchResult."""
    elapsed_ms = _elapsed_ms(start)
    final_url = str(response.url)
    code = response.status_code
    status = _status_from_code(code, redirected=bool(response.history))

    # Reject pages larger than the configured limit so we never hold a huge blob.
    content_length = len(response.content or b"")
    if content_length > config.MAX_CONTENT_SIZE_BYTES:
        log.warning(
            "fetch_content_too_large",
            url=url,
            final_url=final_url,
            bytes=content_length,
            limit=config.MAX_CONTENT_SIZE_BYTES,
        )
        return FetchResult(
            url=url,
            final_url=final_url,
            status=FetchStatus.FAILED,
            http_status_code=code,
            html=None,
            elapsed_ms=elapsed_ms,
            error_reason=f"Content too large ({content_length} bytes).",
        )

    if status.is_ok:
        log.info(
            "fetch_ok",
            kind=page_kind,
            url=url,
            final_url=final_url,
            http_status=code,
            status=status.value,
            elapsed_ms=elapsed_ms,
        )
        return FetchResult(
            url=url,
            final_url=final_url,
            status=status,
            http_status_code=code,
            html=response.text,
            elapsed_ms=elapsed_ms,
            error_reason=None,
        )

    error_reason = f"HTTP {code} ({status.value})."
    log.warning(
        "fetch_failed",
        kind=page_kind,
        url=url,
        final_url=final_url,
        http_status=code,
        status=status.value,
        elapsed_ms=elapsed_ms,
    )
    return FetchResult(
        url=url,
        final_url=final_url,
        status=status,
        http_status_code=code,
        html=None,
        elapsed_ms=elapsed_ms,
        error_reason=error_reason,
    )


def _status_from_code(code: int, redirected: bool) -> FetchStatus:
    """Map an HTTP status code to a FetchStatus."""
    if 200 <= code < 300:
        return FetchStatus.REDIRECTED if redirected else FetchStatus.SUCCESS
    if code in (401, 403, 429):
        return FetchStatus.BLOCKED
    if code in (404, 410):
        return FetchStatus.NOT_FOUND
    if 500 <= code < 600:
        return FetchStatus.SERVER_ERROR
    return FetchStatus.FAILED


def _failure(url: str, status: FetchStatus, start: float, reason: str, page_kind: str) -> FetchResult:
    """Build a FetchResult for a request that never produced an HTTP response."""
    elapsed_ms = _elapsed_ms(start)
    log.warning(
        "fetch_failed",
        kind=page_kind,
        url=url,
        status=status.value,
        reason=reason,
        elapsed_ms=elapsed_ms,
    )
    return FetchResult(
        url=url,
        final_url=url,
        status=status,
        http_status_code=None,
        html=None,
        elapsed_ms=elapsed_ms,
        error_reason=reason,
    )


def _elapsed_ms(start: float) -> int:
    """Milliseconds elapsed since `start` (a time.perf_counter() timestamp)."""
    return int(round((time.perf_counter() - start) * 1000))
