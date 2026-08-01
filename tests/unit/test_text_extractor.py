""""Mission 9 — unit tests for extraction/text_extractor.py."""

from agent3.classification.page_classifier import PageType
from agent3.crawler.models import FetchResult, FetchStatus
from agent3.extraction.text_extractor import ExtractedPage, extract_text


def make_fetch_result(
    *,
    html: str | None,
    status: FetchStatus = FetchStatus.SUCCESS,
    url: str = "https://example.com/about",
    final_url: str = "https://example.com/about",
    error_reason: str | None = None,
) -> FetchResult:
    """Create a FetchResult used by Mission 9 tests."""
    return FetchResult(
        url=url,
        final_url=final_url,
        status=status,
        http_status_code=200 if status.is_ok else None,
        html=html,
        elapsed_ms=25,
        error_reason=error_reason,
    )


def test_extracts_structured_content_from_valid_html() -> None:
    html = """
    <html lang="en-US">
      <head>
        <title>  About Example Company  </title>
        <meta name="description" content=" Learn about our company. ">
      </head>
      <body>
        <nav>Home Pricing Contact</nav>
        <main>
          <h1>About Us</h1>
          <h2>Our Mission</h2>
          <p>We build useful AI tools for businesses.</p>
        </main>
        <footer>Copyright 2026</footer>
        <script>console.log('noise')</script>
      </body>
    </html>
    """

    result = extract_text(
        make_fetch_result(html=html),
        PageType.ABOUT,
    )

    assert isinstance(result, ExtractedPage)
    assert result.url == "https://example.com/about"
    assert result.page_type is PageType.ABOUT
    assert result.title == "About Example Company"
    assert result.meta_description == "Learn about our company."
    assert result.headings == ["About Us", "Our Mission"]
    assert "We build useful AI tools for businesses." in result.clean_text
    assert "Home Pricing Contact" not in result.clean_text
    assert "Copyright 2026" not in result.clean_text
    assert "console.log" not in result.clean_text
    assert result.raw_text_length > 0
    assert result.language == "en-us"
    assert result.fetch_status is FetchStatus.SUCCESS


def test_uses_final_url_after_redirect() -> None:
    fetch_result = make_fetch_result(
        html="""
        <html>
          <body>
            <main>
              <p>Redirected content</p>
            </main>
          </body>
        </html>
        """,
        status=FetchStatus.REDIRECTED,
        url="http://example.com/about",
        final_url="https://www.example.com/about",
    )

    result = extract_text(fetch_result, PageType.ABOUT)

    assert result.url == "https://www.example.com/about"
    assert result.fetch_status is FetchStatus.REDIRECTED
    assert result.clean_text == "Redirected content"


def test_returns_empty_result_for_failed_fetch() -> None:
    fetch_result = make_fetch_result(
        html=None,
        status=FetchStatus.TIMEOUT,
        error_reason="Request timed out.",
    )

    result = extract_text(fetch_result, PageType.UNKNOWN)

    assert result.url == "https://example.com/about"
    assert result.page_type is PageType.UNKNOWN
    assert result.title is None
    assert result.meta_description is None
    assert result.headings == []
    assert result.clean_text == ""
    assert result.raw_text_length == 0
    assert result.language is None
    assert result.fetch_status is FetchStatus.TIMEOUT


def test_returns_empty_result_for_empty_html() -> None:
    result = extract_text(
        make_fetch_result(html="   "),
        PageType.GENERAL,
    )

    assert result.clean_text == ""
    assert result.headings == []
    assert result.raw_text_length == 0
    assert result.fetch_status is FetchStatus.SUCCESS


def test_uses_meta_description_fallbacks() -> None:
    html = """
    <html>
      <head>
        <meta
            property="og:description"
            content="Open Graph description"
        >
      </head>
      <body>
        <main>
          <p>Page text</p>
        </main>
      </body>
    </html>
    """

    result = extract_text(
        make_fetch_result(html=html),
        PageType.GENERAL,
    )

    assert result.meta_description == "Open Graph description"


def test_removes_hidden_elements_and_html_comments() -> None:
    html = """
    <html>
      <body>
        <!-- internal comment -->
        <main>
          <p>Visible text</p>
          <p hidden>Hidden by attribute</p>
          <p aria-hidden="true">Hidden by aria</p>
          <p style="display: none">Hidden by display</p>
          <p style="visibility: hidden">Hidden by visibility</p>
        </main>
      </body>
    </html>
    """

    result = extract_text(
        make_fetch_result(html=html),
        PageType.GENERAL,
    )

    assert result.clean_text == "Visible text"


def test_extracts_unique_headings_in_document_order() -> None:
    html = """
    <html>
      <body>
        <main>
          <h1>Overview</h1>
          <h2>Features</h2>
          <h2>  Features  </h2>
          <h3>Pricing</h3>
        </main>
      </body>
    </html>
    """

    result = extract_text(
        make_fetch_result(html=html),
        PageType.PRODUCT,
    )

    assert result.headings == [
        "Overview",
        "Features",
        "Pricing",
    ]


def test_prefers_main_content_over_other_body_content() -> None:
    html = """
    <html>
      <body>
        <aside>Sidebar noise</aside>
        <main>
          <p>Main business content</p>
        </main>
      </body>
    </html>
    """

    result = extract_text(
        make_fetch_result(html=html),
        PageType.SERVICE,
    )

    assert result.clean_text == "Main business content"
    assert "Sidebar noise" not in result.clean_text