"""Mission 5 — unit tests for crawler/url_normalizer.py.

Pure logic, no network involved, so every test runs offline and fast.
"""

import pytest

from agent3.crawler import url_normalizer


# =============================================================================
# Normalization — valid inputs
# =============================================================================

@pytest.mark.parametrize(
    "raw_url, expected",
    [
        ("example.com", "https://example.com"),
        ("https://www.example.com/", "https://www.example.com"),
        ("http://example.com/about", "http://example.com/about"),
        ("www.example.com", "https://www.example.com"),
        ("//example.com/about", "https://example.com/about"),
    ],
)
def test_normalizes_examples_from_the_spec(raw_url, expected):
    result = url_normalizer.normalize_url(raw_url)
    assert result.is_valid
    assert result.url == expected


def test_strips_unnecessary_trailing_slash_on_a_deep_path():
    result = url_normalizer.normalize_url("https://example.com/about/")
    assert result.is_valid
    assert result.url == "https://example.com/about"


def test_keeps_meaningful_path_without_a_trailing_slash():
    result = url_normalizer.normalize_url("https://example.com/about")
    assert result.url == "https://example.com/about"


def test_lowercases_scheme_and_host_but_preserves_path_case():
    result = url_normalizer.normalize_url("HTTPS://Example.COM/AboutUs")
    assert result.is_valid
    assert result.url == "https://example.com/AboutUs"
    assert result.domain == "example.com"


def test_strips_default_ports():
    assert url_normalizer.normalize_url("http://example.com:80/").url == "http://example.com"
    assert url_normalizer.normalize_url("https://example.com:443/").url == "https://example.com"


def test_keeps_non_default_port():
    result = url_normalizer.normalize_url("http://example.com:8080/status")
    assert result.url == "http://example.com:8080/status"


def test_keeps_query_string_but_drops_fragment():
    result = url_normalizer.normalize_url("https://example.com/search?q=hi#section")
    assert result.url == "https://example.com/search?q=hi"


def test_extracts_domain():
    assert url_normalizer.extract_domain("https://www.example.com/about") == "www.example.com"
    assert url_normalizer.extract_domain("example.com") == "example.com"


# =============================================================================
# Rejection — invalid / dangerous inputs
# =============================================================================

@pytest.mark.parametrize(
    "raw_url",
    [
        "",
        "   ",
        None,
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "mailto:someone@example.com",
        "ftp://files.example.com",
        "http://",
        "https:///about",
        "http://user:pass@example.com",
        "http://example",
        "http://exa mple.com",
        "http://localhost",
        "http://127.0.0.1",
        "http://169.254.169.254",
        "http://[::1]",
        "http://10.0.0.5",
        "https://" + "a" * 3000 + ".com",
    ],
)
def test_rejects_invalid_or_dangerous_urls(raw_url):
    result = url_normalizer.normalize_url(raw_url)
    assert not result.is_valid
    assert result.url is None
    assert result.domain is None
    assert result.error_reason


def test_original_url_is_preserved_on_rejection():
    result = url_normalizer.normalize_url("javascript:alert(1)")
    assert result.original_url == "javascript:alert(1)"


# =============================================================================
# is_internal_url — same-site vs external-site link filtering
# =============================================================================

def test_is_internal_url_true_for_same_domain():
    assert url_normalizer.is_internal_url("https://example.com/pricing", "example.com")


def test_is_internal_url_tolerates_www_redirect_in_either_direction():
    assert url_normalizer.is_internal_url("https://www.example.com/pricing", "example.com")
    assert url_normalizer.is_internal_url("https://example.com/pricing", "www.example.com")


def test_is_internal_url_false_for_external_domain():
    assert not url_normalizer.is_internal_url("https://other.com/pricing", "example.com")


def test_is_internal_url_false_for_a_subdomain_that_is_not_www():
    assert not url_normalizer.is_internal_url("https://blog.example.com/post", "example.com")


def test_is_internal_url_false_for_an_invalid_candidate():
    assert not url_normalizer.is_internal_url("javascript:alert(1)", "example.com")
