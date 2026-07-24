
"""
Mission 8 — Page Type Classification.

Classifies a fetched website page by inspecting:
1. The URL path and query string.
2. The HTML title.
3. The meta description.
4. H1 and H2 headings.

This module performs no network requests and is designed to be called by
the scan orchestrator after a page has already been fetched.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Final
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup


class PageType(str, Enum):
    """Supported semantic website page types."""

    HOMEPAGE = "homepage"
    ABOUT = "about"
    PRODUCT = "product"
    SERVICE = "service"
    PRICING = "pricing"
    BLOG = "blog"
    CASE_STUDY = "case_study"
    CUSTOMER = "customer"
    FAQ = "faq"
    CONTACT = "contact"
    TERMS = "terms"
    PRIVACY_POLICY = "privacy_policy"
    COOKIE_POLICY = "cookie_policy"
    REFUND_POLICY = "refund_policy"
    LEGAL = "legal"
    CAREER = "career"
    GENERAL = "general"
    UNKNOWN = "unknown"


# More specific categories should appear before broader categories.
PAGE_TYPE_KEYWORDS: Final[dict[PageType, tuple[str, ...]]] = {
    PageType.PRIVACY_POLICY: (
        "privacy policy",
        "privacy notice",
        "data protection",
        "data privacy",
        "gdpr",
    ),
    PageType.COOKIE_POLICY: (
        "cookie policy",
        "cookies policy",
        "cookie notice",
        "manage cookies",
    ),
    PageType.REFUND_POLICY: (
        "refund policy",
        "return policy",
        "returns policy",
        "cancellation policy",
        "money back",
    ),
    PageType.TERMS: (
        "terms and conditions",
        "terms of service",
        "terms of use",
        "user agreement",
        "service agreement",
    ),
    PageType.CASE_STUDY: (
        "case study",
        "case studies",
        "success story",
        "success stories",
        "customer story",
        "customer stories",
    ),
    PageType.PRICING: (
        "pricing",
        "price",
        "prices",
        "plans",
        "subscription",
        "subscriptions",
        "packages",
    ),
    PageType.CAREER: (
        "career",
        "careers",
        "jobs",
        "job openings",
        "open positions",
        "vacancies",
        "join us",
        "work with us",
    ),
    PageType.CONTACT: (
        "contact",
        "contact us",
        "get in touch",
        "reach us",
        "talk to sales",
    ),
    PageType.ABOUT: (
        "about",
        "about us",
        "our company",
        "company profile",
        "who we are",
        "our story",
        "our team",
    ),
    PageType.FAQ: (
        "faq",
        "faqs",
        "frequently asked questions",
        "help center",
        "help centre",
        "knowledge base",
    ),
    PageType.BLOG: (
        "blog",
        "news",
        "articles",
        "insights",
        "resources",
        "press",
        "media",
    ),
    PageType.CUSTOMER: (
        "customers",
        "clients",
        "testimonials",
        "reviews",
        "trusted by",
    ),
    PageType.PRODUCT: (
        "product",
        "products",
        "platform",
        "solution",
        "solutions",
        "features",
        "capabilities",
    ),
    PageType.SERVICE: (
        "service",
        "services",
        "what we do",
        "offerings",
        "consulting",
    ),
    PageType.LEGAL: (
        "legal",
        "compliance",
        "disclaimer",
        "accessibility statement",
    ),
}

# A stronger URL match should normally outweigh a weaker HTML hint.
URL_MATCH_WEIGHT: Final[int] = 4
TITLE_MATCH_WEIGHT: Final[int] = 3
HEADING_MATCH_WEIGHT: Final[int] = 2
META_MATCH_WEIGHT: Final[int] = 1


def _normalize_text(value: str) -> str:
    """
    Normalize text for keyword matching.

    Converts separators such as hyphens and underscores into spaces and
    removes repeated whitespace and most punctuation.
    """
    value = unquote(value).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[_\-/]+", " ", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _contains_keyword(text: str, keyword: str) -> bool:
    """
    Check whether a normalized keyword appears as a complete phrase.

    Word boundaries reduce false positives such as matching 'price'
    inside an unrelated longer token.
    """
    normalized_keyword = _normalize_text(keyword)
    if not text or not normalized_keyword:
        return False

    pattern = rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _is_valid_absolute_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return False

    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def _is_homepage(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    return path == ""


def _extract_html_signals(html: str | None) -> dict[str, str]:
    """
    Extract lightweight semantic signals without performing full text extraction.

    Invalid or missing HTML is tolerated and produces empty signals.
    """
    signals = {
        "title": "",
        "meta_description": "",
        "headings": "",
    }

    if not html or not isinstance(html, str):
        return signals

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return signals

    if soup.title:
        title_text = soup.title.get_text(" ", strip=True)
        signals["title"] = _normalize_text(title_text)

    description = soup.find(
        "meta",
        attrs={"name": re.compile(r"^description$", re.IGNORECASE)},
    )
    if description is not None:
        content = description.get("content")
        if isinstance(content, str):
            signals["meta_description"] = _normalize_text(content)

    headings: list[str] = []
    for heading in soup.find_all(["h1", "h2"], limit=12):
        text = heading.get_text(" ", strip=True)
        if text:
            headings.append(text)

    signals["headings"] = _normalize_text(" ".join(headings))
    return signals


def _calculate_url_scores(url: str) -> dict[PageType, int]:
    """Calculate scores from the URL only."""
    parsed = urlparse(url)
    url_signal = _normalize_text(f"{parsed.path} {parsed.query}")
    scores = {page_type: 0 for page_type in PAGE_TYPE_KEYWORDS}

    for page_type, keywords in PAGE_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if _contains_keyword(url_signal, keyword):
                scores[page_type] += URL_MATCH_WEIGHT

    return scores


def _calculate_html_scores(html: str | None) -> dict[PageType, int]:
    """Calculate fallback scores from lightweight HTML signals."""
    html_signals = _extract_html_signals(html)
    scores = {page_type: 0 for page_type in PAGE_TYPE_KEYWORDS}

    for page_type, keywords in PAGE_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if _contains_keyword(html_signals["title"], keyword):
                scores[page_type] += TITLE_MATCH_WEIGHT

            if _contains_keyword(html_signals["headings"], keyword):
                scores[page_type] += HEADING_MATCH_WEIGHT

            if _contains_keyword(html_signals["meta_description"], keyword):
                scores[page_type] += META_MATCH_WEIGHT

    return scores


def _best_scored_type(scores: dict[PageType, int]) -> tuple[PageType | None, int]:
    """Return the best type and score, preserving keyword-map order for ties."""
    highest_score = max(scores.values(), default=0)
    if highest_score == 0:
        return None, 0

    for page_type, score in scores.items():
        if score == highest_score:
            return page_type, score

    return None, 0


def classify_page(url: str, html: str | None = None) -> PageType:
    """
    Classify one website page.

    Args:
        url: Absolute HTTP or HTTPS page URL.
        html: Optional fetched HTML content.

    Returns:
        PageType:
        - HOMEPAGE for a root-domain page.
        - A specific semantic type when URL or HTML evidence exists.
        - GENERAL for a valid non-homepage with readable HTML but no known signal.
        - UNKNOWN for invalid input or when no meaningful evidence exists.
    """
    if not isinstance(url, str) or not url.strip():
        return PageType.UNKNOWN

    url = url.strip()

    if not _is_valid_absolute_url(url):
        return PageType.UNKNOWN

    if _is_homepage(url):
        return PageType.HOMEPAGE

    # URL evidence is authoritative when present. This prevents a page such as
    # /pricing from being mislabeled because its shared layout mentions a blog.
    url_type, _ = _best_scored_type(_calculate_url_scores(url))
    if url_type is not None:
        return url_type

    html_type, _ = _best_scored_type(_calculate_html_scores(html))
    if html_type is not None:
        return html_type

    html_signals = _extract_html_signals(html)
    has_readable_html_signal = any(html_signals.values())
    return PageType.GENERAL if has_readable_html_signal else PageType.UNKNOWN

"""
I'm Keeping just in case we might need it later.
from agent3.common import config
from agent3.common import logging as log"""