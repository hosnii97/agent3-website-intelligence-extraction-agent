"""crawler/fetcher.py — Mission 6.

"Download a page without crashing, ever": safely fetches the homepage or any
internal page and returns a typed FetchResult (never raises for a bad page).
"""

from agent3.crawler.models import FetchResult, FetchStatus
from agent3.common import config
from agent3.common import logging as log
from agent3.common import errors
