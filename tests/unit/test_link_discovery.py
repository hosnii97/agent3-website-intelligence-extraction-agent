"""Mission 7 — unit tests for crawler/link_discovery.py."""

from agent3.crawler import link_discovery
from agent3.crawler.models import FetchResult, FetchStatus
from agent3.common import config

def create_homepage(html: str) -> FetchResult:
    """Create a successful fake homepage response.
    """
    return FetchResult(
        url="https://example.com",
        final_url="https://example.com/",
        status=FetchStatus.SUCCESS,
        http_status_code=200,
        html=html,
        elapsed_ms=100,
        error_reason=None,
    )


def test_discovers_internal_links():
    """Relative internal links should be discovered and made absolute."""
    homepage = create_homepage(
        """
        <html>
            <body>
                <a href="/about">About Us</a>
                <a href="/products">Products</a>
                <a href="/contact">Contact</a>
            </body>
        </html>
        """
    )

    links = link_discovery.discover_links(homepage)

    assert "https://example.com/about" in links
    assert "https://example.com/products" in links
    assert "https://example.com/contact" in links


def test_converts_relative_links_to_absolute_urls():
    """Relative URLs should be converted into complete URLs."""
    homepage = create_homepage(
        """
        <html>
            <body>
                <a href="/services">Services</a>
            </body>
        </html>
        """
    )

    links = link_discovery.discover_links(homepage)

    assert links == ["https://example.com/services"]


def test_removes_duplicate_links():
    """Equivalent versions of the same URL should appear only once."""
    homepage = create_homepage(
        """
        <html>
            <body>
                <a href="/about">About</a>
                <a href="/about/">About with trailing slash</a>
                <a href="/about#team">About team</a>
                <a href="https://example.com/about">
                    Absolute About
                </a>
            </body>
        </html>
        """
    )

    links = link_discovery.discover_links(homepage)

    assert links.count("https://example.com/about") == 1
    assert len(links) == 1


def test_ignores_external_links():
    """Links belonging to other domains should be ignored."""
    homepage = create_homepage(
        """
        <html>
            <body>
                <a href="/about">Internal About</a>

                <a href="https://facebook.com/example">
                    Facebook
                </a>

                <a href="https://another-company.com/products">
                    External Products
                </a>
            </body>
        </html>
        """
    )

    links = link_discovery.discover_links(homepage)

    assert "https://example.com/about" in links
    assert "https://facebook.com/example" not in links
    assert "https://another-company.com/products" not in links
    assert len(links) == 1


def test_ignores_files_and_irrelevant_pages():
    """Assets, files, actions, and irrelevant pages should be ignored."""
    homepage = create_homepage(
        """
        <html>
            <body>
                <a href="/about">About</a>

                <a href="/login">Login</a>
                <a href="/checkout">Checkout</a>
                <a href="/account">Account</a>

                <a href="/images/logo.png">Logo</a>
                <a href="/documents/catalog.pdf">Catalog</a>
                <a href="/scripts/application.js">Script</a>

                <a href="mailto:info@example.com">Email</a>
                <a href="tel:+123456789">Telephone</a>
                <a href="javascript:void(0)">JavaScript action</a>
                <a href="#team">Page section</a>
            </body>
        </html>
        """
    )

    links = link_discovery.discover_links(homepage)

    assert links == ["https://example.com/about"]


def test_prioritizes_business_relevant_pages():
    """Important business pages should appear before general pages."""
    homepage = create_homepage(
        """
        <html>
            <body>
                <a href="/news">General News</a>
                <a href="/contact">Contact</a>
                <a href="/blog">Blog</a>
                <a href="/pricing">Pricing</a>
                <a href="/products">Products</a>
                <a href="/about">About Us</a>
            </body>
        </html>
        """
    )

    links = link_discovery.discover_links(homepage)

    assert links == [
        "https://example.com/about",
        "https://example.com/products",
        "https://example.com/pricing",
        "https://example.com/blog",
        "https://example.com/contact",
        "https://example.com/news",
    ]


def test_uses_anchor_text_when_prioritizing_pages():
    """Visible link text should help prioritize unclear URL paths."""
    homepage = create_homepage(
        """
        <html>
            <body>
                <a href="/page-one">General Information</a>
                <a href="/company">About Us</a>
            </body>
        </html>
        """
    )

    links = link_discovery.discover_links(homepage)

    # "/company" does not contain the word "about", but its anchor
    # text does. It should therefore receive the higher score.
    assert links == [
        "https://example.com/company",
        "https://example.com/page-one",
    ]


def test_enforces_maximum_page_limit():
    """The number of returned pages must not exceed the system limit."""

    # Create more valid internal links than the allowed maximum.
    anchors = ""

    for number in range(config.MAX_PAGES_PER_SCAN + 10):
        anchors += (
            f'<a href="/products/product-{number}">'
            f"Product {number}</a>"
        )

    homepage = create_homepage(
        f"""
        <html>
            <body>
                {anchors}
            </body>
        </html>
        """
    )

    links = link_discovery.discover_links(homepage)

    # Mission 7 uses a fixed system-controlled limit of 15 pages.
    assert config.MAX_PAGES_PER_SCAN == 15
    assert len(links) == config.MAX_PAGES_PER_SCAN


def test_returns_empty_list_when_html_is_missing():
    """An empty HTML response should produce an empty link list."""
    homepage = create_homepage("")

    links = link_discovery.discover_links(homepage)

    assert links == []


def test_does_not_return_the_homepage_again():
    """Links pointing to the same homepage should be ignored."""
    homepage = create_homepage(
        """
        <html>
            <body>
                <a href="/">Homepage</a>
                <a href="https://example.com/">Homepage again</a>
                <a href="/about">About</a>
            </body>
        </html>
        """
    )

    links = link_discovery.discover_links(homepage)

    assert links == ["https://example.com/about"]