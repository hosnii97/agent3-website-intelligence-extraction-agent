"""Agent 3 — Website Intelligence Extraction Agent.

Top-level package. Given a companyId + websiteUrl, safely scan the company's
website, extract clean text, classify pages, run AI structured extraction with
source grounding, and store the result for Agent 1 (and future consumers).

Read `orchestrator/scan_pipeline.py` first if you're new — it runs every step
in order.
"""
