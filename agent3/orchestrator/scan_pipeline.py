"""orchestrator/scan_pipeline.py — the pipeline owner.

"The recipe that runs every step in order." Runs all missions 5-12: normalize
URL, fetch homepage, discover links, fetch/classify/extract each page, chunk,
run AI extraction, and persist. Catches per-page errors so one bad page never
kills the whole scan. Read this file first if you're new (see §5).
"""

from agent3.crawler.url_normalizer import normalize_url
from agent3.crawler.fetcher import fetch_homepage, fetch_page
from agent3.crawler.link_discovery import discover_links
from agent3.crawler.models import FetchResult, FetchStatus
from agent3.classification.page_classifier import classify_page
from agent3.extraction.text_extractor import extract_text, ExtractedPage
from agent3.extraction.chunker import chunk_pages, Chunk
from agent3.ai.extractor import extract_structured_intelligence
from agent3.storage.repository import save_scan_results
from agent3.common import config
from agent3.common import logging as log
from agent3.common import errors
