"""Mission 10 — unit tests for extraction/chunker.py.

Curated to the 10 primary behaviors the chunker must guarantee:
splitting, overlap, the three chunk-count cases (one / many / exactly three),
sequential indexing, metadata population + preservation, and batching.
"""

from dataclasses import dataclass
from typing import Optional

from agent3.extraction import chunker
from agent3.extraction.chunker import Chunk


@dataclass
class FakePage:
    """Minimal stand-in for an ExtractedPage (Missions 6-9 not required here)."""

    company_id: str
    page_url: str
    page_type: str
    title: Optional[str]
    clean_text: str


def _make_text(num_sentences: int) -> str:
    """Build predictable multi-sentence text: 'word0 word1 ... . ' repeated."""
    sentences = []
    counter = 0
    for _ in range(num_sentences):
        words = [f"w{counter + i}" for i in range(10)]
        counter += 10
        sentences.append(" ".join(words) + ".")
    return " ".join(sentences)


def _page(text: str, **overrides) -> FakePage:
    defaults = dict(
        company_id="company_123",
        page_url="https://www.example.com/pricing",
        page_type="pricing",
        title="Pricing",
        clean_text=text,
    )
    defaults.update(overrides)
    return FakePage(**defaults)


# --- split_text ------------------------------------------------------------

def test_split_text_overlap_present_and_roughly_sized():
    text = _make_text(num_sentences=300)
    chunk_size, overlap = 600, 80
    result = chunker.split_text(text, chunk_size=chunk_size, overlap=overlap)
    assert len(result) >= 2
    # tail of chunk N should reappear at the head of chunk N+1
    for first, second in zip(result, result[1:]):
        first_tail = first.split()[-(overlap * 2):]
        second_head = second.split()[: overlap * 2]
        shared = set(first_tail) & set(second_head)
        assert shared, "expected overlapping words between consecutive chunks"
        assert len(shared) <= overlap * 2


def test_split_text_large_text_produces_three_chunks():
    # 150 sentences x 10 words = 1500 words. With chunk_size=600 / overlap=80
    # this packs into exactly 3 overlapping chunks.
    text = _make_text(num_sentences=150)
    chunks = chunker.split_text(text, chunk_size=600, overlap=80)
    assert len(chunks) == 3


# --- chunk_page ------------------------------------------------------------

def test_chunk_page_empty_text_returns_zero_chunks():
    assert chunker.chunk_page(_page(""), "company_123") == []
    assert chunker.chunk_page(_page("   "), "company_123") == []


def test_chunk_page_short_text_returns_exactly_one_chunk():
    page = _page("Just a little bit of text here.")
    chunks = chunker.chunk_page(page, "company_123")
    assert len(chunks) == 1
    assert isinstance(chunks[0], Chunk)


def test_chunk_page_long_text_returns_multiple_chunks():
    page = _page(_make_text(num_sentences=300))
    chunks = chunker.chunk_page(page, "company_123")
    assert len(chunks) > 1


def test_chunk_page_large_text_produces_three_chunks():
    # ~1500 words at the default chunk_size=600 / overlap=80 -> exactly 3 chunks.
    page = _page(_make_text(num_sentences=150))
    chunks = chunker.chunk_page(page, "company_123")
    for c in chunks:
     
    
    assert len(chunks) == 3
    assert [c.chunk_index for c in chunks] == [0, 1, 2]  # sequential from 0


def test_chunk_page_index_sequential_from_zero():
    page = _page(_make_text(num_sentences=300))
    chunks = chunker.chunk_page(page, "company_123")
    indexes = [c.chunk_index for c in chunks]
    assert indexes == list(range(len(chunks)))
    assert indexes[0] == 0


def test_chunk_page_all_metadata_fields_populated():
    page = _page(_make_text(num_sentences=300))
    chunks = chunker.chunk_page(page, "company_123")
    assert chunks
    for c in chunks:
        assert c.company_id == "company_123"
        assert c.page_url == "https://www.example.com/pricing"
        assert c.page_type == "pricing"
        assert c.title == "Pricing"
        assert isinstance(c.chunk_index, int)
        assert c.text and c.text.strip()


def test_chunk_page_preserves_source_metadata_across_pages():
    page = _page(_make_text(num_sentences=50), page_url="https://x.io/about",
                 page_type="about", title="About Us")
    chunks = chunker.chunk_page(page, "company_999")
    for c in chunks:
        assert c.company_id == "company_999"
        assert c.page_url == "https://x.io/about"
        assert c.page_type == "about"
        assert c.title == "About Us"


# --- chunk_pages -----------------------------------------------------------

def test_chunk_pages_returns_flat_combined_list():
    pages = [
        _page(_make_text(num_sentences=100), page_url="https://x.io/a"),
        _page(_make_text(num_sentences=100), page_url="https://x.io/b"),
    ]
    chunks = chunker.chunk_pages(pages, "company_123")
    assert all(isinstance(c, Chunk) for c in chunks)
    urls = {c.page_url for c in chunks}
    assert urls == {"https://x.io/a", "https://x.io/b"}


def test_chunk_pages_skips_empty_pages_without_crashing():
    pages = [
        _page(""),                                   # empty -> contributes nothing
        _page("A little text that fits in one chunk."),
    ]
    chunks = chunker.chunk_pages(pages, "company_123")
    assert len(chunks) == 1
