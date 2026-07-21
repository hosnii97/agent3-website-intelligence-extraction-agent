"""ai/extractor.py — Mission 11.

"Send the prompt, get JSON back, check it's valid": calls the LLM with the
website-intelligence prompt over retrieved chunks and validates the output
against the WebsiteIntelligence schema.
"""

from agent3.ai.schemas import WebsiteIntelligence, SourcedField
from agent3.ai.prompts.website_intelligence_prompt import WEBSITE_INTELLIGENCE_PROMPT
from agent3.ai.rag.retriever import retrieve
from agent3.extraction.chunker import Chunk
from agent3.common import config
from agent3.common import logging as log
from agent3.common import errors
