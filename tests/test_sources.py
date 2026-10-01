import httpx

from research_scout.models import doi_from_text
from research_scout.sources.arxiv import Arxiv
from research_scout.sources.extract import excerpt_from_html, public_http_url
from research_scout.sources.http import get_json
from research_scout.sources.openalex import OpenAlex
from research_scout.sources.semantic_scholar import SemanticScholar
from research_scout.sources.web_search import BraveSearch, looks_like_paper

_WORK = {
    "display_name": "Attention Is All You Need",
    "doi": "https://doi.org/10.1000/test.1",
    "publication_date": "2017-06-12",
    "authorships": [{"author": {"display_name": "Ashish Vaswani"}}],
    "primary_location": {
        "landing_page_url": "https://example.com/paper",
        "source": {"display_name": "NeurIPS"},
    },
    "abstract_inverted_index": {"Attention": [0], "matters": [1]},
}

_ARXIV = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>A Sample Paper</title>
    <summary>Short abstract here.</summary>
    <published>2024-01-02T00:00:00Z</published>
    <author><name>Ada Lovelace</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/2401.00001v1"/>
    <arxiv:doi>10.1000/arxiv.1</arxiv:doi>
  </entry>
</feed>
"""


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openalex_search_parses_work():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["search"] == "transformers"
        return httpx.Response(200, json={"results": [_WORK]})

    items = OpenAlex(_client(handler), mailto="a@b.c").search("transformers", 5)
    assert items[0].canonical_id == "doi:10.1000/test.1"
    assert items[0].authors == "Ashish Vaswani"
    assert items[0].venue_or_site == "NeurIPS"
    assert items[0].excerpt == "Attention matters"
    assert items[0].source == "openalex"


def test_arxiv_parses_atom():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_ARXIV)

    items = Arxiv(_client(handler)).search("sample", 5)
    assert items[0].title == "A Sample Paper"
    assert items[0].authors == "Ada Lovelace"
    assert items[0].canonical_id == "doi:10.1000/arxiv.1"
    assert items[0].published_date == "2024-01-02"
    assert items[0].source == "arxiv"


def test_semantic_scholar_parses_without_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "x-api-key" not in request.headers
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "title": "Scout Paper",
                        "abstract": "About agents.",
                        "venue": "ACL",
                        "publicationDate": "2024-03-01",
                        "url": "https://example.com/s2",
                        "authors": [{"name": "Grace Hopper"}],
                        "externalIds": {"DOI": "10.1000/s2.1"},
                    }
                ]
            },
        )

    items = SemanticScholar(_client(handler)).search("agents", 3)
    assert items[0].canonical_id == "doi:10.1000/s2.1"
    assert items[0].venue_or_site == "ACL"
    assert items[0].authors == "Grace Hopper"


def test_brave_search_parses_hits_and_skips_without_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Subscription-Token"] == "brave-key"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "Paper",
                            "url": "https://arxiv.org/abs/2401.00001",
                            "description": "A paper",
                        },
                        {
                            "title": "Blog",
                            "url": "https://example.com/notes",
                            "description": "A post",
                        },
                    ]
                }
            },
        )

    assert BraveSearch(_client(handler), api_key="").search("agents", 5) == []
    hits = BraveSearch(_client(handler), api_key="brave-key").search("agents", 5)
    assert looks_like_paper(hits[0].url)
    assert not looks_like_paper(hits[1].url)
    assert doi_from_text("https://doi.org/10.1000/test.1") == "10.1000/test.1"


def test_http_retries_then_returns_none():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="no")

    retries = []
    result = get_json(
        _client(handler),
        "https://example.com/works",
        on_retry=lambda: retries.append(1),
    )
    assert result is None
    assert calls["n"] == 3
    assert retries == [1, 1]


def test_public_urls_and_excerpt():
    assert public_http_url("https://example.com/post")
    assert not public_http_url("http://127.0.0.1/secret")
    assert not public_http_url("file:///tmp/x")
    html = """
    <html><head><title>Field Notes</title></head>
    <body><article><p>These notes explain retrieval for research agents in detail.</p></article></body>
    </html>
    """
    extracted = excerpt_from_html(html)
    assert extracted is not None
    assert "retrieval" in extracted["excerpt"].lower() or extracted["title"]
