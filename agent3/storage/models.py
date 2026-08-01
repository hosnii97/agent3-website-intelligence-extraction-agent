"""storage/models.py — Mission 12.

"The shape of our database tables": the 5 tables — website_scans, scanned_pages,
content_chunks, website_intelligence, scan_errors. See Agent3_Architecture.md §6.

These are plain dataclasses rather than an ORM's model classes: the project has
no database driver wired up yet (see requirements.txt), so `repository.py`
persists them in-memory. The dataclass shape below *is* the schema — swapping
in a real database later means adding a driver and mapping these same fields
to real columns, not redesigning them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from agent3.classification.page_classifier import PageType


def new_id(prefix: str) -> str:
    """Generate a unique, prefixed ID (e.g. "scan_ab12cd34...")."""
    return f"{prefix}_{uuid.uuid4().hex}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScanStatus(str, Enum):
    """Lifecycle of a website scan. See Agent3_Architecture.md §6/§8."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WebsiteScan:
    """One row in `website_scans` — one run of "scan this company's website"."""

    company_id: str
    website_url: str
    domain: str
    scan_id: str = field(default_factory=lambda: new_id("scan"))
    status: ScanStatus = ScanStatus.IN_PROGRESS
    pages_discovered: int = 0
    pages_scanned: int = 0
    pages_failed: int = 0
    started_at: datetime = field(default_factory=utcnow)
    completed_at: Optional[datetime] = None
    error_summary: Optional[str] = None


@dataclass
class ScannedPage:
    """One row in `scanned_pages` — one successfully extracted page."""

    scan_id: str
    company_id: str
    page_url: str
    page_type: PageType
    page_title: Optional[str]
    http_status: Optional[int]
    clean_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    page_id: str = field(default_factory=lambda: new_id("page"))
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class ContentChunkRecord:
    """One row in `content_chunks` — one chunk of a scanned page's text."""

    page_id: str
    company_id: str
    chunk_index: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_id: str = field(default_factory=lambda: new_id("chunk"))


@dataclass
class WebsiteIntelligenceRecord:
    """One row in `website_intelligence` — the validated AI extraction output."""

    company_id: str
    scan_id: str
    data: dict[str, Any]
    intelligence_id: str = field(default_factory=lambda: new_id("intel"))
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class ScanError:
    """One row in `scan_errors` — a page-level or scan-level failure.

    `page_url` is None for scan-level errors (e.g. homepage unreachable).
    """

    scan_id: str
    error_type: str
    message: str
    page_url: Optional[str] = None
    error_id: str = field(default_factory=lambda: new_id("err"))
    created_at: datetime = field(default_factory=utcnow)
