import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable

import httpx

from research_scout.models import Item, arxiv_id_from_text, clean_text, paper_canonical_id
from research_scout.sources.http import get_text

log = logging.getLogger("research_scout")
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"
_API = "https://export.arxiv.org/api/query"


class Arxiv:
    def __init__(self, client: httpx.Client, on_retry: Callable[[], None] | None = None):
        self.client = client
        self.on_retry = on_retry

    def search(self, query: str, limit: int) -> list[Item]:
        text = get_text(
            self.client,
            _API,
            params={"search_query": f"all:{query}", "start": 0, "max_results": limit},
            on_retry=self.on_retry,
        )
        if not text:
            return []
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            log.info("arxiv bad_xml")
            return []
        items = []
        for entry in root.findall(f"{_ATOM}entry"):
            item = _entry_to_item(entry, query)
            if item:
                items.append(item)
        return items


def _entry_to_item(entry: ET.Element, query: str) -> Item | None:
    title = clean_text(_text(entry, "title"), 300)
    if not title:
        return None
    raw_id = _text(entry, "id")
    arxiv_id = arxiv_id_from_text(raw_id)
    doi = _text(entry, "doi", namespace=_ARXIV_NS) or None
    authors = [
        clean_text(node.text or "", 120)
        for node in entry.findall(f"{_ATOM}author/{_ATOM}name")
        if node.text
    ]
    pdf = raw_id
    for link in entry.findall(f"{_ATOM}link"):
        if link.attrib.get("title") == "pdf" and link.attrib.get("href"):
            pdf = link.attrib["href"]
    return Item(
        kind="paper",
        canonical_id=paper_canonical_id(doi=doi, arxiv_id=arxiv_id, title=title, url=pdf),
        title=title,
        authors=", ".join(authors[:12]),
        source="arxiv",
        venue_or_site="arXiv",
        published_date=clean_text(_text(entry, "published"), 40)[:10],
        url=pdf or raw_id,
        excerpt=clean_text(_text(entry, "summary"), 400),
        query=query,
    )


def _text(entry: ET.Element, tag: str, namespace: str = _ATOM) -> str:
    node = entry.find(f"{namespace}{tag}")
    return node.text or "" if node is not None and node.text else ""
