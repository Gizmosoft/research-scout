import re
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field

USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.IGNORECASE)

USER_FIELDS = [
    "username",
    "domain",
    "research_interests",
    "goals",
    "key_skills",
    "created_at",
]
RESULT_FIELDS = [
    "kind",
    "canonical_id",
    "title",
    "authors",
    "source",
    "venue_or_site",
    "published_date",
    "url",
    "excerpt",
    "query",
    "band",
    "relevancy_score",
    "reason",
    "retrieved_at",
]


def clean_text(value: str, limit: int = 400) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def normalize_doi(doi: str) -> str:
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE)
    return text.lower().rstrip(").,")


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def doi_from_text(value: str) -> str | None:
    match = _DOI_RE.search(value or "")
    if not match:
        return None
    return normalize_doi(match.group(0))


def arxiv_id_from_text(value: str) -> str | None:
    match = _ARXIV_RE.search(value or "")
    if not match:
        return None
    return match.group(1)


def paper_canonical_id(
    *,
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str = "",
    url: str = "",
) -> str:
    if doi:
        return "doi:" + normalize_doi(doi)
    if arxiv_id:
        return "arxiv:" + arxiv_id.lower()
    if url:
        return "url:" + canonical_url(url)
    return "title:" + title_key(title)


class Profile(BaseModel):
    username: str
    domain: str
    research_interests: str
    goals: str
    key_skills: str
    created_at: str


class Item(BaseModel):
    kind: Literal["paper", "blog"]
    canonical_id: str
    title: str
    authors: str = ""
    source: str = ""
    venue_or_site: str = ""
    published_date: str = ""
    url: str = ""
    excerpt: str = ""
    query: str = ""
    band: str = ""
    relevancy_score: int = 0
    reason: str = ""
    retrieved_at: str = ""
    relation: Literal["direct", "adjacent"] = Field(default="direct", exclude=True)

    def row(self) -> dict[str, str]:
        venue = "" if self.kind == "blog" else self.venue_or_site
        return {
            "kind": self.kind,
            "canonical_id": self.canonical_id,
            "title": self.title,
            "authors": self.authors,
            "source": self.source,
            "venue_or_site": venue,
            "published_date": self.published_date,
            "url": self.url,
            "excerpt": self.excerpt,
            "query": self.query,
            "band": self.band,
            "relevancy_score": str(self.relevancy_score),
            "reason": self.reason,
            "retrieved_at": self.retrieved_at,
        }
