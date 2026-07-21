"""api/schemas.py — Mission 13.

Request/response shapes for the API (pydantic). Keeps the HTTP contract separate
from the internal domain models.
"""

from typing import Optional

from pydantic import BaseModel

from agent3.ai.schemas import WebsiteIntelligence
