"""ai/rag/retriever.py — RAG add-on.

"Given a topic, fetch the most relevant chunks": embeds a query and returns the
top-k most similar chunks, scoped to a single company_id.
"""

from agent3.ai.rag.embedder import embed
from agent3.ai.rag.vector_store import VectorStore
from agent3.extraction.chunker import Chunk
