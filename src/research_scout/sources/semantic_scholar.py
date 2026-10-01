import time
from collections.abc import Callable

import httpx

from research_scout.models import Item, clean_text, paper_canonical_id
from research_scout.sources.http import get_json

_API = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "title,authors,venue,abstract,externalIds,url,publicationDate"
_MIN_GAP_SECONDS = 1.1


class SemanticScholar:
    """Public Graph API. No key. Calls are spaced to stay under the shared free limit."""

    def __init__(self, client: httpx.Client, on_retry: Callable[[], None] | None = None):
        self.client = client
        self.on_retry = on_retry
        self._last_call = 0.0

    def search(self, query: str, limit: int) -> list[Item]:
        self._pace()
        payload = get_json(
            self.client,
            _API,
            params={"query": query, "limit": limit, "fields": _FIELDS},
            on_retry=self.on_retry,
        )
        if not isinstance(payload, dict):
            return []
        items = []
        for paper in payload.get("data") or []:
            item = _to_item(paper, query)
            if item:
                items.append(item)
        return items

    def _pace(self) -> None:
        if not self._last_call:
            self._last_call = time.monotonic()
            return
        remaining = _MIN_GAP_SECONDS - (time.monotonic() - self._last_call)
        if remaining > 0:
            time.sleep(remaining)
        self._last_call = time.monotonic()


def _to_item(paper: dict, query: str) -> Item | None:
    title = clean_text(paper.get("title") or "", 300)
    if not title:
        return None
    external = paper.get("externalIds") or {}
    doi = external.get("DOI") or None
    arxiv_id = external.get("ArXiv") or None
    authors = [row.get("name") for row in paper.get("authors") or [] if row.get("name")]
    return Item(
        kind="paper",
        canonical_id=paper_canonical_id(
            doi=doi,
            arxiv_id=arxiv_id,
            title=title,
            url=paper.get("url") or "",
        ),
        title=title,
        authors=", ".join(authors[:12]),
        source="semantic_scholar",
        venue_or_site=clean_text(paper.get("venue") or "", 200),
        published_date=clean_text(paper.get("publicationDate") or "", 40),
        url=paper.get("url") or "",
        excerpt=clean_text(paper.get("abstract") or "", 400),
        query=query,
    )
