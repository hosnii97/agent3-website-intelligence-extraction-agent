"""storage/repository.py — Mission 12.

"Every save/read of the database goes through here": the save()/get() functions
and the ONLY place that writes SQL.

No database driver is wired up yet (see requirements.txt / common/config.py),
so the "tables" are in-memory dicts keyed by ID for now. Every function below
is written as the boundary a real DB implementation would sit behind — callers
never touch the dicts directly, so swapping this for real SQL later only
touches this one file.
"""

from __future__ import annotations

from typing import Optional

from agent3.storage import models
from agent3.storage.models import (
    ContentChunkRecord,
    ScanError,
    ScannedPage,
    ScanStatus,
    WebsiteIntelligenceRecord,
    WebsiteScan,
)
from agent3.crawler.models import FetchResult
from agent3.crawler.url_normalizer import extract_domain
from agent3.extraction.text_extractor import ExtractedPage
from agent3.extraction.chunker import Chunk
from agent3.ai.schemas import WebsiteIntelligence
from agent3.common import logging as log

# --- in-memory "tables" -----------------------------------------------------

_scans: dict[str, WebsiteScan] = {}

_pages: dict[str, ScannedPage] = {}
_pages_by_scan: dict[str, list[str]] = {}

_chunks: dict[str, ContentChunkRecord] = {}
_chunks_by_page: dict[str, list[str]] = {}

_intelligence: dict[str, WebsiteIntelligenceRecord] = {}
_intelligence_by_company: dict[str, list[str]] = {}

_errors: dict[str, ScanError] = {}
_errors_by_scan: dict[str, list[str]] = {}


def reset() -> None:
    """Clear every in-memory table. Test-only; a real DB never needs this."""
    _scans.clear()
    _pages.clear()
    _pages_by_scan.clear()
    _chunks.clear()
    _chunks_by_page.clear()
    _intelligence.clear()
    _intelligence_by_company.clear()
    _errors.clear()
    _errors_by_scan.clear()


# --- scans -------------------------------------------------------------------


def _get_or_create_scan(
    scan_id: str,
    company_id: str,
    website_url: str,
    domain: str,
) -> WebsiteScan:
    scan = _scans.get(scan_id)
    if scan is None:
        scan = WebsiteScan(
            scan_id=scan_id,
            company_id=company_id,
            website_url=website_url,
            domain=domain,
        )
        _scans[scan_id] = scan
        _pages_by_scan.setdefault(scan_id, [])
        _errors_by_scan.setdefault(scan_id, [])
    return scan


def save_scan_results(
    scan_id: str,
    company_id: str,
    homepage: FetchResult,
    pages: list[ExtractedPage],
    chunks: list[Chunk],
    intelligence: Optional[WebsiteIntelligence],
    pages_discovered: Optional[int] = None,
    pages_failed: int = 0,
) -> WebsiteScan:
    """Persist a completed scan: its pages, their chunks, and the intelligence.

    Called once by the orchestrator after the whole pipeline (Missions 5-11)
    has run for one scan. Creates the `website_scans` row if it doesn't
    already exist (so callers don't need a separate "start scan" step).
    """
    website_url = homepage.final_url or homepage.url
    domain = extract_domain(website_url) or website_url

    scan = _get_or_create_scan(scan_id, company_id, website_url, domain)

    page_id_by_url: dict[str, str] = {}
    for extracted_page in pages:
        page_id_by_url[extracted_page.url] = save_page(scan_id, company_id, extracted_page).page_id

    for chunk in chunks:
        page_id = page_id_by_url.get(chunk.page_url)
        if page_id is None:
            log.warning(
                "chunk_save_skipped_unknown_page",
                scan_id=scan_id,
                page_url=chunk.page_url,
            )
            continue
        save_chunk(page_id, company_id, chunk)

    if intelligence is not None:
        save_intelligence(company_id, scan_id, intelligence)

    scan.pages_scanned = len(pages)
    scan.pages_failed = pages_failed
    scan.pages_discovered = pages_discovered if pages_discovered is not None else len(pages) + pages_failed
    scan.status = ScanStatus.COMPLETED
    scan.completed_at = models.utcnow()

    log.info(
        "scan_results_saved",
        scan_id=scan_id,
        company_id=company_id,
        pages_scanned=scan.pages_scanned,
        pages_failed=scan.pages_failed,
    )

    return scan


def fail_scan(
    scan_id: str,
    company_id: str,
    website_url: str,
    domain: str,
    error_type: str,
    message: str,
) -> WebsiteScan:
    """Mark a scan as failed and record the reason (§8 scan-level failure)."""
    scan = _get_or_create_scan(scan_id, company_id, website_url, domain)
    scan.status = ScanStatus.FAILED
    scan.completed_at = models.utcnow()
    scan.error_summary = message

    record_scan_error(scan_id, error_type, message, page_url=None)

    log.warning(
        "scan_failed",
        scan_id=scan_id,
        company_id=company_id,
        error_type=error_type,
        message=message,
    )

    return scan


def get_scan(scan_id: str) -> Optional[WebsiteScan]:
    return _scans.get(scan_id)


# --- pages ---------------------------------------------------------------


def save_page(scan_id: str, company_id: str, page: ExtractedPage) -> ScannedPage:
    """Persist one extracted page into `scanned_pages`."""
    row = ScannedPage(
        scan_id=scan_id,
        company_id=company_id,
        page_url=page.url,
        page_type=page.page_type,
        page_title=page.title,
        http_status=None,  # ExtractedPage doesn't retain the raw HTTP code
        clean_text=page.clean_text,
        metadata={
            "fetch_status": page.fetch_status.value,
            "meta_description": page.meta_description,
            "headings": page.headings,
            "language": page.language,
            "raw_text_length": page.raw_text_length,
        },
    )
    _pages[row.page_id] = row
    _pages_by_scan.setdefault(scan_id, []).append(row.page_id)
    return row


def get_scanned_pages(scan_id: str) -> list[ScannedPage]:
    return [_pages[page_id] for page_id in _pages_by_scan.get(scan_id, [])]


def get_page(page_id: str) -> Optional[ScannedPage]:
    return _pages.get(page_id)


# --- chunks ----------------------------------------------------------------


def save_chunk(page_id: str, company_id: str, chunk: Chunk) -> ContentChunkRecord:
    """Persist one chunk into `content_chunks`, linked to its scanned page."""
    row = ContentChunkRecord(
        page_id=page_id,
        company_id=company_id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        metadata={
            "page_url": chunk.page_url,
            "page_type": chunk.page_type.value,
            "title": chunk.title,
        },
    )
    _chunks[row.chunk_id] = row
    _chunks_by_page.setdefault(page_id, []).append(row.chunk_id)
    return row


def get_chunks_for_page(page_id: str) -> list[ContentChunkRecord]:
    return [_chunks[chunk_id] for chunk_id in _chunks_by_page.get(page_id, [])]


# --- website intelligence ---------------------------------------------------


def save_intelligence(
    company_id: str,
    scan_id: str,
    intelligence: WebsiteIntelligence,
) -> WebsiteIntelligenceRecord:
    """Persist the validated AI extraction output into `website_intelligence`."""
    row = WebsiteIntelligenceRecord(
        company_id=company_id,
        scan_id=scan_id,
        data=intelligence.model_dump(mode="json"),
    )
    _intelligence[row.intelligence_id] = row
    _intelligence_by_company.setdefault(company_id, []).append(row.intelligence_id)
    return row


def get_website_intelligence(company_id: str) -> Optional[WebsiteIntelligenceRecord]:
    """Return the most recently saved intelligence for a company, if any."""
    ids = _intelligence_by_company.get(company_id)
    if not ids:
        return None
    return _intelligence[ids[-1]]


# --- scan errors -------------------------------------------------------------


def record_scan_error(
    scan_id: str,
    error_type: str,
    message: str,
    page_url: Optional[str] = None,
) -> ScanError:
    """Persist one error into `scan_errors`.

    Used both for page-level errors (one page 404s, scan continues) and
    scan-level errors (`page_url=None`, see `fail_scan`).
    """
    row = ScanError(
        scan_id=scan_id,
        error_type=error_type,
        message=message,
        page_url=page_url,
    )
    _errors[row.error_id] = row
    _errors_by_scan.setdefault(scan_id, []).append(row.error_id)
    return row


def get_scan_errors(scan_id: str) -> list[ScanError]:
    return [_errors[error_id] for error_id in _errors_by_scan.get(scan_id, [])]
