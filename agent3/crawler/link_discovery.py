"""crawler/link_discovery.py — Mission 7.

"Find the pages worth reading on this site": from the fetched homepage, find
and filter internal links that are worth scanning.
"""

from agent3.crawler.models import FetchResult
from agent3.common import config
from agent3.common import logging as log

from pathlib import PurePosixPath
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

# Business-related keywords and their priority scores.
# A higher score means the page is considered more useful for
# extracting company intelligence.
RELEVANT_KEYWORDS = {
    "about": 100,
    "product": 95,
    "products": 95,
    "service": 95,
    "services": 95,
    "solution": 90,
    "solutions": 90,
    "pricing": 90,
    "customer": 85,
    "customers": 85,
    "case-study": 85,
    "case-studies": 85,
    "case_study": 85,
    "resources": 75,
    "blog": 70,
    "faq": 70,
    "contact": 65,
    "career": 60,
    "careers": 60,
    "terms": 50,
    "privacy": 50,
    "legal": 50,
    "cookie-policy": 50,
    "cookies": 50,
    "refund": 50,
}

# Pages containing these path segments usually do not provide useful
# company intelligence, so they are excluded from the crawl.
IGNORED_KEYWORDS = {
    "login",
    "log-in",
    "signin",
    "sign-in",
    "signup",
    "sign-up",
    "register",
    "cart",
    "checkout",
    "account",
    "search",
    "logout",
}

# These extensions represent files or assets rather than HTML pages.
# Downloading them would waste crawl time and could consume a lot of memory.
IGNORED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".rar",
    ".mp3",
    ".mp4",
    ".avi",
    ".css",
    ".js",
    ".xml",
}

def discover_links(homepage: FetchResult) -> list[str]:
    """Discover and prioritize internal links from a homepage.

    The number of returned links is controlled by
    config.MAX_PAGES_PER_SCAN. It is not provided by the user.

    Args:
        homepage:
            The result returned by the homepage fetcher. It should
            contain the homepage HTML and its URL.

    Returns:
        A list of unique internal URLs ordered by business relevance.

        An empty list is returned if:

        - The homepage has no HTML.
        - The homepage has no valid URL.
        - No valid internal links are found.
    """

    # Link extraction is impossible if the homepage fetch did not
    # return any HTML.
    if not homepage.html:
        return []

    # Prefer final_url because the original URL may have redirected.
    #
    # Example:
    # http://example.com -> https://www.example.com/
    #
    # If final_url is missing, fall back to the originally requested URL.
    base_url = homepage.final_url or homepage.url

    if not base_url:
        return []

    # Extract the homepage domain so external links can be rejected.
    base_domain = _normalized_domain(base_url)

    # If the homepage URL itself is invalid, link discovery cannot
    # safely continue.
    if not base_domain:
        return []

    # Canonicalize the homepage URL so links pointing back to the
    # homepage can be ignored.
    homepage_url = _canonicalize_url(base_url)

    if homepage_url is None:
        return []

    # Parse the HTML document.
    soup = BeautifulSoup(homepage.html, "html.parser")

    # Map each URL to its relevance score.
    #
    # A dictionary automatically removes duplicate URLs.
    candidates: dict[str, int] = {}

    # Examine every anchor element containing an href attribute.
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()

        # Ignore empty links, fragments, email links, telephone links,
        # JavaScript actions, and embedded data.
        if not _is_supported_href(href):
            continue

        # Convert relative links into absolute URLs.
        #
        # Example:
        # base URL: https://example.com
        # href:     /about
        # result:   https://example.com/about
        absolute_url = urljoin(base_url, href)

        # Normalize the URL so equivalent URLs use the same format.
        canonical_url = _canonicalize_url(absolute_url)

        # Ignore malformed or unsupported URLs.
        if canonical_url is None:
            continue

        # Only keep links that belong to the homepage's domain.
        #
        # Accepted:
        # https://example.com/about
        #
        # Rejected:
        # https://facebook.com/example
        if _normalized_domain(canonical_url) != base_domain:
            continue

        # Do not scan the homepage again.
        if canonical_url == homepage_url:
            continue

        # Ignore assets, downloadable files, login pages, checkout
        # pages, and other irrelevant URLs.
        if _is_irrelevant_url(canonical_url):
            continue

        # The visible anchor text can help identify the page's purpose.
        #
        # Example:
        # <a href="/company">About us</a>
        #
        # The URL path does not contain "about", but the text does.
        anchor_text = anchor.get_text(" ", strip=True)

        # Calculate the page's expected business relevance.
        score = _relevance_score(canonical_url, anchor_text)

        # A URL can appear more than once with different anchor text.
        # Keep its highest relevance score.
        previous_score = candidates.get(canonical_url)

        if previous_score is None or score > previous_score:
            candidates[canonical_url] = score

    # Sort using two rules:
    #
    # 1. Higher relevance scores appear first.
    # 2. Equal scores are sorted alphabetically.
    #
    # Alphabetical tie-breaking produces deterministic results,
    # which makes the function easier to test.
    ordered_links = sorted(
        candidates,
        key=lambda url: (-candidates[url], url),
    )

    # Enforce the system-controlled crawl limit.
    #
    # The caller and end user cannot change this value.
    return ordered_links[:config.MAX_PAGES_PER_SCAN]


def _is_supported_href(href: str) -> bool:
    """Check whether an href may represent a crawlable webpage.

    Args:
        href:
            The raw href value extracted from an anchor element.

    Returns:
        True if the link may be crawled, otherwise False.
    """

    # Empty href values and page fragments do not identify new pages.
    if not href or href.startswith("#"):
        return False

    # Link schemes are case-insensitive.
    lowered_href = href.lower()

    # These links perform actions or open other applications.
    # They should not be passed to the HTTP page fetcher.
    unsupported_prefixes = (
        "mailto:",
        "tel:",
        "javascript:",
        "data:",
    )

    return not lowered_href.startswith(unsupported_prefixes)


def _normalized_domain(url: str) -> str:
    """Extract and normalize a URL's hostname.

    The common "www." prefix is removed so these domains are treated
    as the same website:

    - example.com
    - www.example.com

    Args:
        url:
            The URL whose domain should be extracted.

    Returns:
        The lowercase normalized hostname, or an empty string if the
        URL has no hostname.
    """

    hostname = (urlsplit(url).hostname or "").lower()

    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname


def _canonicalize_url(url: str) -> str | None:
    """Convert a URL into a consistent representation.

    Canonicalization allows duplicate links to be identified.

    For example, these links represent the same page:

    - https://example.com/about
    - https://example.com/about/
    - https://example.com/about#team

    Args:
        url:
            The absolute URL to canonicalize.

    Returns:
        The canonical URL, or None if the URL is invalid or does not
        use HTTP/HTTPS.
    """

    try:
        parsed = urlsplit(url)

        # The crawler only supports regular HTTP and HTTPS pages.
        scheme = parsed.scheme.lower()

        if scheme not in {"http", "https"}:
            return None

        hostname = (parsed.hostname or "").lower()

        # An absolute URL must contain a hostname.
        if not hostname:
            return None

        # Accessing parsed.port can raise ValueError if the URL contains
        # an invalid port, so this code is inside the try block.
        port = parsed.port

        # Standard HTTP and HTTPS ports do not need to appear in the
        # canonical URL.
        is_default_port = (
            port == 80 and scheme == "http"
        ) or (
            port == 443 and scheme == "https"
        )

        netloc = hostname

        # Preserve non-standard ports because they may point to a
        # different server or web application.
        if port is not None and not is_default_port:
            netloc = f"{hostname}:{port}"

        # An empty path means the website root.
        path = parsed.path or "/"

        # Treat "/about/" and "/about" as the same page.
        if path != "/":
            path = path.rstrip("/")

        # Keep the query string because it may identify meaningful
        # content.
        #
        # Remove the fragment because it only points to a location
        # inside the same page.
        return urlunsplit(
            (
                scheme,
                netloc,
                path,
                parsed.query,
                "",
            )
        )

    except ValueError:
        # A malformed link must not crash the entire website scan.
        return None


def _is_irrelevant_url(url: str) -> bool:
    """Check whether a URL points to an irrelevant page or file.

    Args:
        url:
            A canonical internal URL.

    Returns:
        True if the URL should be ignored, otherwise False.
    """

    parsed = urlsplit(url)
    path = parsed.path.lower()

    # Extract the last file extension from the path.
    #
    # Example:
    # /images/logo.png -> .png
    suffix = PurePosixPath(path).suffix

    # Ignore images, documents, archives, scripts, and other assets.
    if suffix in IGNORED_EXTENSIONS:
        return True

    # Split the path into complete segments.
    #
    # Using complete segments prevents accidental matches.
    # For example, "accounting" should not match "account".
    path_parts = {
        part
        for part in path.strip("/").split("/")
        if part
    }

    # Reject the URL if any complete path segment is irrelevant.
    return bool(path_parts.intersection(IGNORED_KEYWORDS))


def _relevance_score(url: str, anchor_text: str) -> int:
    """Calculate a business-relevance score for a link.

    Both the URL path and visible anchor text are checked.

    A higher score means the page should be scanned earlier.
    Unknown internal pages receive a score of zero. They may still
    be selected if fewer than MAX_PAGES_PER_SCAN relevant pages exist.

    Args:
        url:
            The canonical internal URL.

        anchor_text:
            The visible text inside the HTML anchor element.

    Returns:
        The highest matching relevance score, or zero if no relevant
        keyword is found.
    """

    parsed = urlsplit(url)

    # Combine the path and anchor text to improve keyword matching.
    #
    # Spaces and underscores are converted to hyphens so terms such
    # as "case studies", "case_studies", and "case-studies" use a
    # similar format.
    searchable_text = (
        f"{parsed.path} {anchor_text}"
        .lower()
        .replace("_", "-")
        .replace(" ", "-")
    )

    # Collect the score of every matching business keyword.
    matching_scores = [
        score
        for keyword, score in RELEVANT_KEYWORDS.items()
        if keyword in searchable_text
    ]

    # Use the strongest matching category.
    return max(matching_scores, default=0)

