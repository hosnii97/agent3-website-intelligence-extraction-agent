"""ai/prompts/website_intelligence_prompt.py — Mission 11.

"The exact instructions we give the AI." This is the prompt engineering surface
of Agent 3: the text that turns a pile of scraped page chunks into a single,
grounded, schema-shaped JSON object.

Three things live here, and nothing else (all real logic is in `extractor.py`):

* ``SYSTEM_PROMPT`` — the model's role and the hard rules (JSON only, ground
  every field in a source URL, never invent facts).
* ``build_user_prompt(context, strict=False)`` — assembles the per-scan user
  message from the source-labeled page context. ``strict=True`` appends a
  firmer reminder, used on the single retry after a parse/validation failure
  (see Agent3_Architecture.md §10).
* ``WEBSITE_INTELLIGENCE_PROMPT`` — the base task text, kept as a module
  constant because `extractor.py` imports it by name and older callers/tests
  may reference it directly.

The design choices here are the mission's "Course Connection" checklist made
concrete: prompt engineering (explicit role + rules), structured JSON output
(a spelled-out schema, "respond with JSON and nothing else"), grounding /
source-aware answers (every value cites the URLs it came from), and refusal
when unsupported (`not_available` instead of a guess).
"""

from __future__ import annotations

from agent3.ai.schemas import NOT_AVAILABLE

# The literal JSON skeleton we show the model. Keeping it as text (rather than
# generating it from the pydantic schema) lets us annotate each field in plain
# language — the model follows an annotated example far more reliably than a
# bare type definition. This mirrors `WebsiteIntelligence` in ai/schemas.py; if
# you add a field there, add it here too.
_OUTPUT_SHAPE = f"""{{
  "company_overview":      {{ "value": "...", "confidence": "high|medium|low", "sources": ["<url>", ...] }},
  "products_and_services": {{ "value": "...", "confidence": "high|medium|low", "sources": ["<url>", ...] }},
  "pricing":               {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "target_customers":      {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "customer_journey":      {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "use_cases":             {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "blog_topics":           {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "case_studies":          {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "contact_details":       {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "terms_summary":         {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "privacy_summary":       {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "refund_policy":         {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "legal_indicators":      {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "calls_to_action":       {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "key_claims":            {{ "value": "...", "confidence": "...", "sources": ["<url>"] }}  | null,
  "legal_pages": {{
    "terms_available": true|false,
    "privacy_policy_available": true|false,
    "refund_policy_available": true|false,
    "cookie_policy_available": true|false,
    "sources": ["<url>", ...]
  }},
  "missing_information": ["<short label of a category you looked for but could not ground>", ...]
}}"""

SYSTEM_PROMPT = (
    "You are a precise website-intelligence analyst. You are given text that was "
    "scraped from the pages of one company's website, and your only job is to "
    "extract structured business information from it.\n"
    "\n"
    "Hard rules — follow every one:\n"
    "1. Respond with a SINGLE JSON object and nothing else. No prose, no "
    "markdown, no code fences, no explanation before or after.\n"
    "2. Ground every field. A field's `sources` array must contain only URLs "
    "that appear in the provided context and that actually support the value. "
    "Never cite a URL that is not in the context.\n"
    "3. Never invent, assume, or infer facts that are not stated in the "
    f"context. If you cannot support a value from the text, use \"{NOT_AVAILABLE}\" "
    "for a required field (with an empty sources list) or `null` for an "
    "optional field — do NOT guess.\n"
    "4. Set `confidence` honestly: \"high\" when the text states it plainly, "
    "\"medium\" when it is implied or partial, \"low\" when it is a weak "
    "signal.\n"
    "5. List every category you looked for but could not ground in "
    "`missing_information`.\n"
    "6. Extraction, not creativity: summarize what the site says, do not "
    "market on its behalf."
)

# Base task text. `build_user_prompt` wraps this with the actual page context;
# it is also exported on its own as WEBSITE_INTELLIGENCE_PROMPT for callers that
# want just the instruction block.
WEBSITE_INTELLIGENCE_PROMPT = (
    "Extract structured website intelligence from the company website content "
    "below and return it as one JSON object with EXACTLY this shape "
    "(optional fields may be null):\n"
    "\n"
    f"{_OUTPUT_SHAPE}\n"
    "\n"
    "Field guidance:\n"
    "- company_overview: what the company is and does, in 1-3 sentences.\n"
    "- products_and_services: the main products/services offered.\n"
    "- pricing: pricing model, plans, or figures if present.\n"
    "- target_customers: who the product is for (segments, industries, roles).\n"
    "- customer_journey: how a customer signs up / onboards / gets started.\n"
    "- use_cases: concrete problems the product solves.\n"
    "- blog_topics: the themes covered in the blog/resources, if any.\n"
    "- case_studies: named customer stories or results, if any.\n"
    "- contact_details: emails, phone numbers, addresses, contact routes.\n"
    "- terms_summary / privacy_summary / refund_policy: a short summary of each "
    "legal document IF its text is present in the context.\n"
    "- legal_indicators: trust/compliance signals (certifications, GDPR, SOC2, "
    "guarantees).\n"
    "- calls_to_action: the primary actions the site pushes (\"Book a demo\", "
    "\"Start free trial\").\n"
    "- key_claims: notable promises or claims the company makes about itself.\n"
    "- legal_pages: booleans for whether each policy page exists on the site "
    "(true even if you only saw a link/title for it), plus the URLs.\n"
)

# Appended on the retry after a failed parse/validation. Short, blunt, and
# specifically about the two failure modes we actually see: non-JSON wrappers
# and ungrounded/invented sources.
_STRICT_RETRY_REMINDER = (
    "\n\nIMPORTANT — your previous response could not be parsed as the required "
    "JSON object. Reply with ONLY the raw JSON object: no markdown, no code "
    "fences, no commentary. Double-check that every URL in every `sources` list "
    "appears verbatim in the context below, and that the JSON is syntactically "
    "valid."
)


def build_context_block(context: str) -> str:
    """Wrap the assembled page context in clear delimiters for the model."""
    return f"--- BEGIN WEBSITE CONTENT ---\n{context}\n--- END WEBSITE CONTENT ---"


def build_user_prompt(context: str, strict: bool = False) -> str:
    """Build the full user message: task instructions + the page context.

    Args:
        context: Source-labeled page text assembled by `extractor.py`
            (each block prefixed with the URL it came from, so the model can
            cite it). May be empty — the instructions still hold.
        strict: When True, append the stricter reminder used on the single
            retry after a parse/validation failure.

    Returns:
        The complete user-turn string to send to the model.
    """
    prompt = f"{WEBSITE_INTELLIGENCE_PROMPT}\n\n{build_context_block(context)}"
    if strict:
        prompt += _STRICT_RETRY_REMINDER
    return prompt
