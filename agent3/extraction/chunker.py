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


@dataclass
class Chunk:
    """One retrievable slice of a page's clean text.

    See Agent3_Architecture.md §4 for the shared contract. `chunk_pages()`
    (Mission 10) still needs to be implemented — this dataclass is added
    ahead of that so downstream consumers (storage, RAG) have a type to
    depend on.
    """

    company_id: str
    page_url: str
    page_type: PageType
    chunk_index: int
    title: Optional[str]
    text: str
