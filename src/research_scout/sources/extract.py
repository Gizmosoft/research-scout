import json
import logging
from urllib.parse import urlsplit

import httpx
import trafilatura

from research_scout.config import FETCH_BYTE_CAP
from research_scout.models import clean_text

log = logging.getLogger("research_scout")


def public_http_url(url: str) -> bool:
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not host:
        return False
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return False
    return True


def fetch_excerpt(client: httpx.Client, url: str) -> dict[str, str] | None:
    if not public_http_url(url):
        return None
    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if content_type and "html" not in content_type and "text" not in content_type:
                return None
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                chunks.append(chunk)
                total += len(chunk)
                if total >= FETCH_BYTE_CAP:
                    break
    except httpx.HTTPError:
        log.info("extract failed host=%s", urlsplit(url).netloc)
        return None
    html = b"".join(chunks).decode("utf-8", errors="ignore")
    return excerpt_from_html(html)


def excerpt_from_html(html: str) -> dict[str, str] | None:
    raw = trafilatura.extract(
        html,
        output_format="json",
        with_metadata=True,
        include_comments=False,
    )
    if not raw:
        return None
    data = json.loads(raw)
    title = clean_text(data.get("title") or "", 300)
    excerpt = clean_text(data.get("text") or "", 400)
    if not title and not excerpt:
        return None
    return {
        "title": title,
        "authors": clean_text(data.get("author") or "", 300),
        "published_date": clean_text(data.get("date") or "", 40),
        "excerpt": excerpt,
    }
