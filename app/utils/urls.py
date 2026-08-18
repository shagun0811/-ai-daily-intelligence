"""URL canonicalization for Level 2 duplicate detection."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "gclsrc",
    "mc_cid",
    "mc_eid",
    "igshid",
    "si",
    "ref",
    "referrer",
}


def canonicalize_url(url: str | None) -> str:
    """Lowercase host, drop fragment and tracking query params, strip trailing slash."""
    if not url:
        return ""
    raw = url.strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    filtered = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(filtered))
    return urlunsplit((scheme, netloc, path, query, ""))
