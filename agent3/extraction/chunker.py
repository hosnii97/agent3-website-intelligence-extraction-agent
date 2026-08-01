"""extraction/chunker.py — Mission 10.

"Cut long text into small labeled pieces": splits an ExtractedPage's clean text
into Chunk objects with metadata, ready for embedding/retrieval.
See Agent3_Architecture.md §4 for the Chunk contract.
"""

import re
from dataclasses import dataclass
from typing import Optional

from agent3.common import config
from agent3.common import logging as log


@dataclass
class Chunk:
    """One labeled slice of a page's clean text, ready for embedding/retrieval.

    A Chunk is the unit Mission 11 (AI extraction) and the RAG layer operate on:
    a small piece of text plus enough metadata to trace it back to its source
    page and the company it belongs to. See Agent3_Architecture.md §4.

    Attributes:
        company_id: The company this chunk's page belongs to (scopes retrieval).
        page_url: The URL of the source page this text came from.
        page_type: The classified type of the source page (e.g. "pricing").
        chunk_index: Position of this chunk within its page, starting at 0.
        title: The source page's title, if it had one.
        text: The chunk's actual text content.
    """

    company_id: str
    page_url: str
    page_type: str
    chunk_index: int
    title: Optional[str]
    text: str


# A "token" here is a whitespace-delimited word. This is a deliberately simple
# proxy for real LLM tokens — good enough for sizing chunks without pulling in a
# tokenizer dependency, and keeps the module testable in isolation.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    """Break a block of text into sentence-ish units.

    Splits on sentence-ending punctuation followed by whitespace. Falls back to
    treating the whole block as one unit when no boundary is found, so no text is
    ever dropped.
    """
    parts = _SENTENCE_END.split(text.strip())
    return [part for part in parts if part]


def _segment(text: str) -> list[str]:
    """Split text into the smallest natural units we're willing to keep whole.

    Prefers paragraph boundaries (blank lines), then sentence boundaries within
    each paragraph. Each returned segment is treated as atomic — `split_text`
    packs segments into chunks but never cuts one in half.
    """
    segments: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        segments.extend(_split_sentences(paragraph))
    return segments


def _word_count(text: str) -> int:
    """Count whitespace-delimited words (our stand-in for tokens)."""
    return len(text.split())


def split_text(
    text: str,
    chunk_size: int = config.CHUNK_SIZE_TOKENS,
    overlap: int = config.CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    """Split `text` into overlapping chunks of roughly `chunk_size` words.

    Chunks are built by packing whole sentences/paragraphs together until adding
    the next segment would exceed `chunk_size` words. Consecutive chunks share
    about `overlap` words (whole sentences carried over from the tail of the
    previous chunk), so context isn't lost at chunk boundaries. Sentences are
    never split mid-way unless a single sentence alone already exceeds
    `chunk_size`, in which case it's hard-wrapped on word boundaries as a last
    resort.

    Args:
        text: The clean text to split. May be empty.
        chunk_size: Target maximum words per chunk.
        overlap: Approximate number of words repeated between adjacent chunks.

    Returns:
        A list of chunk strings in document order. Empty text yields an empty
        list; text shorter than `chunk_size` yields exactly one chunk.
    """
    if text is None or not text.strip():
        return []
    chunk_size = max(1, chunk_size)   # never let a misconfig zero/negative size crash
    overlap = max(0, overlap)
    if overlap >= chunk_size:  # guard against a degenerate/never-advancing window
        overlap = chunk_size // 4

    segments = _segment(text)

    # Hard-wrap any single segment that's larger than a whole chunk, so the
    # packing loop below can always fit at least one segment per chunk.
    normalized: list[str] = []
    for segment in segments:
        if _word_count(segment) <= chunk_size:
            normalized.append(segment)
            continue
        words = segment.split()
        for start in range(0, len(words), chunk_size):
            normalized.append(" ".join(words[start:start + chunk_size]))

    chunks: list[str] = []
    current: list[str] = []      # segments in the chunk being built
    current_words = 0
    for segment in normalized:
        seg_words = _word_count(segment)
        if current and current_words + seg_words > chunk_size:
            chunks.append(" ".join(current))
            # Carry the tail segments (~`overlap` words) into the next chunk.
            current, current_words = _overlap_tail(current, overlap)
        current.append(segment)
        current_words += seg_words

    if current:
        chunks.append(" ".join(current))
    return chunks


def _overlap_tail(segments: list[str], overlap: int) -> tuple[list[str], int]:
    """Return the trailing segments of a chunk totaling ~`overlap` words.

    Used to seed the next chunk so adjacent chunks share context. Whole segments
    are kept intact; we walk backwards until we've collected at least `overlap`
    words (or run out of segments).
    """
    if overlap <= 0:
        return [], 0
    tail: list[str] = []
    words = 0
    for segment in reversed(segments):
        tail.insert(0, segment)
        words += _word_count(segment)
        if words >= overlap:
            break
    return tail, words


def _page_type_str(page_type) -> str:
    """Normalize a page_type to a plain string.

    Accepts either a raw string or a PageType enum member (which is a str-Enum,
    so `.value` gives the clean "pricing" form rather than "PageType.PRICING").
    """
    return getattr(page_type, "value", page_type)


def chunk_page(page, company_id: Optional[str] = None) -> list[Chunk]:
    """Split one page's clean text into an ordered list of Chunk objects.

    Args:
        page: The source page. Must expose `page_url`/`url`, `page_type`,
            `title`, and `clean_text`; may also expose `company_id`.
        company_id: The owning company. Takes precedence over `page.company_id`
            when given (the batch caller supplies it explicitly); falls back to
            `page.company_id` when omitted.

    Returns:
        Chunks in document order with `chunk_index` starting at 0. An empty list
        (never an error) when the page has no usable text.
    """
    resolved_company_id = company_id or getattr(page, "company_id", None)
    page_url = getattr(page, "page_url", None) or getattr(page, "url", None)
    clean_text = getattr(page, "clean_text", None)

    pieces = split_text(clean_text) if clean_text else []
    if not pieces:
        log.warning("chunk_page_empty", company_id=resolved_company_id, url=page_url)
        return []

    page_type = _page_type_str(getattr(page, "page_type", None))
    title = getattr(page, "title", None)

    return [
        Chunk(
            company_id=resolved_company_id,
            page_url=page_url,
            page_type=page_type,
            chunk_index=index,
            title=title,
            text=piece,
        )
        for index, piece in enumerate(pieces)
    ]


def chunk_pages(pages: list, company_id: str) -> list[Chunk]:
    """Chunk every page in a scan into one combined, flat list of Chunks.

    Runs `chunk_page()` over each page and concatenates the results. `chunk_index`
    is per-page (it restarts at 0 for each page); the source `page_url` on each
    Chunk is what disambiguates chunks across pages.

    Args:
        pages: The extracted pages from a single scan.
        company_id: The owning company, applied to every produced Chunk.

    Returns:
        All chunks across all pages, in page order then chunk order. Pages with
        no usable text contribute nothing (they're logged and skipped).
    """
    chunks: list[Chunk] = []
    for page in pages:
        chunks.extend(chunk_page(page, company_id=company_id))

    log.info(
        "chunk_pages_done",
        company_id=company_id,
        pages=len(pages),
        chunks=len(chunks),
    )
    return chunks
