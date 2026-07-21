"""ai/tools/tool_handlers.py — MCP add-on.

The real functions the tools run under the hood — they reuse the same retriever
and page lookups the fixed pipeline uses.
"""

from agent3.ai.tools import tool_definitions
from agent3.ai.rag.retriever import retrieve
from agent3.extraction.text_extractor import ExtractedPage
from agent3.extraction.chunker import Chunk
