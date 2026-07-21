"""ai/rag/vector_store.py — RAG add-on.

"Where the vectors live, and how we search them": stores (vector, chunk_id,
company_id, page_type) and answers similarity queries (FAISS / pgvector / Chroma).
"""

from agent3.extraction.chunker import Chunk
from agent3.common import config
