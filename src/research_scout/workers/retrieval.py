import logging
from typing import Literal
from urllib.parse import urlsplit

import httpx

from research_scout.config import CANDIDATE_MULTIPLIER, TIMEOUT_SECONDS, Settings
from research_scout.models import (
    Item,
    arxiv_id_from_text,
    canonical_url,
    doi_from_text,
    paper_canonical_id,
)
from research_scout.sources.arxiv import Arxiv
from research_scout.sources.extract import fetch_excerpt, public_http_url
from research_scout.sources.openalex import OpenAlex
from research_scout.sources.semantic_scholar import SemanticScholar
from research_scout.sources.web_search import BraveSearch, looks_like_paper
from research_scout.telemetry.metrics import RunMetrics

log = logging.getLogger("research_scout")


class RetrievalWorker:
    def __init__(self, settings: Settings, metrics: RunMetrics):
        self.settings = settings
        self.metrics = metrics
        self.client = httpx.Client(
            timeout=TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        )
        retry = metrics.add_retry
        self.openalex = OpenAlex(self.client, settings.openalex_mailto, on_retry=retry)
        self.arxiv = Arxiv(self.client, on_retry=retry)
        self.semantic_scholar = SemanticScholar(self.client, on_retry=retry)
        self.web = BraveSearch(self.client, settings.brave_search_api_key, on_retry=retry)

    def close(self) -> None:
        self.client.close()

    def collect(
        self,
        paper_queries: list[str],
        blog_queries: list[str],
        relation: Literal["direct", "adjacent"],
    ) -> list[Item]:
        papers = self._papers(paper_queries, relation)
        blogs = self._blogs(blog_queries) if relation == "direct" and self.settings.blog_target else []
        unique = _unique(papers + blogs)
        log.info("retrieve relation=%s count=%s", relation, len(unique))
        return unique

    def _papers(self, queries: list[str], relation: Literal["direct", "adjacent"]) -> list[Item]:
        per_query = _per_query(self.settings.paper_target, len(queries), sources=3)
        items: list[Item] = []
        for query in queries:
            openalex_hits = self.openalex.search(query, per_query)
            arxiv_hits = self.arxiv.search(query, per_query)
            scholar_hits = self.semantic_scholar.search(query, per_query)
            index_hits = openalex_hits + arxiv_hits + scholar_hits
            self.metrics.retrieval_index += len(index_hits)
            for item in index_hits:
                item.query = query
                item.relation = relation
            items.extend(index_hits)
            web_hits = self.web.search(query, per_query)
            self.metrics.retrieval_web += len(web_hits)
            web_papers = self._web_papers(web_hits, query, relation)
            items.extend(web_papers)
            log.info(
                "worker=retrieval relation=%s query=%s openalex=%s arxiv=%s semantic_scholar=%s web_hits=%s web_papers=%s",
                relation,
                query,
                len(openalex_hits),
                len(arxiv_hits),
                len(scholar_hits),
                len(web_hits),
                len(web_papers),
            )
        return items

    def _web_papers(self, hits, query: str, relation: Literal["direct", "adjacent"]) -> list[Item]:
        items: list[Item] = []
        enriched = 0
        cap = self.settings.paper_target * 2
        for hit in hits:
            if not looks_like_paper(hit.url):
                continue
            doi = doi_from_text(hit.url)
            arxiv_id = arxiv_id_from_text(hit.url)
            item = None
            if enriched < cap and (doi or arxiv_id):
                item = self.openalex.lookup(doi=doi, arxiv_id=arxiv_id, query=query)
                enriched += 1
            if item is None:
                item = Item(
                    kind="paper",
                    canonical_id=paper_canonical_id(
                        doi=doi, arxiv_id=arxiv_id, title=hit.title, url=hit.url
                    ),
                    title=hit.title,
                    source="web",
                    url=hit.url,
                    excerpt=hit.description,
                    query=query,
                )
            item.query = query
            item.relation = relation
            items.append(item)
        return items

    def _blogs(self, queries: list[str]) -> list[Item]:
        if not queries:
            return []
        per_query = _per_query(self.settings.blog_target, len(queries), sources=1)
        limit = max(self.settings.blog_target * CANDIDATE_MULTIPLIER, 1)
        items: list[Item] = []
        for query in queries:
            hits = self.web.search(query, per_query)
            self.metrics.retrieval_web += len(hits)
            before = len(items)
            for hit in hits:
                if len(items) >= limit or looks_like_paper(hit.url) or not public_http_url(hit.url):
                    continue
                extracted = fetch_excerpt(self.client, hit.url) or {}
                title = extracted.get("title") or hit.title
                items.append(
                    Item(
                        kind="blog",
                        canonical_id="url:" + canonical_url(hit.url),
                        title=title,
                        authors=extracted.get("authors", ""),
                        source=urlsplit(hit.url).netloc,
                        published_date=extracted.get("published_date", ""),
                        url=hit.url,
                        excerpt=extracted.get("excerpt") or hit.description,
                        query=query,
                    )
                )
            log.info(
                "worker=retrieval relation=direct query=%s web_hits=%s blogs=%s",
                query,
                len(hits),
                len(items) - before,
            )
        return items


def _per_query(target: int, query_count: int, sources: int) -> int:
    queries = max(query_count, 1)
    return max(3, (target * CANDIDATE_MULTIPLIER) // queries // sources)


def _unique(items: list[Item]) -> list[Item]:
    seen: set[str] = set()
    unique: list[Item] = []
    for item in items:
        if item.canonical_id in seen:
            continue
        seen.add(item.canonical_id)
        unique.append(item)
    return unique
