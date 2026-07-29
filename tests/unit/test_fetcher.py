"""Mission 6 — tests for crawler/fetcher.py.

Exactly 6 strong tests:
  1 FAKE  — fully mocked, covers every FetchStatus branch offline & fast.
  5 REAL  — hit live websites end-to-end (marked `network`).

The real tests skip gracefully if the machine is offline, so they never turn a
working implementation into a red build.

  pytest -m network         # only the 5 real-site tests
  pytest -m "not network"   # only the fake test
"""

from unittest import mock

import pytest
import requests

from agent3.crawler import fetcher
from agent3.crawler.models import FetchResult, FetchStatus


# =============================================================================
# 1) FAKE TEST — mocked network, exercises every branch of the fetcher
# =============================================================================

class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code=200, url="https://example.com/", history=None,
                 text="<html><body>hi</body></html>"):
        self.status_code = status_code
        self.url = url
        self.history = history or []
        self.text = text
        self.content = text.encode("utf-8")


def _patch_get(*, response=None, side_effect=None):
    kwargs = {"side_effect": side_effect} if side_effect is not None else {"return_value": response}
    return mock.patch.object(fetcher.requests, "get", **kwargs)


def test_fake_covers_every_status_branch():
    """One strong mocked test: every outcome maps correctly and NEVER raises."""

    # --- 200 OK, no redirect -> SUCCESS, html + code stored, no error ---
    with _patch_get(response=FakeResponse(status_code=200)):
        r = fetcher.fetch_homepage("https://example.com")
    assert r.status is FetchStatus.SUCCESS and r.status.is_ok
    assert r.http_status_code == 200
    assert r.html and "hi" in r.html
    assert r.error_reason is None
    assert r.final_url == "https://example.com/"
    assert r.elapsed_ms >= 0

    # --- 200 after a 301 -> REDIRECTED, final_url updated ---
    redirected = FakeResponse(status_code=200, url="https://www.example.com/",
                              history=[FakeResponse(status_code=301)])
    with _patch_get(response=redirected):
        r = fetcher.fetch_homepage("https://example.com")
    assert r.status is FetchStatus.REDIRECTED and r.status.is_ok
    assert r.final_url == "https://www.example.com/"

    # --- 404 -> NOT_FOUND, no html, code + reason stored ---
    with _patch_get(response=FakeResponse(status_code=404)):
        r = fetcher.fetch_homepage("https://example.com/missing")
    assert r.status is FetchStatus.NOT_FOUND
    assert r.http_status_code == 404 and r.html is None and r.error_reason

    # --- 403 -> BLOCKED ---
    with _patch_get(response=FakeResponse(status_code=403)):
        r = fetcher.fetch_homepage("https://example.com")
    assert r.status is FetchStatus.BLOCKED and r.http_status_code == 403

    # --- 500 -> SERVER_ERROR (retryable) ---
    with _patch_get(response=FakeResponse(status_code=500)):
        r = fetcher.fetch_homepage("https://example.com")
    assert r.status is FetchStatus.SERVER_ERROR and r.status.is_retryable

    # --- Timeout -> TIMEOUT, no code, reason saved, does not crash ---
    with _patch_get(side_effect=requests.exceptions.Timeout()):
        r = fetcher.fetch_homepage("https://slow.example.com")
    assert r.status is FetchStatus.TIMEOUT
    assert r.http_status_code is None and r.error_reason and r.status.is_retryable

    # --- Connection error -> FAILED ---
    with _patch_get(side_effect=requests.exceptions.ConnectionError("boom")):
        r = fetcher.fetch_homepage("https://unreachable.example.com")
    assert r.status is FetchStatus.FAILED and r.error_reason

    # --- Unexpected error -> FAILED (last-resort guard, never crashes) ---
    with _patch_get(side_effect=ValueError("weird")):
        r = fetcher.fetch_homepage("https://example.com")
    assert r.status is FetchStatus.FAILED and r.error_reason

    # --- Oversized page -> FAILED with "too large" reason ---
    with mock.patch.object(fetcher.config, "MAX_CONTENT_SIZE_BYTES", 10):
        with _patch_get(response=FakeResponse(status_code=200, text="x" * 100)):
            r = fetcher.fetch_homepage("https://example.com")
    assert r.status is FetchStatus.FAILED
    assert r.http_status_code == 200 and "too large" in r.error_reason.lower()

    # --- fetch_page reuses the same logic ---
    with _patch_get(response=FakeResponse(status_code=200)):
        r = fetcher.fetch_page("https://example.com/about")
    assert r.status is FetchStatus.SUCCESS


# =============================================================================
# 2-6) REAL TESTS — live network requests against real websites
# =============================================================================

def _skip_if_unreachable(result: FetchResult) -> None:
    """Skip (not fail) when the failure is clearly a local network problem."""
    if result.http_status_code is None and result.status in (
        FetchStatus.TIMEOUT,
        FetchStatus.FAILED,
    ):
        pytest.skip(f"network unavailable: {result.error_reason}")


@pytest.mark.network
def test_real_example_com_success():
    """example.com — the classic stable test site: clean 200 + known content."""
    r = fetcher.fetch_homepage("https://example.com")
    _skip_if_unreachable(r)

    assert r.status is FetchStatus.SUCCESS
    assert r.http_status_code == 200
    assert r.html and "Example Domain" in r.html
    assert r.error_reason is None
    assert r.final_url.startswith("https://example.com")
    assert r.elapsed_ms >= 0


@pytest.mark.network
def test_real_github_http_to_https_redirect():
    """github.com over http — proves redirects are followed and recorded."""
    r = fetcher.fetch_homepage("http://github.com")
    _skip_if_unreachable(r)

    assert r.status is FetchStatus.REDIRECTED
    assert r.status.is_ok
    assert r.http_status_code == 200
    assert r.final_url.startswith("https://")
    assert r.html


@pytest.mark.network
def test_real_404_page():
    """A real 404 on a live site — code + reason stored, no html, no crash."""
    r = fetcher.fetch_homepage("https://example.com/nonexistent-page-xyz123")
    _skip_if_unreachable(r)

    assert r.status is FetchStatus.NOT_FOUND
    assert r.http_status_code == 404
    assert r.html is None
    assert r.error_reason


@pytest.mark.network
def test_real_wikipedia_success():
    """A large real homepage — fetch succeeds and returns substantial html."""
    r = fetcher.fetch_homepage("https://www.wikipedia.org")
    _skip_if_unreachable(r)

    assert r.status is FetchStatus.SUCCESS
    assert r.http_status_code == 200
    assert r.html and "Wikipedia" in r.html
    assert len(r.html) > 1000


@pytest.mark.network
def test_real_python_org_success_via_fetch_page():
    """python.org via fetch_page() — the page path reuses the same safe logic."""
    r = fetcher.fetch_page("https://www.python.org")
    _skip_if_unreachable(r)

    assert r.status.is_ok
    assert r.http_status_code == 200
    assert r.html and "Python" in r.html
    assert r.error_reason is None
