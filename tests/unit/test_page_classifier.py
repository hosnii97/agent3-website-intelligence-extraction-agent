"""Mission 8 — unit tests for classification/page_classifier.py."""

"""Unit tests for Mission 8 page classification."""

import pytest

from agent3.classification import page_classifier
from agent3.classification.page_classifier import PageType

classify_page = page_classifier.classify_page

@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com", PageType.HOMEPAGE),
        ("https://example.com/", PageType.HOMEPAGE),
        ("https://example.com/about-us", PageType.ABOUT),
        ("https://example.com/pricing", PageType.PRICING),
        ("https://example.com/services", PageType.SERVICE),
        ("https://example.com/products/platform", PageType.PRODUCT),
        ("https://example.com/blog/article-1", PageType.BLOG),
        ("https://example.com/case-studies/acme", PageType.CASE_STUDY),
        ("https://example.com/customers", PageType.CUSTOMER),
        ("https://example.com/faq", PageType.FAQ),
        ("https://example.com/contact-us", PageType.CONTACT),
        ("https://example.com/terms-of-service", PageType.TERMS),
        ("https://example.com/privacy-policy", PageType.PRIVACY_POLICY),
        ("https://example.com/cookie-policy", PageType.COOKIE_POLICY),
        ("https://example.com/refund-policy", PageType.REFUND_POLICY),
        ("https://example.com/legal", PageType.LEGAL),
        ("https://example.com/careers", PageType.CAREER),
    ],
)
def test_classify_page_from_url(url: str, expected: PageType) -> None:
    assert classify_page(url) == expected


def test_classifies_from_html_title() -> None:
    html = """
    <html>
      <head><title>Simple and transparent pricing</title></head>
      <body></body>
    </html>
    """
    assert classify_page("https://example.com/page/123", html) == PageType.PRICING


def test_classifies_from_meta_description() -> None:
    html = """
    <html>
      <head>
        <meta name="description"
              content="Read our frequently asked questions and support answers">
      </head>
      <body></body>
    </html>
    """
    assert classify_page("https://example.com/support/123", html) == PageType.FAQ


def test_classifies_from_heading() -> None:
    html = """
    <html>
      <body>
        <h1>Contact us</h1>
        <h2>Talk to our team</h2>
      </body>
    </html>
    """
    assert classify_page("https://example.com/page/123", html) == PageType.CONTACT


def test_url_signal_outweighs_conflicting_html_signal() -> None:
    html = """
    <html>
      <head><title>Latest company blog articles</title></head>
      <body><h1>News and insights</h1></body>
    </html>
    """
    assert classify_page("https://example.com/pricing", html) == PageType.PRICING


def test_specific_policy_beats_generic_legal_signal() -> None:
    html = """
    <html>
      <head><title>Legal information</title></head>
      <body><h1>Privacy Policy</h1></body>
    </html>
    """
    result = classify_page("https://example.com/legal/privacy-policy", html)
    assert result == PageType.PRIVACY_POLICY


@pytest.mark.parametrize(
    "url",
    [
        "",
        " ",
        "not-a-valid-url",
        "example.com/about",
        "ftp://example.com/about",
    ],
)
def test_invalid_urls_return_unknown(url: str) -> None:
    assert classify_page(url) == PageType.UNKNOWN


def test_valid_page_with_unrecognized_html_returns_general() -> None:
    html = """
    <html>
      <head><title>Welcome to Acme</title></head>
      <body><h1>Explore our world</h1></body>
    </html>
    """
    result = classify_page("https://example.com/something", html)
    assert result == PageType.GENERAL


def test_valid_page_without_html_or_url_signal_returns_unknown() -> None:
    assert classify_page("https://example.com/x7k2") == PageType.UNKNOWN


def test_none_html_does_not_crash() -> None:
    assert classify_page("https://example.com/about", None) == PageType.ABOUT


def test_malformed_html_does_not_crash() -> None:
    html = "<html><head><title>Pricing<body><h1>Plans"
    assert classify_page("https://example.com/page", html) == PageType.PRICING


def test_query_string_can_supply_signal() -> None:
    url = "https://example.com/page?id=2&section=contact"
    assert classify_page(url) == PageType.CONTACT


def test_encoded_url_is_normalized() -> None:
    url = "https://example.com/privacy%20policy"
    assert classify_page(url) == PageType.PRIVACY_POLICY


def test_hyphenated_case_study_is_classified_correctly() -> None:
    url = "https://example.com/customer-case-study"
    assert classify_page(url) == PageType.CASE_STUDY
