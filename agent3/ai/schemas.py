"""ai/schemas.py — Mission 11.

The exact JSON shape the AI must return, as pydantic models: SourcedField and
WebsiteIntelligence. `extractor.py` validates the LLM output against these.
See Agent3_Architecture.md §4.
"""

from typing import Literal, Optional

from pydantic import BaseModel, HttpUrl
