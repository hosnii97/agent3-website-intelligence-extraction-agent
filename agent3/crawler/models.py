"""crawler/models.py — Shared data contracts for the crawl layer.

Defines FetchStatus + FetchResult, the typed objects `fetcher.py` produces and
everyone downstream (link_discovery, text_extractor, orchestrator) consumes.
See Agent3_Architecture.md §4.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
