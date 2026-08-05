"""api/routes.py — Mission 13.

Defines the 3 endpoints (scan-website, scan status, get website-intelligence).
Thin layer: validate input, call the orchestrator, shape the response.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agent3.api import schemas
from agent3.orchestrator.scan_pipeline import run_website_scan
from agent3.storage.repository import (
    _get_or_create_scan,
    get_scan,
    get_scan_errors,
    get_website_intelligence,
    fail_scan,
)
from agent3.common import logging as log
from agent3.common import errors

from agent3.ai.extractor import extracted_data_summary
from agent3.ai.schemas import WebsiteIntelligence
from agent3.crawler.url_normalizer import normalize_url
from agent3.storage.models import ScanStatus


# Main FastAPI application.
app = FastAPI(
    title="Agent 3 Website Intelligence API",
    description=(
        "Scans company websites and returns structured "
        "website intelligence."
    ),
    version="1.0.0",
)


def serialize_model(model: Any) -> dict[str, Any]:
    """Convert a Pydantic model to JSON using camelCase fields."""

    return model.model_dump(
        by_alias=True,
        mode="json",
        exclude_none=True,
    )


def build_error_response(
    http_status: int,
    error_type: str,
    message: str,
    *,
    company_id: Optional[str] = None,
    scan_id: Optional[str] = None,
    status: str = "error",
    retryable: bool = False,
    details: Optional[dict[str, Any]] = None,
) -> JSONResponse:
    """Build a standard Agent 3 error response."""

    error = schemas.ErrorResponse(
        companyId=company_id,
        scanId=scan_id,
        status=status,
        errorType=error_type,
        message=message,
        retryable=retryable,
        details=details,
    )

    return JSONResponse(
        status_code=http_status,
        content=serialize_model(error),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request,
    exception: RequestValidationError,
) -> JSONResponse:
    """Convert FastAPI validation errors from HTTP 422 to HTTP 400."""

    validation_errors = exception.errors()

    first_error = (
        validation_errors[0]
        if validation_errors
        else {}
    )

    location = first_error.get("loc", ())
    field_name = location[-1] if location else None

    details = None

    if field_name is not None:
        details = {
            "field": str(field_name),
        }

    return build_error_response(
        http_status=400,
        error_type="invalid_input",
        message=first_error.get(
            "msg",
            "The request body is invalid.",
        ),
        retryable=False,
        details=details,
    )


def domains_match(
    provided_domain: str,
    website_domain: str,
) -> bool:
    """Compare domains while ignoring a leading 'www.'."""

    clean_provided_domain = (
        provided_domain
        .strip()
        .lower()
        .removeprefix("www.")
    )

    clean_website_domain = (
        website_domain
        .strip()
        .lower()
        .removeprefix("www.")
    )

    return clean_provided_domain == clean_website_domain


def execute_scan_in_background(
    scan_id: str,
    request: schemas.ScanWebsiteRequest,
    normalized_url: str,
    website_domain: str,
) -> None:
    """Run the website scanning pipeline in the background."""

    try:
        log.info(
            "website_scan_started",
            scan_id=scan_id,
            company_id=request.company_id,
            website_url=normalized_url,
        )

        run_website_scan(
            scan_id=scan_id,
            company_id=request.company_id,
            website_url=normalized_url,
            max_pages=request.options.max_pages,
        )

    except Exception as exception:
        log.error(
            "website_scan_failed",
            scan_id=scan_id,
            company_id=request.company_id,
            error=str(exception),
        )

        # Store the failure so the scan does not remain in_progress.
        fail_scan(
            scan_id=scan_id,
            company_id=request.company_id,
            website_url=normalized_url,
            domain=website_domain,
            error_type="internal_error",
            message=str(exception),
        )


@app.post(
    "/api/agents/agent3/scan-website",
    status_code=202,
    response_model=schemas.ScanResponse,
    response_model_by_alias=True,
    summary="Start a website scan",
)
def start_website_scan(
    request: schemas.ScanWebsiteRequest,
    background_tasks: BackgroundTasks,
):
    """Validate the request and start the website scan."""

    # Validate and normalize the website URL.
    normalized = normalize_url(request.website_url)

    if not normalized.is_valid:
        return build_error_response(
            http_status=400,
            error_type="invalid_url",
            message=(
                normalized.error_reason
                or "websiteUrl must be a valid HTTP or HTTPS URL."
            ),
            company_id=request.company_id,
            retryable=False,
            details={
                "field": "websiteUrl",
                "value": request.website_url,
            },
        )

    normalized_url = normalized.url
    website_domain = normalized.domain

    # These values should exist after successful validation.
    if normalized_url is None or website_domain is None:
        return build_error_response(
            http_status=400,
            error_type="invalid_url",
            message="websiteUrl could not be normalized.",
            company_id=request.company_id,
            retryable=False,
            details={
                "field": "websiteUrl",
            },
        )

    # Validate the optional domain field.
    if request.domain is not None:
        if not domains_match(
            request.domain,
            website_domain,
        ):
            return build_error_response(
                http_status=400,
                error_type="domain_mismatch",
                message=(
                    "domain must match the host in websiteUrl."
                ),
                company_id=request.company_id,
                retryable=False,
                details={
                    "field": "domain",
                    "providedDomain": request.domain,
                    "websiteDomain": website_domain,
                },
            )

    # Create a unique ID for this scan.
    scan_id = f"scan_{uuid.uuid4().hex}"

    # Use the existing repository function.
    # No repository.py change is required.
    scan = _get_or_create_scan(
        scan_id=scan_id,
        company_id=request.company_id,
        website_url=normalized_url,
        domain=website_domain,
    )

    # Run the pipeline after returning the HTTP response.
    background_tasks.add_task(
        execute_scan_in_background,
        scan_id,
        request,
        normalized_url,
        website_domain,
    )

    # Immediately return the scan ID and in-progress status.
    return schemas.ScanResponse(
        companyId=scan.company_id,
        scanId=scan.scan_id,
        status="in_progress",
        startedAt=scan.started_at,
    )


@app.get(
    "/api/agents/agent3/scans/{scan_id}",
    response_model=schemas.ScanResponse | schemas.ErrorResponse,
    response_model_by_alias=True,
    summary="Get website scan status",
)
def get_website_scan_status(scan_id: str):
    """Return the current status or final result of a scan."""

    scan = get_scan(scan_id)

    if scan is None:
        return build_error_response(
            http_status=404,
            error_type="scan_not_found",
            message=f"Scan '{scan_id}' was not found.",
            scan_id=scan_id,
            retryable=False,
        )

    # Return a failed scan using the standard error structure.
    if scan.status == ScanStatus.FAILED:
        stored_errors = get_scan_errors(scan_id)

        error_type = "internal_error"

        if stored_errors:
            error_type = stored_errors[-1].error_type

        retryable_error_types = {
            "website_unreachable",
            "timeout",
            "ai_extraction_failed",
            "internal_error",
        }

        return schemas.ErrorResponse(
            companyId=scan.company_id,
            scanId=scan.scan_id,
            status="failed",
            errorType=error_type,
            message=(
                scan.error_summary
                or "The website scan failed."
            ),
            retryable=(
                error_type in retryable_error_types
            ),
        )

    summary = None

    # Build the extracted data summary for completed scans.
    if scan.status == ScanStatus.COMPLETED:
        intelligence_record = get_website_intelligence(
            scan.company_id
        )

        intelligence = None

        # Confirm that the intelligence belongs to this scan.
        if (
            intelligence_record is not None
            and intelligence_record.scan_id == scan.scan_id
        ):
            intelligence = WebsiteIntelligence.model_validate(
                intelligence_record.data
            )

        summary = extracted_data_summary(intelligence)

    return schemas.ScanResponse(
        companyId=scan.company_id,
        scanId=scan.scan_id,
        status=scan.status.value,
        pagesScanned=(
            scan.pages_scanned
            if scan.status != ScanStatus.IN_PROGRESS
            else None
        ),
        pagesFailed=(
            scan.pages_failed
            if scan.status != ScanStatus.IN_PROGRESS
            else None
        ),
        extractedDataSummary=summary,
        startedAt=scan.started_at,
        completedAt=scan.completed_at,
    )


@app.get(
    "/api/companies/{company_id}/website-intelligence",
    response_model=WebsiteIntelligence,
    summary="Get website intelligence for a company",
)
def get_company_website_intelligence(
    company_id: str,
):
    """Return the latest website intelligence for a company."""

    intelligence_record = get_website_intelligence(
        company_id
    )

    if intelligence_record is None:
        return build_error_response(
            http_status=404,
            error_type="intelligence_not_found",
            message=(
                "Website intelligence was not found "
                f"for company '{company_id}'."
            ),
            company_id=company_id,
            retryable=False,
        )

    # The repository stores intelligence as a dictionary.
    # Validate it using the existing shared AI schema.
    return WebsiteIntelligence.model_validate(
        intelligence_record.data
    )