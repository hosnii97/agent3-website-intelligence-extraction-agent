"""Mission 13 — hits the actual API endpoints.
These tests use FastAPI's TestClient and mock the website scan pipeline,
so they run locally without crawling a real website or calling an AI model.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from agent3.ai.schemas import (
    LegalPages,
    SourcedField,
    WebsiteIntelligence,
)
from agent3.api import routes
from agent3.storage import repository
from agent3.storage.models import ScanStatus


# TestClient sends requests directly to the FastAPI application.
client = TestClient(routes.app)


@pytest.fixture(autouse=True)
def clean_repository():
    """Ensure each test starts with an empty in-memory database."""

    repository.reset()

    yield

    repository.reset()


@pytest.fixture
def disable_real_scan(monkeypatch):
    """Replace the real scan pipeline with a function that does nothing.

    FastAPI executes background tasks during TestClient requests. Without this
    mock, a POST test could perform real network and AI operations.
    """

    def fake_run_website_scan(
        scan_id: str,
        company_id: str,
        website_url: str,
        max_pages: int,
    ):
        return None

    monkeypatch.setattr(
        routes,
        "run_website_scan",
        fake_run_website_scan,
    )


def create_test_intelligence() -> WebsiteIntelligence:
    """Create valid structured website intelligence for API tests."""

    overview = SourcedField(
        value="Example Company provides website intelligence services.",
        confidence="high",
        sources=["https://example.com/about"],
    )

    products = SourcedField(
        value="The company provides an AI website analysis platform.",
        confidence="high",
        sources=["https://example.com/products"],
    )

    pricing = SourcedField(
        value="The service provides monthly subscription plans.",
        confidence="medium",
        sources=["https://example.com/pricing"],
    )

    blog_topics = SourcedField(
        value="The blog discusses AI and website analytics.",
        confidence="medium",
        sources=["https://example.com/blog"],
    )

    case_studies = SourcedField(
        value="The website contains customer success stories.",
        confidence="medium",
        sources=["https://example.com/case-studies"],
    )

    return WebsiteIntelligence(
        company_overview=overview,
        products_and_services=products,
        pricing=pricing,
        blog_topics=blog_topics,
        case_studies=case_studies,
        legal_pages=LegalPages(
            terms_available=True,
            privacy_policy_available=True,
            sources=[
                "https://example.com/terms",
                "https://example.com/privacy",
            ],
        ),
        missing_information=[],
    )


# =============================================================================
# POST /api/agents/agent3/scan-website
# =============================================================================


def test_start_scan_returns_202_and_scan_information(
    disable_real_scan,
):
    """A valid request should create and return an in-progress scan."""

    response = client.post(
        "/api/agents/agent3/scan-website",
        json={
            "companyId": "company_123",
            "websiteUrl": "https://www.example.com",
        },
    )

    assert response.status_code == 202

    body = response.json()

    assert body["companyId"] == "company_123"
    assert body["scanId"].startswith("scan_")
    assert body["status"] == "in_progress"
    assert "startedAt" in body

    # Final-result fields should not appear while the scan is running.
    assert "pagesScanned" not in body
    assert "pagesFailed" not in body
    assert "completedAt" not in body

    # The scan should also be retrievable from storage.
    stored_scan = repository.get_scan(body["scanId"])

    assert stored_scan is not None
    assert stored_scan.company_id == "company_123"
    assert stored_scan.status == ScanStatus.IN_PROGRESS


def test_start_scan_normalizes_website_url(
    disable_real_scan,
):
    """The API should normalize a valid website URL before storing it."""

    response = client.post(
        "/api/agents/agent3/scan-website",
        json={
            "companyId": "company_123",
            "websiteUrl": "https://Example.COM/",
        },
    )

    assert response.status_code == 202

    scan_id = response.json()["scanId"]
    stored_scan = repository.get_scan(scan_id)

    assert stored_scan is not None
    assert stored_scan.website_url == "https://example.com"
    assert stored_scan.domain == "example.com"


def test_start_scan_accepts_matching_domain(
    disable_real_scan,
):
    """A provided domain may match while differing only by 'www.'."""

    response = client.post(
        "/api/agents/agent3/scan-website",
        json={
            "companyId": "company_123",
            "websiteUrl": "https://www.example.com",
            "domain": "example.com",
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "in_progress"


def test_start_scan_rejects_missing_company_id():
    """Missing required fields should produce HTTP 400."""

    response = client.post(
        "/api/agents/agent3/scan-website",
        json={
            "websiteUrl": "https://example.com",
        },
    )

    assert response.status_code == 400

    body = response.json()

    assert body["status"] == "error"
    assert body["errorType"] == "invalid_input"
    assert body["retryable"] is False
    assert body["details"]["field"] == "companyId"


def test_start_scan_rejects_missing_website_url():
    """A missing websiteUrl should produce a clear validation error."""

    response = client.post(
        "/api/agents/agent3/scan-website",
        json={
            "companyId": "company_123",
        },
    )

    assert response.status_code == 400

    body = response.json()

    assert body["status"] == "error"
    assert body["errorType"] == "invalid_input"
    assert body["retryable"] is False
    assert body["details"]["field"] == "websiteUrl"


@pytest.mark.parametrize(
    "website_url",
    [
        "",
        "javascript:alert(1)",
        "ftp://example.com",
        "http://localhost",
        "http://127.0.0.1",
    ],
)
def test_start_scan_rejects_invalid_website_url(
    website_url,
):
    """Malformed, unsupported, or unsafe URLs should be rejected."""

    response = client.post(
        "/api/agents/agent3/scan-website",
        json={
            "companyId": "company_123",
            "websiteUrl": website_url,
        },
    )

    assert response.status_code == 400

    body = response.json()

    # An empty string is rejected by Pydantic before URL normalization.
    expected_error_type = (
        "invalid_input"
        if website_url == ""
        else "invalid_url"
    )

    assert body["status"] == "error"
    assert body["errorType"] == expected_error_type
    assert body["retryable"] is False


def test_start_scan_rejects_domain_mismatch():
    """The optional domain must match the website URL host."""

    response = client.post(
        "/api/agents/agent3/scan-website",
        json={
            "companyId": "company_123",
            "websiteUrl": "https://example.com",
            "domain": "different-company.com",
        },
    )

    assert response.status_code == 400

    body = response.json()

    assert body["companyId"] == "company_123"
    assert body["status"] == "error"
    assert body["errorType"] == "domain_mismatch"
    assert body["retryable"] is False
    assert body["details"]["field"] == "domain"


def test_background_pipeline_receives_request_values(
    monkeypatch,
):
    """The endpoint should trigger the scan pipeline with normalized values."""

    received_arguments = {}

    def fake_run_website_scan(
        scan_id: str,
        company_id: str,
        website_url: str,
        max_pages: int,
    ):
        received_arguments.update(
            {
                "scan_id": scan_id,
                "company_id": company_id,
                "website_url": website_url,
                "max_pages": max_pages,
            }
        )

    monkeypatch.setattr(
        routes,
        "run_website_scan",
        fake_run_website_scan,
    )

    response = client.post(
        "/api/agents/agent3/scan-website",
        json={
            "companyId": "company_123",
            "websiteUrl": "https://Example.COM/",
            "options": {
                "maxPages": 10,
            },
        },
    )

    assert response.status_code == 202

    body = response.json()

    assert received_arguments == {
        "scan_id": body["scanId"],
        "company_id": "company_123",
        "website_url": "https://example.com",
        "max_pages": 10,
    }


def test_background_pipeline_failure_marks_scan_failed(
    monkeypatch,
):
    """Unexpected pipeline exceptions should be persisted as failures."""

    def failing_run_website_scan(
        scan_id: str,
        company_id: str,
        website_url: str,
        max_pages: int,
    ):
        raise RuntimeError("Unexpected pipeline failure")

    monkeypatch.setattr(
        routes,
        "run_website_scan",
        failing_run_website_scan,
    )

    response = client.post(
        "/api/agents/agent3/scan-website",
        json={
            "companyId": "company_123",
            "websiteUrl": "https://example.com",
        },
    )

    assert response.status_code == 202

    scan_id = response.json()["scanId"]
    stored_scan = repository.get_scan(scan_id)

    assert stored_scan is not None
    assert stored_scan.status == ScanStatus.FAILED
    assert stored_scan.error_summary == "Unexpected pipeline failure"

    stored_errors = repository.get_scan_errors(scan_id)

    assert len(stored_errors) == 1
    assert stored_errors[0].error_type == "internal_error"


# =============================================================================
# GET /api/agents/agent3/scans/{scanId}
# =============================================================================


def test_get_scan_status_returns_in_progress_scan():
    """An existing unfinished scan should return in_progress."""

    repository._get_or_create_scan(
        scan_id="scan_123",
        company_id="company_123",
        website_url="https://example.com",
        domain="example.com",
    )

    response = client.get(
        "/api/agents/agent3/scans/scan_123"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["companyId"] == "company_123"
    assert body["scanId"] == "scan_123"
    assert body["status"] == "in_progress"
    assert "startedAt" in body
    assert "pagesScanned" not in body


def test_get_scan_status_returns_404_for_unknown_scan():
    """An unknown scan ID should return a clear 404 error."""

    response = client.get(
        "/api/agents/agent3/scans/unknown_scan"
    )

    assert response.status_code == 404

    body = response.json()

    assert body["scanId"] == "unknown_scan"
    assert body["status"] == "error"
    assert body["errorType"] == "scan_not_found"
    assert body["retryable"] is False


def test_get_scan_status_returns_failed_scan():
    """A failed scan should return its stored failure information."""

    repository.fail_scan(
        scan_id="scan_failed",
        company_id="company_123",
        website_url="https://example.com",
        domain="example.com",
        error_type="website_unreachable",
        message="The website could not be reached.",
    )

    response = client.get(
        "/api/agents/agent3/scans/scan_failed"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["companyId"] == "company_123"
    assert body["scanId"] == "scan_failed"
    assert body["status"] == "failed"
    assert body["errorType"] == "website_unreachable"
    assert body["message"] == "The website could not be reached."
    assert body["retryable"] is True


def test_get_scan_status_returns_completed_summary():
    """A completed scan should return counts and extracted-data summary."""

    scan = repository._get_or_create_scan(
        scan_id="scan_completed",
        company_id="company_123",
        website_url="https://example.com",
        domain="example.com",
    )

    # Arrange a completed scan directly so the test remains independent
    # from the crawling pipeline.
    scan.status = ScanStatus.COMPLETED
    scan.pages_scanned = 5
    scan.pages_failed = 1
    scan.completed_at = datetime.now(timezone.utc)

    repository.save_intelligence(
        company_id="company_123",
        scan_id="scan_completed",
        intelligence=create_test_intelligence(),
    )

    response = client.get(
        "/api/agents/agent3/scans/scan_completed"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["companyId"] == "company_123"
    assert body["scanId"] == "scan_completed"
    assert body["status"] == "completed"
    assert body["pagesScanned"] == 5
    assert body["pagesFailed"] == 1
    assert "completedAt" in body

    assert body["extractedDataSummary"] == {
        "hasPricing": True,
        "hasBlog": True,
        "hasTerms": True,
        "hasPrivacyPolicy": True,
        "hasCaseStudies": True,
    }


# =============================================================================
# GET /api/companies/{companyId}/website-intelligence
# =============================================================================


def test_get_company_intelligence_returns_latest_result():
    """The endpoint should return validated WebsiteIntelligence JSON."""

    intelligence = create_test_intelligence()

    repository.save_intelligence(
        company_id="company_123",
        scan_id="scan_123",
        intelligence=intelligence,
    )

    response = client.get(
        "/api/companies/company_123/website-intelligence"
    )

    assert response.status_code == 200

    body = response.json()

    assert (
        body["company_overview"]["value"]
        == "Example Company provides website intelligence services."
    )

    assert (
        body["products_and_services"]["value"]
        == "The company provides an AI website analysis platform."
    )

    assert body["pricing"]["confidence"] == "medium"
    assert body["legal_pages"]["terms_available"] is True
    assert body["legal_pages"]["privacy_policy_available"] is True


def test_get_company_intelligence_returns_404_when_missing():
    """A company without stored intelligence should return HTTP 404."""

    response = client.get(
        "/api/companies/company_missing/website-intelligence"
    )

    assert response.status_code == 404

    body = response.json()

    assert body["companyId"] == "company_missing"
    assert body["status"] == "error"
    assert body["errorType"] == "intelligence_not_found"
    assert body["retryable"] is False


