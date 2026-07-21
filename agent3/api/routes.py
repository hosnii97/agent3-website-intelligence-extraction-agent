"""api/routes.py — Mission 13.

Defines the 3 endpoints (scan-website, scan status, get website-intelligence).
Thin layer: validate input, call the orchestrator, shape the response.
"""

from agent3.api import schemas
from agent3.orchestrator.scan_pipeline import run_website_scan
from agent3.storage.repository import get_scan, get_website_intelligence
from agent3.common import logging as log
from agent3.common import errors
