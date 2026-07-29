"""crawler/url_normalizer.py — Mission 5.

"Fix messy URLs before we use them": clean and validate the input URL and
extract its domain before anything else in the pipeline runs.

What it handles (Mission 5 acceptance criteria):
  - Validates that the input is a well-formed absolute http(s) URL.
  - Adds https:// when the scheme is missing.
  - Removes unnecessary trailing slashes.
  - Extracts the domain (hostname).
  - Rejects unsupported schemes (ftp:, javascript:, data:, mailto:, ...),
    malformed hosts, and private/loopback targets (SSRF guard).
  - Exposes is_internal_url() so link_discovery never crawls off-site links,
    tolerating the common non-www <-> www redirect.
"""

import ipaddress
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from agent3.common import config

_ALLOWED_SCHEMES = {"http", "https"}

# Schemes we recognize by name so "example.com:8080" (no scheme, just a port)
# isn't mistaken for a scheme -- only prepend https:// when the prefix isn't
# actually a known scheme.
_KNOWN_SCHEMES = {
    "http", "https", "ftp", "ftps", "file", "javascript", "data",
    "mailto", "tel", "ws", "wss", "vbscript", "about", "blob",
}
_SCHEME_PREFIX_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")
_HOSTNAME_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


@dataclass
class NormalizedUrl:
    """Result of validating + cleaning a raw website URL (Mission 5).

    Attributes:
        original_url: Exactly what was passed in, untouched.
        url: The cleaned, absolute http(s) URL. None when is_valid is False.
        domain: The lowercase hostname (e.g. "www.example.com"). None when invalid.
        is_valid: Whether `original_url` passed all validation rules.
        error_reason: Human-readable reason when is_valid is False, else None.
    """

    original_url: str
    url: Optional[str]
    domain: Optional[str]
    is_valid: bool
    error_reason: Optional[str] = None


def normalize_url(raw_url: str) -> NormalizedUrl:
    """Validate and clean a raw website URL. Never raises."""
    if raw_url is None or not str(raw_url).strip():
        return _invalid(raw_url, "URL is empty.")

    candidate = raw_url.strip()

    if len(candidate) > config.MAX_URL_LENGTH:
        return _invalid(raw_url, f"URL exceeds {config.MAX_URL_LENGTH} characters.")

    candidate = _ensure_scheme(candidate)

    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        return _invalid(raw_url, f"URL could not be parsed: {exc}")

    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        return _invalid(raw_url, f"Unsupported URL scheme '{scheme}'. Only http/https are allowed.")

    if "@" in parts.netloc:
        return _invalid(raw_url, "URLs with embedded credentials are not allowed.")

    hostname = parts.hostname
    if not hostname:
        return _invalid(raw_url, "URL is missing a host.")

    try:
        port = parts.port
    except ValueError:
        return _invalid(raw_url, "URL has an invalid port.")

    host_error = _validate_host(hostname)
    if host_error:
        return _invalid(raw_url, host_error)

    domain = hostname.lower()
    normalized = _rebuild(scheme, domain, port, parts.path, parts.query)

    return NormalizedUrl(
        original_url=raw_url,
        url=normalized,
        domain=domain,
        is_valid=True,
        error_reason=None,
    )


def extract_domain(url: str) -> Optional[str]:
    """Return the lowercase hostname for `url`, or None if it doesn't normalize."""
    return normalize_url(url).domain


def is_internal_url(candidate_url: str, base_domain: str) -> bool:
    """True when `candidate_url` belongs to the same site as `base_domain`.

    Tolerates the common non-www <-> www redirect (Mission 6 already follows
    redirects and records the final URL) so a homepage on "example.com" that
    redirects to "www.example.com" doesn't make every discovered link look
    external, while a genuinely different domain is still rejected.
    """
    if not base_domain:
        return False
    candidate_domain = extract_domain(candidate_url)
    if not candidate_domain:
        return False
    return _strip_www(candidate_domain) == _strip_www(base_domain.lower())


def _ensure_scheme(candidate: str) -> str:
    """Prepend https:// when the URL has no (real) scheme."""
    if candidate.startswith("//"):
        return f"https:{candidate}"

    match = _SCHEME_PREFIX_RE.match(candidate)
    if match and match.group(1).lower() in _KNOWN_SCHEMES:
        return candidate

    return f"https://{candidate}"


def _validate_host(hostname: str) -> Optional[str]:
    """Return an error reason if the hostname is malformed or dangerous, else None."""
    hostname = hostname.lower()

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip is not None:
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return f"'{hostname}' is a private/loopback address and cannot be scanned."
        return None

    if hostname == "localhost":
        return "'localhost' cannot be scanned."

    if len(hostname) > 253:
        return "Hostname is too long."

    labels = hostname.split(".")
    if len(labels) < 2:
        return f"'{hostname}' is not a valid domain (missing a top-level domain)."

    if not all(_HOSTNAME_LABEL_RE.match(label) for label in labels):
        return f"'{hostname}' contains invalid characters."

    return None


def _rebuild(scheme: str, domain: str, port: Optional[int], path: str, query: str) -> str:
    """Reassemble the URL: default port stripped, no unnecessary trailing slash, no fragment."""
    is_default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = domain if port is None or is_default_port else f"{domain}:{port}"

    path = path or ""
    if path == "/":
        path = ""
    elif len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, query, ""))


def _strip_www(hostname: str) -> str:
    return hostname[4:] if hostname.startswith("www.") else hostname


def _invalid(raw_url: str, reason: str) -> NormalizedUrl:
    return NormalizedUrl(original_url=raw_url, url=None, domain=None, is_valid=False, error_reason=reason)
