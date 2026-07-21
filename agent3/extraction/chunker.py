"""extraction/chunker.py — Mission 10.

"Cut long text into small labeled pieces": splits an ExtractedPage's clean text
into Chunk objects with metadata, ready for embedding/retrieval.
See Agent3_Architecture.md §4 for the Chunk contract.
"""

from dataclasses import dataclass
from typing import Optional

from agent3.classification.page_classifier import PageType
from agent3.extraction.text_extractor import ExtractedPage
from agent3.common import config
