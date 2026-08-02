"""Mission 11 — unit tests for ai/extractor.py.

These tests run FULLY OFFLINE: a `FakeLLMClient` stands in for the Anthropic
client (injected via the `client=` argument), so no API key and no network are
ever needed. Each test scripts the exact reply(ies) the fake returns, which
lets us assert the extractor's behavior on every branch of Architecture §10:
parsing, validation, the single retry, grounding, and graceful failure.

Covered behaviors:
  * valid JSON is parsed, validated, and returned
  * JSON wrapped in a ```json ... ``` fence is still parsed
  * an invalid first reply triggers exactly one retry; a good second reply wins
  * two bad replies exhaust the retry and return None (never raises)
  * a network/SDK exception on the call is caught and retried
  * grounding drops sources that weren't in the context...
  * ...collapsing an ungrounded REQUIRED field to not_available
  * ...and dropping an ungrounded OPTIONAL field to None
  * empty chunks short-circuit to None (no client call)
  * missing/None client returns None instead of crashing
  * chunk selection respects the context-char budget and page-type priority
  * extracted_data_summary reports the right booleans (incl. the None case)
"""

from __future__ import annotations

import json

import pytest

from agent3.ai import extractor
from agent3.ai.schemas import NOT_AVAILABLE, SourcedField, WebsiteIntelligence
from agent3.extraction.chunker import Chunk


# --- test doubles -----------------------------------------------------------


class _TextBlock:
    """Mimics an Anthropic content block (has a `.text` attribute)."""

    def __init__(self, text: str) -> None:
        self.text = text


class _Response:
    """Mimics an Anthropic message response (`.content` = list of blocks)."""

    def __init__(self, text: str) -> None:
        self.content = [_TextBlock(text)]


class FakeLLMClient:
    """Scriptable stand-in for `anthropic.Anthropic()`.

    Give it a list of replies (strings) or exceptions; each `messages.create`
    call pops the next one. A string is returned as a response; an exception
    instance is raised (to simulate a network/SDK failure). Records every call
    so tests can assert how many turns happened and what was sent.
    """

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    class _Messages:
        def __init__(self, outer: "FakeLLMClient") -> None:
            self._outer = outer

        def create(self, **kwargs):
            self._outer.calls.append(kwargs)
            reply = self._outer._replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return _Response(reply)

    @property
    def messages(self) -> "FakeLLMClient._Messages":
        return FakeLLMClient._Messages(self)


# --- fixtures / builders ----------------------------------------------------


def _chunk(url: str, page_type: str = "homepage", index: int = 0, text: str = "Some text.", title=None) -> Chunk:
    return Chunk(
        company_id="company_123",
        page_url=url,
        page_type=page_type,
        chunk_index=index,
        title=title,
        text=text,
    )


def _default_chunks():
    return [
        _chunk("https://acme.com", "homepage", 0,
               "Acme builds workflow automation software for sales teams."),
        _chunk("https://acme.com/pricing", "pricing", 0,
               "Acme offers three plans: Starter, Pro, and Enterprise."),
    ]


def _valid_payload(**overrides) -> dict:
    """A minimal, fully-grounded WebsiteIntelligence payload the fake can return."""
    payload = {
        "company_overview": {
            "value": "Acme builds workflow automation software for sales teams.",
            "confidence": "high",
            "sources": ["https://acme.com"],
        },
        "products_and_services": {
            "value": "Workflow automation software.",
            "confidence": "high",
            "sources": ["https://acme.com"],
        },
        "pricing": {
            "value": "Three plans: Starter, Pro, Enterprise.",
            "confidence": "medium",
            "sources": ["https://acme.com/pricing"],
        },
        "legal_pages": {
            "terms_available": False,
            "privacy_policy_available": False,
            "refund_policy_available": False,
            "cookie_policy_available": False,
            "sources": [],
        },
        "missing_information": [],
    }
    payload.update(overrides)
    return payload


def _json(payload: dict) -> str:
    return json.dumps(payload)


# --- happy path -------------------------------------------------------------


def test_valid_json_is_parsed_and_returned():
    client = FakeLLMClient([_json(_valid_payload())])
    result = extractor.extract_structured_intelligence(_default_chunks(), client=client)

    assert isinstance(result, WebsiteIntelligence)
    assert result.company_overview.value.startswith("Acme builds")
    assert result.pricing is not None
    assert len(client.calls) == 1  # no retry needed


def test_call_uses_temperature_zero_and_configured_model():
    client = FakeLLMClient([_json(_valid_payload())])
    extractor.extract_structured_intelligence(_default_chunks(), client=client)

    sent = client.calls[0]
    assert sent["temperature"] == 0.0          # deterministic extraction (§10)
    assert sent["model"]                        # a model name was passed
    assert isinstance(sent["messages"], list) and sent["messages"]


def test_context_sent_to_model_labels_each_source_url():
    client = FakeLLMClient([_json(_valid_payload())])
    extractor.extract_structured_intelligence(_default_chunks(), client=client)

    user_msg = client.calls[0]["messages"][0]["content"]
    # Grounding starts by making the source visible to the model.
    assert "https://acme.com" in user_msg
    assert "https://acme.com/pricing" in user_msg


def test_json_wrapped_in_markdown_fence_is_parsed():
    fenced = "```json\n" + _json(_valid_payload()) + "\n```"
    client = FakeLLMClient([fenced])
    result = extractor.extract_structured_intelligence(_default_chunks(), client=client)

    assert isinstance(result, WebsiteIntelligence)
    assert len(client.calls) == 1


def test_json_embedded_in_prose_is_recovered():
    messy = "Sure, here is the data:\n" + _json(_valid_payload()) + "\nHope that helps!"
    client = FakeLLMClient([messy])
    result = extractor.extract_structured_intelligence(_default_chunks(), client=client)

    assert isinstance(result, WebsiteIntelligence)


# --- retry behavior (Architecture §10) --------------------------------------


def test_invalid_then_valid_retries_once_and_succeeds():
    client = FakeLLMClient(["this is not json at all", _json(_valid_payload())])
    result = extractor.extract_structured_intelligence(_default_chunks(), client=client)

    assert isinstance(result, WebsiteIntelligence)
    assert len(client.calls) == 2  # one retry happened


def test_retry_prompt_is_stricter_than_first():
    client = FakeLLMClient(["nope", _json(_valid_payload())])
    extractor.extract_structured_intelligence(_default_chunks(), client=client)

    first = client.calls[0]["messages"][0]["content"]
    second = client.calls[1]["messages"][0]["content"]
    assert len(second) > len(first)
    assert "could not be parsed" in second


def test_two_bad_replies_exhaust_retries_and_return_none():
    client = FakeLLMClient(["not json", "still not json"])
    result = extractor.extract_structured_intelligence(_default_chunks(), client=client)

    assert result is None
    assert len(client.calls) == 2  # tried exactly twice, then gave up


def test_schema_invalid_json_is_retried():
    # Valid JSON, but missing the required company_overview/products fields.
    bad = _json({"pricing": {"value": "x", "confidence": "low", "sources": []}})
    client = FakeLLMClient([bad, _json(_valid_payload())])
    result = extractor.extract_structured_intelligence(_default_chunks(), client=client)

    assert isinstance(result, WebsiteIntelligence)
    assert len(client.calls) == 2


def test_network_error_is_caught_and_retried():
    client = FakeLLMClient([RuntimeError("connection reset"), _json(_valid_payload())])
    result = extractor.extract_structured_intelligence(_default_chunks(), client=client)

    assert isinstance(result, WebsiteIntelligence)
    assert len(client.calls) == 2


def test_persistent_network_error_returns_none():
    client = FakeLLMClient([RuntimeError("down"), RuntimeError("still down")])
    result = extractor.extract_structured_intelligence(_default_chunks(), client=client)

    assert result is None


# --- grounding (the core Mission 11 guarantee) ------------------------------


def test_ungrounded_source_on_optional_field_is_dropped_and_field_removed():
    # case_studies cites a URL that was never in the context -> unsupported.
    payload = _valid_payload(case_studies={
        "value": "Customer X cut costs 40%.",
        "confidence": "low",
        "sources": ["https://acme.com/case-studies/x"],  # NOT in context
    })
    client = FakeLLMClient([_json(payload)])
    result = extractor.extract_structured_intelligence(_default_chunks(), client=client)

    assert result.case_studies is None                     # dropped as ungrounded
    assert "case studies" in result.missing_information


def test_grounded_sources_are_kept():
    result = extractor.extract_structured_intelligence(
        _default_chunks(), client=FakeLLMClient([_json(_valid_payload())])
    )
    assert result.pricing is not None
    assert [str(s) for s in result.pricing.sources][0].startswith("https://acme.com/pricing")


def test_ungrounded_required_field_collapses_to_not_available():
    # company_overview cites a URL not in context -> can't be dropped (required),
    # so it must collapse to not_available with no sources.
    payload = _valid_payload()
    payload["company_overview"] = {
        "value": "Totally made up overview.",
        "confidence": "high",
        "sources": ["https://somewhere-else.com"],  # NOT in context
    }
    client = FakeLLMClient([_json(payload)])
    result = extractor.extract_structured_intelligence(_default_chunks(), client=client)

    assert result.company_overview.value == NOT_AVAILABLE
    assert result.company_overview.sources == []
    assert "company overview" in result.missing_information


def test_partially_grounded_sources_keep_only_valid_ones():
    payload = _valid_payload()
    payload["company_overview"]["sources"] = [
        "https://acme.com",              # in context -> keep
        "https://evil.com/injected",     # not in context -> drop
    ]
    client = FakeLLMClient([_json(payload)])
    result = extractor.extract_structured_intelligence(_default_chunks(), client=client)

    kept = [str(s) for s in result.company_overview.sources]
    assert any("acme.com" in s for s in kept)
    assert not any("evil.com" in s for s in kept)


def test_trailing_slash_mismatch_still_grounds():
    # Chunk URL has no trailing slash; pydantic normalizes the cited bare domain
    # WITH one. Normalization in the extractor must treat them as equal.
    chunks = [_chunk("https://acme.com", "homepage", 0, "Acme does things.")]
    payload = {
        "company_overview": {"value": "Acme does things.", "confidence": "high",
                             "sources": ["https://acme.com"]},
        "products_and_services": {"value": "Things.", "confidence": "medium",
                                  "sources": ["https://acme.com"]},
        "legal_pages": {"terms_available": False, "privacy_policy_available": False,
                        "refund_policy_available": False, "cookie_policy_available": False,
                        "sources": []},
        "missing_information": [],
    }
    result = extractor.extract_structured_intelligence(chunks, client=FakeLLMClient([_json(payload)]))
    assert result.company_overview.is_available()
    assert result.company_overview.sources  # not stripped away


# --- edge cases -------------------------------------------------------------


def test_empty_chunks_returns_none_without_calling_model():
    client = FakeLLMClient([_json(_valid_payload())])
    result = extractor.extract_structured_intelligence([], client=client)

    assert result is None
    assert client.calls == []  # model was never called


def test_none_client_returns_none_gracefully(monkeypatch):
    # Simulate "no client could be built" (e.g. missing API key in production).
    monkeypatch.setattr(extractor, "_build_default_client", lambda: None)
    result = extractor.extract_structured_intelligence(_default_chunks())  # no client passed

    assert result is None


def test_bare_string_response_is_supported():
    # A fake that returns a plain string (not a .content object) should work,
    # exercising the string branch of _text_from_response.
    class StringClient(FakeLLMClient):
        class _Messages(FakeLLMClient._Messages):
            def create(self, **kwargs):
                self._outer.calls.append(kwargs)
                return self._outer._replies.pop(0)  # raw string, not _Response

        @property
        def messages(self):
            return StringClient._Messages(self)

    result = extractor.extract_structured_intelligence(
        _default_chunks(), client=StringClient([_json(_valid_payload())])
    )
    assert isinstance(result, WebsiteIntelligence)


# --- chunk selection --------------------------------------------------------


def test_selection_respects_context_char_budget(monkeypatch):
    monkeypatch.setattr(extractor.config, "LLM_MAX_CONTEXT_CHARS", 50)
    big_chunks = [_chunk(f"https://acme.com/p{i}", "general", 0, "x" * 40) for i in range(10)]
    selected = extractor._select_context_chunks(big_chunks, 50)

    # At least one chunk is always taken; the budget stops it well short of all 10.
    assert 1 <= len(selected) < 10


def test_selection_prioritizes_high_value_page_types():
    chunks = [
        _chunk("https://acme.com/blog/post", "blog", 0, "A blog post."),
        _chunk("https://acme.com", "homepage", 0, "The homepage."),
        _chunk("https://acme.com/pricing", "pricing", 0, "Pricing info."),
    ]
    selected = extractor._select_context_chunks(chunks, 10_000)
    ordered_types = [c.page_type for c in selected]
    # homepage (priority 0) must come before blog (priority 16).
    assert ordered_types.index("homepage") < ordered_types.index("blog")


def test_selection_reads_pages_breadth_first():
    # Two pages, two chunks each. Breadth-first => we see chunk 0 of BOTH pages
    # before chunk 1 of either, so both pages are represented under a tight budget.
    chunks = [
        _chunk("https://acme.com", "homepage", 0, "home0"),
        _chunk("https://acme.com", "homepage", 1, "home1"),
        _chunk("https://acme.com/about", "about", 0, "about0"),
        _chunk("https://acme.com/about", "about", 1, "about1"),
    ]
    selected = extractor._select_context_chunks(chunks, 10_000)
    first_two_urls = {c.page_url for c in selected[:2]}
    assert first_two_urls == {"https://acme.com", "https://acme.com/about"}


# --- extracted_data_summary -------------------------------------------------


def test_summary_reports_expected_booleans():
    result = extractor.extract_structured_intelligence(
        _default_chunks(), client=FakeLLMClient([_json(_valid_payload())])
    )
    summary = extractor.extracted_data_summary(result)

    assert summary["hasPricing"] is True         # pricing was grounded
    assert summary["hasBlog"] is False
    assert summary["hasCaseStudies"] is False
    assert set(summary) == {
        "hasPricing", "hasBlog", "hasTerms", "hasPrivacyPolicy", "hasCaseStudies",
    }


def test_summary_of_none_is_all_false():
    summary = extractor.extracted_data_summary(None)
    assert summary == {
        "hasPricing": False,
        "hasBlog": False,
        "hasTerms": False,
        "hasPrivacyPolicy": False,
        "hasCaseStudies": False,
    }


def test_summary_uses_legal_pages_flags_for_terms_and_privacy():
    payload = _valid_payload(legal_pages={
        "terms_available": True,
        "privacy_policy_available": True,
        "refund_policy_available": False,
        "cookie_policy_available": False,
        "sources": ["https://acme.com/pricing"],  # must be in-context to survive grounding
    })
    result = extractor.extract_structured_intelligence(
        _default_chunks(), client=FakeLLMClient([_json(payload)])
    )
    summary = extractor.extracted_data_summary(result)
    assert summary["hasTerms"] is True
    assert summary["hasPrivacyPolicy"] is True


# --- pure-function unit checks ----------------------------------------------


@pytest.mark.parametrize("raw,expected_keys", [
    ('{"a": 1}', {"a"}),
    ('```json\n{"a": 1}\n```', {"a"}),
    ('```\n{"a": 1}\n```', {"a"}),
    ('prefix {"a": 1} suffix', {"a"}),
])
def test_parse_json_variants(raw, expected_keys):
    assert set(extractor._parse_json(raw)) == expected_keys


@pytest.mark.parametrize("raw", ["", None, "not json", "[1, 2, 3]", "42"])
def test_parse_json_rejects_non_objects(raw):
    # arrays and scalars are valid JSON but not the object we require
    assert extractor._parse_json(raw) is None


def test_normalize_url_is_trailing_slash_and_case_insensitive():
    assert extractor._normalize_url("https://Acme.com/") == extractor._normalize_url("https://acme.com")
