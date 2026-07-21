"""mcp_server/agent3_server.py — MCP add-on.

Wraps the same three Mission 13 endpoints as MCP tools so any MCP-compatible
agent can call them: scan_website, get_scan_status, get_website_intelligence.
"""

from agent3.orchestrator.scan_pipeline import run_website_scan
from agent3.storage.repository import get_scan, get_website_intelligence
from agent3.ai.schemas import WebsiteIntelligence
from agent3.common import config
from agent3.common import logging as log
