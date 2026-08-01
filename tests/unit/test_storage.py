"""Mission 12 — unit tests for storage/models.py and storage/repository.py."""

import pytest

from agent3.ai.schemas import SourcedField, WebsiteIntelligence
from agent3.classification.page_classifier import PageType
from agent3.crawler.models import FetchResult, FetchStatus
from agent3.extraction.chunker import Chunk
from agent3.extraction.text_extractor import ExtractedPage
from agent3.storage import repository
from agent3.storage.models import ScanStatus


@pytest.fixture(autouse=True)
def clean_storage():
    """Every test starts against an empty in-memory store."""
    repository.reset()
    yield
    repository.reset()


def _extracted_page(url="https://example.com/pricing", page_type=PageType.PRICING):
    return ExtractedPage(
        url=url,
        page_type=page_type,
        title="Pricing",
        meta_description="Our plans",
        headings=["Plans"],
        clean_text="Starter $10/mo. Pro $50/mo.",
        raw_text_length=28,
        language="en",
        fetch_status=FetchStatus.SUCCESS,
    )


def _homepage_fetch_result(url="https://example.com"):
    return FetchResult(
        url=url,
        final_url=url,
        status=FetchStatus.SUCCESS,
        http_status_code=200,
        html="<html></html>",
        elapsed_ms=120,
    )


def _intelligence():
    source = SourcedField(
        value="Acme sells widgets.",
        confidence="high",
        sources=["https://example.com/about"],
    )
    return WebsiteIntelligence(
        company_overview=source,
        products_and_services=source,
        legal_pages={"termsAvailable": True},
        missing_information=[],
    )


def test_scan_gets_a_unique_scan_id():
    scan_a = repository.save_scan_results(
        scan_id="scan_a",
        company_id="company_1",
        homepage=_homepage_fetch_result(),
        pages=[],
        chunks=[],
        intelligence=None,
    )
    scan_b = repository.save_scan_results(
        scan_id="scan_b",
        company_id="company_1",
        homepage=_homepage_fetch_result(),
        pages=[],
        chunks=[],
        intelligence=None,
    )

    assert scan_a.scan_id == "scan_a"
    assert scan_b.scan_id == "scan_b"
    assert scan_a.scan_id != scan_b.scan_id


def test_save_scan_results_persists_pages_linked_to_scan_and_company():
    page = _extracted_page()

    repository.save_scan_results(
        scan_id="scan_1",
        company_id="company_1",
        homepage=_homepage_fetch_result(),
        pages=[page],
        chunks=[],
        intelligence=None,
    )

    saved_pages = repository.get_scanned_pages("scan_1")
    assert len(saved_pages) == 1
    saved_page = saved_pages[0]
    assert saved_page.scan_id == "scan_1"
    assert saved_page.company_id == "company_1"
    assert saved_page.page_url == page.url
    assert saved_page.page_type == PageType.PRICING
    assert saved_page.clean_text == page.clean_text  # extracted text is saved


def test_chunks_are_linked_to_their_scanned_page():
    page = _extracted_page()
    chunk = Chunk(
        company_id="company_1",
        page_url=page.url,
        page_type=page.page_type,
        chunk_index=0,
        title=page.title,
        text="Starter $10/mo.",
    )

    repository.save_scan_results(
        scan_id="scan_1",
        company_id="company_1",
        homepage=_homepage_fetch_result(),
        pages=[page],
        chunks=[chunk],
        intelligence=None,
    )

    saved_page = repository.get_scanned_pages("scan_1")[0]
    saved_chunks = repository.get_chunks_for_page(saved_page.page_id)

    assert len(saved_chunks) == 1
    assert saved_chunks[0].page_id == saved_page.page_id
    assert saved_chunks[0].company_id == "company_1"
    assert saved_chunks[0].text == "Starter $10/mo."


def test_save_scan_results_marks_scan_completed_with_counts():
    scan = repository.save_scan_results(
        scan_id="scan_1",
        company_id="company_1",
        homepage=_homepage_fetch_result(),
        pages=[_extracted_page()],
        chunks=[],
        intelligence=None,
        pages_discovered=3,
        pages_failed=2,
    )

    assert scan.status == ScanStatus.COMPLETED
    assert scan.pages_scanned == 1
    assert scan.pages_failed == 2
    assert scan.pages_discovered == 3
    assert scan.completed_at is not None

    fetched = repository.get_scan("scan_1")
    assert fetched is scan


def test_structured_intelligence_is_saved_and_retrievable_by_company():
    intelligence = _intelligence()

    repository.save_scan_results(
        scan_id="scan_1",
        company_id="company_1",
        homepage=_homepage_fetch_result(),
        pages=[],
        chunks=[],
        intelligence=intelligence,
    )

    saved = repository.get_website_intelligence("company_1")
    assert saved is not None
    assert saved.company_id == "company_1"
    assert saved.scan_id == "scan_1"
    assert saved.data["company_overview"]["value"] == "Acme sells widgets."


def test_get_website_intelligence_returns_latest_when_rescanned():
    repository.save_scan_results(
        scan_id="scan_1",
        company_id="company_1",
        homepage=_homepage_fetch_result(),
        pages=[],
        chunks=[],
        intelligence=_intelligence(),
    )
    repository.save_scan_results(
        scan_id="scan_2",
        company_id="company_1",
        homepage=_homepage_fetch_result(),
        pages=[],
        chunks=[],
        intelligence=_intelligence(),
    )

    latest = repository.get_website_intelligence("company_1")
    assert latest.scan_id == "scan_2"


def test_get_website_intelligence_never_leaks_across_companies():
    repository.save_scan_results(
        scan_id="scan_1",
        company_id="company_1",
        homepage=_homepage_fetch_result(),
        pages=[],
        chunks=[],
        intelligence=_intelligence(),
    )

    assert repository.get_website_intelligence("company_2") is None


def test_fail_scan_marks_scan_failed_and_stores_a_scan_level_error():
    scan = repository.fail_scan(
        scan_id="scan_1",
        company_id="company_1",
        website_url="https://example.com",
        domain="example.com",
        error_type="website_unreachable",
        message="The website could not be reached within the configured timeout.",
    )

    assert scan.status == ScanStatus.FAILED
    assert scan.completed_at is not None
    assert scan.error_summary == "The website could not be reached within the configured timeout."

    errors = repository.get_scan_errors("scan_1")
    assert len(errors) == 1
    assert errors[0].scan_id == "scan_1"
    assert errors[0].page_url is None
    assert errors[0].error_type == "website_unreachable"


def test_record_scan_error_stores_page_level_errors_without_failing_the_scan():
    repository.save_scan_results(
        scan_id="scan_1",
        company_id="company_1",
        homepage=_homepage_fetch_result(),
        pages=[_extracted_page()],
        chunks=[],
        intelligence=None,
    )

    repository.record_scan_error(
        scan_id="scan_1",
        error_type="not_found",
        message="404 fetching /careers",
        page_url="https://example.com/careers",
    )

    scan = repository.get_scan("scan_1")
    errors = repository.get_scan_errors("scan_1")

    assert scan.status == ScanStatus.COMPLETED  # one bad page doesn't fail the scan
    assert len(errors) == 1
    assert errors[0].page_url == "https://example.com/careers"


def test_get_scan_returns_none_for_unknown_scan_id():
    assert repository.get_scan("does_not_exist") is None
