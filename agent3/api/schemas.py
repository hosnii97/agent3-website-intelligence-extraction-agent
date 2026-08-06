"""api/schemas.py — Mission 13.

Request/response shapes for the API (pydantic). Keeps the HTTP contract separate
from the internal domain models.
"""

from __future__ import annotations

from typing import Optional, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent3.ai.schemas import WebsiteIntelligence


from agent3.common import config
from datetime import datetime

class ApiModel(BaseModel):
    """Base class shared by all Agent 3 API models."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )


class ScanOptions(ApiModel):
    """Optional website scan configuration."""

    max_pages: int = Field(
        default=config.MAX_PAGES_PER_SCAN,
        alias="maxPages",
        ge=1,
        le=50,
    )

    force_rescan: bool = Field(
        default=False,
        alias="forceRescan",
    )

    callback_url: Optional[str] = Field(
        default=None,
        alias="callbackUrl",
    )

    @field_validator("callback_url")
    @classmethod
    def validate_callback_url(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        """The API contract only permits HTTPS callback URLs."""

        if value is not None and not value.startswith("https://"):
            raise ValueError(
                "callbackUrl must be an absolute HTTPS URL"
            )

        return value


class ScanWebsiteRequest(ApiModel):
    """Request body for POST /scan-website."""

    company_id: str = Field(
        alias="companyId",
        min_length=1,
    )

    website_url: str = Field(
        alias="websiteUrl",
        min_length=1,
        max_length=config.MAX_URL_LENGTH,
    )

    domain: Optional[str] = None

    options: ScanOptions = Field(
        default_factory=ScanOptions,
    )

    @field_validator("company_id")
    @classmethod
    def validate_company_id(cls, value: str) -> str:
        """Reject a blank company ID."""

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("companyId must not be empty")

        return cleaned_value


class ExtractedDataSummary(ApiModel):
    """Boolean summary of the content found during a scan."""

    has_pricing: bool = Field(
        default=False,
        alias="hasPricing",
    )

    has_blog: bool = Field(
        default=False,
        alias="hasBlog",
    )

    has_terms: bool = Field(
        default=False,
        alias="hasTerms",
    )

    has_privacy_policy: bool = Field(
        default=False,
        alias="hasPrivacyPolicy",
    )

    has_case_studies: bool = Field(
        default=False,
        alias="hasCaseStudies",
    )


class ScanResponse(ApiModel):
    """Successful response for starting or checking a scan."""

    company_id: str = Field(alias="companyId")
    scan_id: str = Field(alias="scanId")

    status: Literal[
        "in_progress",
        "completed",
    ]

    pages_scanned: Optional[int] = Field(
        default=None,
        alias="pagesScanned",
    )

    pages_failed: Optional[int] = Field(
        default=None,
        alias="pagesFailed",
    )

    extracted_data_summary: Optional[
        ExtractedDataSummary
    ] = Field(
        default=None,
        alias="extractedDataSummary",
    )

    started_at: datetime = Field(alias="startedAt")

    completed_at: Optional[datetime] = Field(
        default=None,
        alias="completedAt",
    )


class ErrorResponse(ApiModel):
    """Standard error response defined by the API contract."""

    company_id: Optional[str] = Field(
        default=None,
        alias="companyId",
    )

    scan_id: Optional[str] = Field(
        default=None,
        alias="scanId",
    )

    status: Literal[
        "error",
        "failed",
    ]

    error_type: str = Field(alias="errorType")
    message: str
    retryable: bool

    details: Optional[dict[str, Any]] = None


# Re-export the shared intelligence schema through the API schema module.
# This keeps the AI and API layers on the same data contract.
WebsiteIntelligenceResponse = WebsiteIntelligence