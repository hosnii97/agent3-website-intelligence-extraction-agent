"""crawler/link_discovery.py — Mission 7.

"Find the pages worth reading on this site": from the fetched homepage, find
and filter internal links that are worth scanning.
"""

from agent3.crawler.models import FetchResult
from agent3.common import config
from agent3.common import logging as log
