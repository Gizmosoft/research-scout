from collections.abc import Callable
from urllib.parse import quote

import httpx

from research_scout.models import Item, clean_text, paper_canonical_id
from research_scout.sources.http import get_json

_API = "https://api.openalex.org/works"


class OpenAlex:
    def __init__(
        self,
        client: httpx.Client,
        mailto: str = "",
        on_retry: Callable[[], None] | None = None,
    ):
        self.client = client
        self.mailto = mailto
        self.on_retry = on_retry

    def search(self, query: str, limit: int) -> list[Item]:
        params: dict[str, str | int] = {"search": query, "per-page": limit}
        if self.mailto:
            params["mailto"] = self.mailto
        payload = get_json(self.client, _API, params=params, on_retry=self.on_retry)
        if not isinstance(payload, dict):
            return []
        items = []
        for work in payload.get("results") or []:
            item = work_to_item(work, query)
            if item:
                items.append(item)
        return items

    def lookup(self, *, doi: str | None, arxiv_id: str | None, query: str) -> Item | None:
        if doi:
            work_id = quote(f"https://doi.org/{doi}", safe="")
        elif arxiv_id:
            work_id = quote(f"arxiv:{arxiv_id}", safe="")
        else:
            return None
        params = {"mailto": self.mailto} if self.mailto else None
        payload = get_json(self.client, f"{_API}/{work_id}", params=params, on_retry=self.on_retry)
        if not isinstance(payload, dict):
            return None
        return work_to_item(payload, query)


def work_to_item(work: dict, query: str) -> Item | None:
    title = clean_text(work.get("display_name") or "", 300)
    if not title:
        return None
    doi = work.get("doi") or ""
    location = work.get("primary_location") or {}
    source = (location.get("source") or {}).get("display_name") or ""
    url = location.get("landing_page_url") or doi or work.get("id") or ""
    return Item(
        kind="paper",
        canonical_id=paper_canonical_id(doi=doi or None, title=title, url=url),
        title=title,
        authors=_authors(work),
        source="openalex",
        venue_or_site=clean_text(source, 200),
        published_date=clean_text(work.get("publication_date") or "", 40),
        url=url,
        excerpt=_abstract(work),
        query=query,
    )


def _authors(work: dict) -> str:
    names = []
    for row in work.get("authorships") or []:
        name = (row.get("author") or {}).get("display_name")
        if name:
            names.append(name)
    return ", ".join(names[:12])


def _abstract(work: dict) -> str:
    inverted = work.get("abstract_inverted_index") or {}
    pairs: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        for pos in positions:
            if isinstance(pos, int) and pos < 80:
                pairs.append((pos, word))
    pairs.sort()
    return clean_text(" ".join(word for _, word in pairs), 400)
