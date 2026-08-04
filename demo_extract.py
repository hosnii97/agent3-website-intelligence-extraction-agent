"""demo_extract.py — a tiny live demo of Mission 11 (AI structured extraction).

Runs the real extractor against a real LLM (OpenAI) using a handful of sample
page chunks, and prints the grounded WebsiteIntelligence it returns. This is
the "prove it works end to end" script for a demo — it exercises the exact code
path the orchestrator uses in production (`extract_structured_intelligence`).

How to run:
    1. Put your key in .env at the repo root:   OPENAI_API_KEY=sk-...
       (.env is gitignored, so the key never gets committed.)
    2. From the repo root:
           python demo_extract.py
       or with the project venv:
           .venv/bin/python demo_extract.py

No key? The unit tests (tests/unit/test_ai_extractor.py) demonstrate the same
logic fully offline with a fake model — this script is only for a live call.
"""

import json
import os
import sys

# Load OPENAI_API_KEY (and any AGENT3_* overrides) from .env if present, so you
# don't have to `export` anything by hand. Falls back silently if python-dotenv
# isn't installed or there's no .env — the SDK can still read a real env var.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from agent3.extraction.chunker import Chunk
from agent3.ai import extractor
from agent3.common import config


# A few sample chunks, as Mission 10's chunker would produce them. In a real
# scan these come from actually crawling + extracting the site; here they're
# hand-written so the demo is self-contained and repeatable.
SAMPLE_CHUNKS = [
    Chunk(
        company_id="company_123",
        page_url="https://www.example.com",
        page_type="homepage",
        chunk_index=0,
        title="Example — Workflow automation for sales teams",
        text=(
            "Example Company provides workflow automation tools that help sales "
            "teams close deals faster. Book a demo to see it in action."
        ),
    ),
    Chunk(
        company_id="company_123",
        page_url="https://www.example.com/pricing",
        page_type="pricing",
        chunk_index=0,
        title="Pricing",
        text=(
            "Example offers three subscription plans: Starter at $29/user/month, "
            "Pro at $59/user/month, and a custom-priced Enterprise plan."
        ),
    ),
    Chunk(
        company_id="company_123",
        page_url="https://www.example.com/about",
        page_type="about",
        chunk_index=0,
        title="About Us",
        text=(
            "Founded in 2018, Example Company serves mid-market B2B sales "
            "organizations across North America and Europe."
        ),
    ),
    Chunk(
        company_id="company_123",
        page_url="https://www.example.com/privacy",
        page_type="privacy_policy",
        chunk_index=0,
        title="Privacy Policy",
        text=(
            "This Privacy Policy explains how Example Company collects, uses, and "
            "protects your personal data in accordance with GDPR."
        ),
    ),
]


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "ERROR: OPENAI_API_KEY is not set.\n"
            "Put it in a .env file at the repo root (OPENAI_API_KEY=sk-...) "
            "or export it in your shell, then re-run.",
            file=sys.stderr,
        )
        return 1

    print(f"Model: {config.LLM_MODEL}  (temperature={config.LLM_TEMPERATURE})")
    print(f"Sending {len(SAMPLE_CHUNKS)} sample chunks to the model...\n")

    # This is the exact call the orchestrator makes (Mission 11 step).
    # client=None -> the extractor builds a real OpenAI client from the env key.
    intelligence = extractor.extract_structured_intelligence(SAMPLE_CHUNKS)

    if intelligence is None:
        print("Extraction returned None (see the logged reason above).")
        return 2

    print("\n=== WebsiteIntelligence (grounded, validated) ===")
    print(json.dumps(intelligence.model_dump(mode="json"), indent=2))

    print("\n=== extractedDataSummary (the cheap boolean view for Agent 1) ===")
    print(json.dumps(extractor.extracted_data_summary(intelligence), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
