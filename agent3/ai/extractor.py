"""ai/extractor.py — Mission 11.

"Send the prompt, get JSON back, check it's valid." This is the module the
orchestrator calls once per scan: given the page chunks, it produces one
grounded, validated `WebsiteIntelligence` object (or `None` if the model can't
deliver one). See Agent3_Architecture.md §10.

The flow, end to end:

    chunks
      │  1. select the most useful chunks within a context budget
      │     (page-type priority + round-robin, so every important page
      │      contributes before any one page is read in depth)
      ▼
    context (each block labeled with its source URL)
      │  2. call the LLM at temperature 0 (deterministic extraction)
      ▼
    raw text
      │  3. parse JSON (tolerating markdown fences)
      │  4. validate against the WebsiteIntelligence pydantic schema
      │     — on failure, retry ONCE with a stricter reminder, then give up
      ▼
    WebsiteIntelligence
      │  5. enforce grounding: drop any source URL the model cited that
      │     wasn't actually in the context; collapse fields left ungrounded
      ▼
    grounded WebsiteIntelligence  (or None)

Design choices worth knowing:

* **The LLM client is injected.** `extract_structured_intelligence(chunks,
  client=...)` takes an optional client so tests run fully offline with a fake,
  and production passes nothing (a real Anthropic client is built lazily).
* **RAG is not required here.** Architecture §10/§13 make retrieval an additive
  layer; the fixed pipeline works standalone. Chunk selection by page type is
  the lightweight stand-in, so this module has no numpy/faiss dependency and
  runs anywhere the rest of Agent 3 runs.
* **Failures are data, not exceptions.** A missing API key, a network error, an
  unparseable reply, or a validation failure all end in a logged `None`, never
  a crash — one AI hiccup must not sink a whole scan (§13).
* **Grounding is enforced in code, not just asked for in the prompt.** The
  prompt requests source URLs; this module then *verifies* them, which is what
  makes "the model does not invent unsupported facts" a guarantee rather than a
  hope.

Kept Python 3.9-safe (`Optional[...]`, no `X | Y` unions) so it imports and
tests on the interpreter this project is currently pinned to.
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from typing import Any, Iterable, Optional

from pydantic import ValidationError

from agent3.ai.schemas import (
    NOT_AVAILABLE,
    OPTIONAL_SOURCED_FIELDS,
    SourcedField,
    WebsiteIntelligence,
)
from agent3.ai.prompts.website_intelligence_prompt import (
    SYSTEM_PROMPT,
    WEBSITE_INTELLIGENCE_PROMPT,
    build_user_prompt,
)
from agent3.extraction.chunker import Chunk
from agent3.common import config
from agent3.common import logging as log

# Two required fields (Agent3_Architecture.md §4) that can never be null: if the
# model can't ground them, they collapse to NOT_AVAILABLE rather than vanish.
# The value is the human label used in `missing_information` when that happens.
_REQUIRED_FIELDS = {
    "company_overview": "company overview",
    "products_and_services": "products and services",
}

# Lower number = read this page type sooner. Blog/general/unknown are
# deprioritized (a blog post rarely holds the company overview or pricing);
# legal pages sit mid-pack because we DO want their text for the policy
# summaries. Anything not listed falls to the back via the default.
_PAGE_TYPE_PRIORITY = {
    "homepage": 0,
    "about": 1,
    "product": 2,
    "service": 3,
    "pricing": 4,
    "customer": 5,
    "case_study": 6,
    "use_case": 7,
    "faq": 8,
    "contact": 9,
    "terms": 10,
    "privacy_policy": 11,
    "refund_policy": 12,
    "cookie_policy": 13,
    "legal": 14,
    "career": 15,
    "blog": 16,
    "general": 17,
    "unknown": 18,
}
_DEFAULT_PRIORITY = 99


# --- public API -------------------------------------------------------------


def extract_structured_intelligence(
    chunks: list[Chunk],
    client: Optional[Any] = None,
) -> Optional[WebsiteIntelligence]:
    """Extract one grounded `WebsiteIntelligence` object from a scan's chunks.

    This is the single entry point the orchestrator calls (Mission 11 step in
    `scan_pipeline.py`). It selects the most useful chunks, asks the LLM for
    structured JSON, validates and grounds the result, and returns it.

    Args:
        chunks: All chunks produced for one company's scan (Mission 10 output).
            An empty list yields `None` (nothing to extract from).
        client: An optional object exposing `messages.create(...)` like the
            Anthropic SDK. Injected in tests so no API key or network is needed;
            when omitted, a real Anthropic client is built lazily.

    Returns:
        A validated, source-grounded `WebsiteIntelligence`, or `None` if there
        was nothing to extract or the model could not produce valid output
        after one retry. Never raises for an AI/network failure — it logs and
        returns `None` so the surrounding scan still completes.
    """
    if not chunks:
        log.info("ai_extraction_skipped_no_chunks")
        return None

    selected = _select_context_chunks(chunks, config.LLM_MAX_CONTEXT_CHARS)
    context = _build_context(selected)
    allowed_sources = _normalized_source_set(selected)

    client = client or _build_default_client()
    if client is None:
        # No usable LLM client (missing package or API key). Degrade, don't die.
        log.error("ai_extraction_unavailable", reason="no_llm_client")
        return None

    log.info(
        "ai_extraction_started",
        chunks=len(chunks),
        selected=len(selected),
        context_chars=len(context),
    )

    # One initial attempt + one stricter retry, per Architecture §10.
    for attempt in (1, 2):
        strict = attempt == 2
        user_prompt = build_user_prompt(context, strict=strict)

        try:
            raw = _complete(client, SYSTEM_PROMPT, user_prompt)
        except Exception as exc:  # network/SDK error — retry, then give up
            log.error("ai_extraction_call_failed", attempt=attempt, error=str(exc))
            continue

        data = _parse_json(raw)
        if data is None:
            log.warning("ai_output_parsing_failed", attempt=attempt)
            continue

        data = _presanitize(data)
        try:
            intelligence = WebsiteIntelligence.model_validate(data)
        except ValidationError as exc:
            log.warning(
                "ai_output_validation_failed",
                attempt=attempt,
                error=str(exc)[:200],
            )
            continue

        grounded = _enforce_grounding(intelligence, allowed_sources)
        log.info("ai_extraction_completed", attempt=attempt)
        return grounded

    log.error("ai_extraction_failed", reason="exhausted_retries")
    return None


def extracted_data_summary(intelligence: Optional[WebsiteIntelligence]) -> dict:
    """Boolean rollup for the API's `extractedDataSummary` (Contract §4.2).

    A cheap "does this company have X, yes/no" view of the full intelligence
    object, so a caller (Agent 1) can make quick decisions without pulling the
    whole payload. All keys are always present (never omitted).
    """
    if intelligence is None:
        return {
            "hasPricing": False,
            "hasBlog": False,
            "hasTerms": False,
            "hasPrivacyPolicy": False,
            "hasCaseStudies": False,
        }

    legal = intelligence.legal_pages
    return {
        "hasPricing": _has_value(intelligence.pricing),
        "hasBlog": _has_value(intelligence.blog_topics),
        "hasTerms": legal.terms_available or _has_value(intelligence.terms_summary),
        "hasPrivacyPolicy": (
            legal.privacy_policy_available or _has_value(intelligence.privacy_summary)
        ),
        "hasCaseStudies": _has_value(intelligence.case_studies),
    }


# --- chunk selection & context ----------------------------------------------


def _select_context_chunks(chunks: list[Chunk], max_chars: int) -> list[Chunk]:
    """Pick the chunks to send to the model, within a character budget.

    Strategy: group chunks by their page, order pages by how useful their type
    is (`_PAGE_TYPE_PRIORITY`), then read *breadth-first* — chunk 0 of every
    page in priority order, then chunk 1 of every page, and so on — stopping
    once the budget is spent. Breadth-first matters for one-shot extraction:
    it guarantees every important page contributes something before the budget
    is eaten by the long tail of a single big page.
    """
    if max_chars <= 0:
        return []

    # Group by page URL, preserving the order pages first appeared.
    by_page: "OrderedDict[str, list[Chunk]]" = OrderedDict()
    for chunk in chunks:
        by_page.setdefault(chunk.page_url, []).append(chunk)

    # Within each page, read low chunk_index first (top of the page first).
    for page_chunks in by_page.values():
        page_chunks.sort(key=lambda c: c.chunk_index)

    # Order pages by type priority. Python's sort is stable, so pages of equal
    # priority keep their first-seen order.
    ordered_pages = sorted(
        by_page.values(),
        key=lambda page_chunks: _page_priority(page_chunks[0].page_type),
    )

    selected: list[Chunk] = []
    total_chars = 0
    max_depth = max((len(p) for p in ordered_pages), default=0)
    for depth in range(max_depth):
        for page_chunks in ordered_pages:
            if depth >= len(page_chunks):
                continue
            chunk = page_chunks[depth]
            chunk_chars = len(chunk.text)
            # Always take at least one chunk; after that, respect the budget.
            if selected and total_chars + chunk_chars > max_chars:
                return selected
            selected.append(chunk)
            total_chars += chunk_chars
    return selected


def _page_priority(page_type: Any) -> int:
    """Priority rank for a page type (accepts a PageType enum or a plain str)."""
    key = getattr(page_type, "value", page_type)
    if isinstance(key, str):
        key = key.lower()
    return _PAGE_TYPE_PRIORITY.get(key, _DEFAULT_PRIORITY)


def _build_context(chunks: Iterable[Chunk]) -> str:
    """Render selected chunks into one source-labeled context string.

    Every block is prefixed with the URL (and title, if any) it came from, so
    the model has a URL to cite in each field's `sources` — grounding starts
    with making the source visible.
    """
    blocks: list[str] = []
    for chunk in chunks:
        header = f"[source: {chunk.page_url}]"
        if chunk.title:
            header += f" (title: {chunk.title})"
        blocks.append(f"{header}\n{chunk.text}")
    return "\n\n".join(blocks)


# --- LLM call ---------------------------------------------------------------


def _build_default_client() -> Optional[Any]:
    """Build a real Anthropic client, or return None if that's not possible.

    Constructed lazily (and defensively) so importing this module never
    requires the `anthropic` package or an API key — only actually running an
    extraction does. A missing dependency/key degrades to `None` (logged),
    which the caller turns into a `None` result rather than a crash.
    """
    try:
        import anthropic
    except ImportError:
        log.error("ai_client_unavailable", reason="anthropic_package_not_installed")
        return None
    try:
        return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    except Exception as exc:  # e.g. no API key configured
        log.error("ai_client_unavailable", reason=str(exc))
        return None


def _complete(client: Any, system_prompt: str, user_prompt: str) -> str:
    """Send one message to the model and return its text.

    Uses temperature 0 (from config) — this is extraction, not writing, so we
    want the same input to give the same output.
    """
    response = client.messages.create(
        model=config.LLM_MODEL,
        max_tokens=config.LLM_MAX_OUTPUT_TOKENS,
        temperature=config.LLM_TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return _text_from_response(response)


def _text_from_response(response: Any) -> str:
    """Pull the plain text out of an Anthropic-style response.

    Tolerant of shapes so tests can pass a lightweight fake: accepts a bare
    string, an object with a `.content` list of text blocks (real SDK), or a
    list of dicts with a "text" key.
    """
    if isinstance(response, str):
        return response

    content = getattr(response, "content", None)
    if content is None:
        return str(response)

    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            parts.append(text)
    return "".join(parts)


# --- parsing & sanitizing ---------------------------------------------------

_FENCE_OPEN = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_FENCE_CLOSE = re.compile(r"\s*```$")


def _parse_json(text: Optional[str]) -> Optional[dict]:
    """Parse the model's reply into a dict, tolerating markdown code fences.

    Returns None (never raises) when the text can't be read as a JSON object,
    so the caller can log `ai_output_parsing_failed` and retry.
    """
    if not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _FENCE_OPEN.sub("", cleaned)
        cleaned = _FENCE_CLOSE.sub("", cleaned).strip()

    parsed = _loads_object(cleaned)
    if parsed is not None:
        return parsed

    # Last resort: grab the outermost {...} span and try that. Handles a model
    # that wrapped the JSON in a sentence despite instructions.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        return _loads_object(cleaned[start : end + 1])
    return None


def _loads_object(text: str) -> Optional[dict]:
    """json.loads that only accepts a JSON object (dict), else None."""
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _presanitize(data: dict) -> dict:
    """Light cleanup before pydantic validation.

    The model occasionally emits a `sources` value that isn't a clean list of
    URL strings (a lone string, a null, a non-URL note). Rather than let one
    stray entry fail validation of an otherwise-good object, coerce every
    `sources` list to URL-looking strings here. Grounding (later) still has the
    final say on which of those survive.
    """
    for value in data.values():
        if isinstance(value, dict) and "sources" in value:
            value["sources"] = _clean_source_list(value.get("sources"))
    return data


def _clean_source_list(sources: Any) -> list:
    """Coerce a `sources` field into a list of http(s) URL strings."""
    if isinstance(sources, str):
        sources = [sources]
    if not isinstance(sources, list):
        return []
    return [
        s
        for s in sources
        if isinstance(s, str) and s.strip().lower().startswith(("http://", "https://"))
    ]


# --- grounding --------------------------------------------------------------


def _enforce_grounding(
    intelligence: WebsiteIntelligence,
    allowed_sources: set,
) -> WebsiteIntelligence:
    """Strip ungrounded evidence, then clean up the fields that are left.

    For every sourced field, drop any URL that wasn't actually in the context
    we sent (a cited-but-unseen URL is, by definition, unsupported). Then:
      * a required field left with no value or no source becomes NOT_AVAILABLE;
      * an optional field left with no value or no source becomes None (dropped);
    and each field cleaned this way is recorded in `missing_information`. This
    is where "every insight is connected to a source URL" is enforced.
    """
    missing = list(intelligence.missing_information)

    # Required fields: can't be null — collapse to NOT_AVAILABLE if ungrounded.
    for name, label in _REQUIRED_FIELDS.items():
        field = getattr(intelligence, name)
        _filter_sources(field, allowed_sources, label)
        if not field.is_available() or not field.sources:
            setattr(
                intelligence,
                name,
                SourcedField(value=NOT_AVAILABLE, confidence="low", sources=[]),
            )
            missing.append(label)

    # Optional fields: drop entirely (None) if ungrounded.
    for name in OPTIONAL_SOURCED_FIELDS:
        field = getattr(intelligence, name)
        if field is None:
            continue
        _filter_sources(field, allowed_sources, name)
        if not field.is_available() or not field.sources:
            setattr(intelligence, name, None)
            missing.append(_humanize(name))

    # legal_pages carries its own source list; ground it the same way.
    intelligence.legal_pages.sources = [
        url
        for url in intelligence.legal_pages.sources
        if _normalize_url(url) in allowed_sources
    ]

    intelligence.missing_information = _dedupe_preserving_order(missing)
    return intelligence


def _filter_sources(field: SourcedField, allowed: set, label: str) -> None:
    """Drop any of a field's sources not present in the allowed (context) set."""
    kept = [url for url in field.sources if _normalize_url(url) in allowed]
    dropped = len(field.sources) - len(kept)
    if dropped:
        log.warning("ai_source_dropped_ungrounded", field=label, dropped=dropped)
    field.sources = kept


def _normalized_source_set(chunks: Iterable[Chunk]) -> set:
    """The set of source URLs a field is allowed to cite (normalized)."""
    return {_normalize_url(chunk.page_url) for chunk in chunks}


def _normalize_url(url: Any) -> str:
    """Normalize a URL for tolerant equality.

    pydantic's HttpUrl appends a trailing slash to a bare domain
    ("https://x.com" -> "https://x.com/") while the crawler strips trailing
    slashes; normalizing both sides (lowercase, no single trailing slash) lets
    a grounded citation match the chunk it came from despite that drift.
    """
    text = str(url).strip().lower()
    if text.endswith("/"):
        text = text[:-1]
    return text


# --- small helpers ----------------------------------------------------------


def _has_value(field: Optional[SourcedField]) -> bool:
    """True when an optional field is present and holds a real (grounded) value."""
    return field is not None and field.is_available() and bool(field.sources)


def _humanize(field_name: str) -> str:
    """"target_customers" -> "target customers" for missing_information labels."""
    return field_name.replace("_", " ")


def _dedupe_preserving_order(items: Iterable[str]) -> list:
    """De-duplicate while keeping first-seen order (stable, readable output)."""
    seen: set = set()
    result: list = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
