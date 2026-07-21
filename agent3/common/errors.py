"""common/errors.py — Mission 15.

Shared error types + the standard error JSON shape. Every error maps to
`retryable: true/false` so Agent 1 knows whether to retry later.
"""

from enum import Enum
