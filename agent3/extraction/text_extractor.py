"""extraction/text_extractor.py — Mission 9.

"Strip the HTML junk, keep the real text": turns a fetched page into an
ExtractedPage (clean_text + title + headings + metadata).
See Agent3_Architecture.md §4 for the ExtractedPage contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup, Comment

from agent3.classification.page_classifier import PageType
from agent3.common import logging as log
from agent3.crawler.models import FetchResult, FetchStatus


@dataclass
class ExtractedPage:
    """Structured content extracted from one fetched webpage.

    Attributes:
        url:
            The final source URL of the page.

        page_type:
            The semantic page category assigned by Mission 8.

        title:
            The page title extracted from the HTML title element.

        meta_description:
            The page description extracted from its metadata.

        headings:
            Non-empty H1-H6 headings in document order.

        clean_text:
            Readable page text after HTML noise and repeated whitespace
            have been removed.

        raw_text_length:
            Character length of the text before final whitespace
            normalization.

        language:
            Language declared by the page, when available.

        fetch_status:
            The status returned by the page fetcher.
    """

    url: str
    page_type: PageType
    title: Optional[str]
    meta_description: Optional[str]
    headings: list[str]
    clean_text: str
    raw_text_length: int
    language: Optional[str]
    fetch_status: FetchStatus


def extract_text(
    fetch_result: FetchResult,
    page_type: PageType,
) -> ExtractedPage:
    """Extract clean, readable content from a fetched webpage.

    Failed fetches and empty pages return an empty ExtractedPage instead
    of raising an exception. This allows one problematic page to be
    skipped without crashing the complete website scan.

    Args:
        fetch_result:
            The typed result returned by the crawler fetcher.

        page_type:
            The semantic page category assigned by Mission 8.

    Returns:
        An ExtractedPage suitable for chunking and later AI processing.
    """
    page_url = fetch_result.final_url or fetch_result.url

    log.info(
        "content_extraction_started",
        url=page_url,
        page_type=page_type.value,
        fetch_status=fetch_result.status.value,
    )

    if not fetch_result.status.is_ok:
        log.warning(
            "content_extraction_skipped",
            url=page_url,
            page_type=page_type.value,
            fetch_status=fetch_result.status.value,
            reason=fetch_result.error_reason or "Fetch was not successful.",
        )

        return _empty_extracted_page(
            fetch_result=fetch_result,
            page_type=page_type,
        )

    if not fetch_result.html or not fetch_result.html.strip():
        log.warning(
            "content_extraction_empty_html",
            url=page_url,
            page_type=page_type.value,
            fetch_status=fetch_result.status.value,
        )

        return _empty_extracted_page(
            fetch_result=fetch_result,
            page_type=page_type,
        )

    try:
        soup = BeautifulSoup(fetch_result.html, "html.parser")

        title = _extract_title(soup)
        meta_description = _extract_meta_description(soup)
        language = _extract_language(soup)

        _remove_comments(soup)
        _remove_noise_elements(soup)
        _remove_hidden_elements(soup)

        headings = _extract_headings(soup)
        content_root = _select_content_root(soup)

        raw_text = content_root.get_text(
            separator="\n",
            strip=True,
        )

        clean_text = _normalize_text(raw_text)

        extracted_page = ExtractedPage(
            url=page_url,
            page_type=page_type,
            title=title,
            meta_description=meta_description,
            headings=headings,
            clean_text=clean_text,
            raw_text_length=len(raw_text),
            language=language,
            fetch_status=fetch_result.status,
        )

        log.info(
            "content_extraction_completed",
            url=page_url,
            page_type=page_type.value,
            title=title,
            headings_count=len(headings),
            raw_text_length=len(raw_text),
            clean_text_length=len(clean_text),
        )

        return extracted_page

    except Exception as exc:
        # Extraction of one malformed page must not terminate the scan.
        log.warning(
            "content_extraction_failed",
            url=page_url,
            page_type=page_type.value,
            error=str(exc),
        )

        return _empty_extracted_page(
            fetch_result=fetch_result,
            page_type=page_type,
        )


def _empty_extracted_page(
    fetch_result: FetchResult,
    page_type: PageType,
) -> ExtractedPage:
    """Create a valid empty result for a failed or contentless page."""
    return ExtractedPage(
        url=fetch_result.final_url or fetch_result.url,
        page_type=page_type,
        title=None,
        meta_description=None,
        headings=[],
        clean_text="",
        raw_text_length=0,
        language=None,
        fetch_status=fetch_result.status,
    )


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    """Extract and normalize the page title.

    Returns:
        The normalized title, or None when no meaningful title exists.
    """
    if soup.title is None:
        return None

    title = soup.title.get_text(
        separator=" ",
        strip=True,
    )

    title = _normalize_inline_text(title)

    return title or None


def _extract_meta_description(
    soup: BeautifulSoup,
) -> Optional[str]:
    """Extract a page description from common metadata fields.

    The standard meta description is preferred. Open Graph and Twitter
    descriptions are used as fallbacks.
    """
    standard_description = soup.find(
        "meta",
        attrs={
            "name": lambda value: (
                isinstance(value, str)
                and value.strip().lower() == "description"
            )
        },
    )

    description = _meta_content(standard_description)

    if description:
        return description

    open_graph_description = soup.find(
        "meta",
        attrs={
            "property": lambda value: (
                isinstance(value, str)
                and value.strip().lower() == "og:description"
            )
        },
    )

    description = _meta_content(open_graph_description)

    if description:
        return description

    twitter_description = soup.find(
        "meta",
        attrs={
            "name": lambda value: (
                isinstance(value, str)
                and value.strip().lower() == "twitter:description"
            )
        },
    )

    return _meta_content(twitter_description)


def _meta_content(meta_tag: object) -> Optional[str]:
    """Return normalized content from a BeautifulSoup meta element."""
    if meta_tag is None or not hasattr(meta_tag, "get"):
        return None

    content = meta_tag.get("content")

    if not isinstance(content, str):
        return None

    normalized_content = _normalize_inline_text(content)

    return normalized_content or None


def _extract_language(soup: BeautifulSoup) -> Optional[str]:
    """Extract the language declared by the webpage.

    The HTML lang attribute is preferred. The Content-Language metadata
    field is used as a fallback.
    """
    html_tag = soup.find("html")

    if html_tag is not None:
        language = html_tag.get("lang")

        if isinstance(language, str):
            normalized_language = language.strip().lower()

            if normalized_language:
                return normalized_language

    language_meta = soup.find(
        "meta",
        attrs={
            "http-equiv": lambda value: (
                isinstance(value, str)
                and value.strip().lower() == "content-language"
            )
        },
    )

    language = _meta_content(language_meta)

    if language:
        return language.lower()

    return None


def _remove_comments(soup: BeautifulSoup) -> None:
    """Remove HTML comments from the parsed document."""
    comments = soup.find_all(
        string=lambda text: isinstance(text, Comment)
    )

    for comment in comments:
        comment.extract()


def _remove_noise_elements(soup: BeautifulSoup) -> None:
    """Remove elements that normally contain no useful business content."""
    removable_tags = {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "canvas",
        "iframe",
        "object",
        "embed",
        "nav",
        "footer",
        "form",
    }

    for element in soup.find_all(removable_tags):
        element.decompose()


def _remove_hidden_elements(soup: BeautifulSoup) -> None:
    """Remove elements explicitly marked as hidden.

    This does not try to evaluate full CSS. It handles common HTML
    mechanisms websites use to hide elements from users.
    """
    for element in soup.find_all(True):
        if element.has_attr("hidden"):
            element.decompose()
            continue

        aria_hidden = element.get("aria-hidden")

        if (
            isinstance(aria_hidden, str)
            and aria_hidden.strip().lower() == "true"
        ):
            element.decompose()
            continue

        style = element.get("style")

        if not isinstance(style, str):
            continue

        normalized_style = re.sub(
            r"\s+",
            "",
            style.lower(),
        )

        if (
            "display:none" in normalized_style
            or "visibility:hidden" in normalized_style
        ):
            element.decompose()


def _extract_headings(soup: BeautifulSoup) -> list[str]:
    """Extract unique, non-empty H1-H6 headings in document order."""
    headings: list[str] = []
    seen_headings: set[str] = set()

    for heading_element in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6"]
    ):
        heading = heading_element.get_text(
            separator=" ",
            strip=True,
        )

        heading = _normalize_inline_text(heading)

        if not heading:
            continue

        comparison_value = heading.casefold()

        if comparison_value in seen_headings:
            continue

        seen_headings.add(comparison_value)
        headings.append(heading)

    return headings


def _select_content_root(soup: BeautifulSoup):
    """Select the HTML element most likely to contain the main page text.

    Selection priority:
        1. main
        2. article
        3. common content containers
        4. body
        5. the entire parsed document
    """
    main_element = soup.find("main")

    if main_element is not None:
        return main_element

    article_element = soup.find("article")

    if article_element is not None:
        return article_element

    common_content_selectors = (
        '[role="main"]',
        "#main-content",
        "#main_content",
        "#content",
        ".main-content",
        ".main_content",
        ".page-content",
        ".page_content",
        ".content",
    )

    for selector in common_content_selectors:
        content_element = soup.select_one(selector)

        if content_element is not None:
            return content_element

    if soup.body is not None:
        return soup.body

    return soup


def _normalize_text(text: str) -> str:
    """Normalize multiline page text.

    Repeated whitespace inside each line is collapsed, empty lines are
    removed, and repeated adjacent lines are removed.
    """
    normalized_lines: list[str] = []
    previous_line: Optional[str] = None

    for raw_line in text.splitlines():
        normalized_line = _normalize_inline_text(raw_line)

        if not normalized_line:
            continue

        if normalized_line == previous_line:
            continue

        normalized_lines.append(normalized_line)
        previous_line = normalized_line

    return "\n".join(normalized_lines)


def _normalize_inline_text(text: str) -> str:
    """Collapse repeated whitespace inside a single text value."""
    return " ".join(text.split())