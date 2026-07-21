"""extraction/text_extractor.py — Mission 9.

"Strip the HTML junk, keep the real text": turns a fetched page into an
ExtractedPage (clean_text + title + headings + metadata).
See Agent3_Architecture.md §4 for the ExtractedPage contract.
"""

from dataclasses import dataclass
from typing import Optional

from agent3.crawler.models import FetchResult, FetchStatus
from agent3.classification.page_classifier import PageType
from agent3.common import config
from agent3.common import logging as log
