"""classification/page_classifier.py — Mission 8.

"Guess what kind of page this is": defines the PageType enum and decides the
page_type for each URL (homepage, pricing, blog, legal, ...).
See Agent3_Architecture.md §4 for the PageType contract.
"""

from enum import Enum

from agent3.common import config
from agent3.common import logging as log
