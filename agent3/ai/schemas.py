"""ai/schemas.py — Mission 11.

The exact JSON shape the AI must return, as pydantic models: SourcedField and
WebsiteIntelligence. `extractor.py` validates the LLM output against these.
See Agent3_Architecture.md §4.
"""

from typing import Literal, Optional

from pydantic import BaseModel, HttpUrl


class SourcedField(BaseModel):
    """One AI-extracted field, grounded in the page(s) it came from.

    A field the model cannot point to a source for must be omitted/None,
    never guessed.
    """

    value: str
    confidence: Literal["high", "medium", "low"]
    sources: list[HttpUrl]


class WebsiteIntelligence(BaseModel):
    """The exact JSON shape the extraction LLM (Mission 11) must return.

    `extractor.py` still needs to implement the LLM call + retry logic —
    this schema is added ahead of that so downstream consumers (storage)
    have a type to depend on. See Agent3_Architecture.md §4.
    """

    company_overview: SourcedField
    products_and_services: SourcedField
    pricing: Optional[SourcedField] = None
    target_customers: Optional[SourcedField] = None
    case_studies: Optional[SourcedField] = None
    contact_details: Optional[SourcedField] = None
    legal_pages: dict
    missing_information: list[str]
