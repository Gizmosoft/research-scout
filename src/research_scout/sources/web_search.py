import logging
from collections.abc import Callable

import httpx
from pydantic import BaseModel

from research_scout.models import arxiv_id_from_text, clean_text, doi_from_text
from research_scout.sources.http import get_json

log = logging.getLogger("research_scout")
_API = "https://api.search.brave.com/res/v1/web/search"


class WebHit(BaseModel):
    title: str
    url: str
    description: str = ""


def looks_like_paper(url: str) -> bool:
    lowered = (url or "").lower()
    return lowered.endswith(".pdf") or bool(doi_from_text(url) or arxiv_id_from_text(url))


class BraveSearch:
    def __init__(
        self,
        client: httpx.Client,
        api_key: str = "",
        on_retry: Callable[[], None] | None = None,
    ):
        self.client = client
        self.api_key = api_key
        self.on_retry = on_retry
        self._warned = False

    def search(self, query: str, count: int) -> list[WebHit]:
        if not self.api_key:
            if not self._warned:
                log.info("web_search skipped reason=missing_api_key")
                self._warned = True
            return []
        payload = get_json(
            self.client,
            _API,
            params={"q": query, "count": min(count, 20)},
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
            on_retry=self.on_retry,
        )
        if not isinstance(payload, dict):
            return []
        hits = []
        for row in (payload.get("web") or {}).get("results") or []:
            url = row.get("url") or ""
            title = clean_text(row.get("title") or "", 300)
            if not url or not title:
                continue
            hits.append(
                WebHit(title=title, url=url, description=clean_text(row.get("description") or "", 400))
            )
        return hits
