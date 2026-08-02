"""ai/schemas.py — Mission 11.

The exact JSON shape the AI must return, as pydantic models. `extractor.py`
validates the raw LLM output against `WebsiteIntelligence`; anything that
doesn't fit these types is rejected and retried, so downstream consumers
(storage, the API summary) can trust the shape without re-checking it.

Design notes
------------
* Every substantive field is a `SourcedField` — a value the model must be
  able to point back to a source URL for. This is how Mission 11's grounding
  requirement ("every insight connected to a source URL") is encoded in the
  type system rather than left to prose in the prompt.
* This expands the contract sketched in Agent3_Architecture.md §4 to cover the
  full "Information to Extract" list in the mission brief. The two fields the
  architecture pinned as required (`company_overview`, `products_and_services`)
  stay required; everything else is optional and defaults to absent, so a small
  site that only has a homepage still produces a valid object.
* `legal_pages` is a typed `LegalPages` model rather than the bare `dict` in
  §4 — it still serializes to a plain JSON object, but the boolean flags are
  now validated and safe for `api/schemas.py` to read for `extractedDataSummary`.
* Kept Python 3.9-safe on purpose (`Optional[...]`, `list[...]`, no `X | Y`
  unions) so this module — and the tests that import it — run on the 3.9
  interpreter this project is currently pinned to.

The sentinel string for "we looked but this genuinely isn't on the site" is
`NOT_AVAILABLE`; the extractor uses it when it has to keep a required field but
has no grounded evidence for it.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl

# The one canonical "we couldn't find this" marker. Kept here (next to the
# schema) so the prompt, the extractor, and any consumer all agree on the
# exact string instead of each inventing their own ("n/a", "unknown", ...).
NOT_AVAILABLE = "not_available"

Confidence = Literal["high", "medium", "low"]


class SourcedField(BaseModel):
    """One AI-extracted fact, grounded in the page(s) it came from.

    A field the model cannot point to a real source for must not be invented:
    the extractor either drops it (optional fields) or collapses it to
    `NOT_AVAILABLE` with an empty `sources` list (required fields). A meaningful
    `value` with an empty `sources` list is therefore always treated as
    ungrounded and cleaned up before the object is returned.

    Attributes:
        value: The extracted text, or `NOT_AVAILABLE` when nothing was found.
        confidence: How sure the model is — "high" / "medium" / "low".
        sources: The page URLs this value was drawn from (grounding evidence).
    """

    value: str
    confidence: Confidence = "low"
    sources: list[HttpUrl] = Field(default_factory=list)

    def is_available(self) -> bool:
        """True when this field holds a real, non-sentinel value."""
        return bool(self.value) and self.value.strip().lower() != NOT_AVAILABLE


class LegalPages(BaseModel):
    """Which legal/policy pages exist on the site, plus where we saw them.

    Booleans (never omitted) so a caller can rely on the key always being
    present — mirrors the `extractedDataSummary` contract in
    Agent3_API_Contract.md §4.2.
    """

    terms_available: bool = False
    privacy_policy_available: bool = False
    refund_policy_available: bool = False
    cookie_policy_available: bool = False
    sources: list[HttpUrl] = Field(default_factory=list)


class WebsiteIntelligence(BaseModel):
    """The exact JSON shape the extraction LLM (Mission 11) must return.

    `company_overview` and `products_and_services` are required (per
    Agent3_Architecture.md §4); every other insight is optional and absent
    (`None`) when the site didn't support it. `missing_information` lists, in
    plain words, the categories the model looked for but couldn't ground —
    this is the honest "here's what we don't know" channel that keeps the
    model from padding empty fields with guesses.
    """

    # --- required core (always present on any real company site) ---
    company_overview: SourcedField
    products_and_services: SourcedField

    # --- commercial / audience ---
    pricing: Optional[SourcedField] = None
    target_customers: Optional[SourcedField] = None
    customer_journey: Optional[SourcedField] = None
    use_cases: Optional[SourcedField] = None

    # --- content / social proof ---
    blog_topics: Optional[SourcedField] = None
    case_studies: Optional[SourcedField] = None

    # --- contact ---
    contact_details: Optional[SourcedField] = None

    # --- legal / trust summaries ---
    terms_summary: Optional[SourcedField] = None
    privacy_summary: Optional[SourcedField] = None
    refund_policy: Optional[SourcedField] = None
    legal_indicators: Optional[SourcedField] = None

    # --- marketing signals ---
    calls_to_action: Optional[SourcedField] = None
    key_claims: Optional[SourcedField] = None

    # --- rollups ---
    legal_pages: LegalPages = Field(default_factory=LegalPages)
    missing_information: list[str] = Field(default_factory=list)


# The optional SourcedField insights, in output order. Defined at module level
# (not as a class attribute) so pydantic doesn't mistake it for a model field.
# The extractor iterates this to clean ungrounded optional fields uniformly.
OPTIONAL_SOURCED_FIELDS = (
    "pricing",
    "target_customers",
    "customer_journey",
    "use_cases",
    "blog_topics",
    "case_studies",
    "contact_details",
    "terms_summary",
    "privacy_summary",
    "refund_policy",
    "legal_indicators",
    "calls_to_action",
    "key_claims",
)
