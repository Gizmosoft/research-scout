import logging

from research_scout.models import Profile, clean_text
from research_scout.telemetry.ollama_client import OllamaClient

log = logging.getLogger("research_scout")

_PLAN = (
    "Plan searches for a researcher. "
    'Reply with JSON only: {"paper_queries": ["..."], "blog_queries": ["..."]}. '
    "Give 4 paper queries and 3 blog queries. Each query is under 12 words."
)
_ADJACENT = (
    "Direct paper search was short. "
    'Reply with JSON only: {"paper_queries": ["..."]}. '
    "Give 3 queries on adjacent topics. Each query is under 12 words."
)


class QueryAgent:
    def __init__(self, llm: OllamaClient):
        self.llm = llm

    def plan(self, profile: Profile) -> tuple[list[str], list[str]]:
        payload = self.llm.chat_json(_PLAN, _profile_text(profile), task="plan")
        papers = _strings(payload.get("paper_queries"), 4)
        blogs = _strings(payload.get("blog_queries"), 3)
        if not papers:
            papers = [clean_text(profile.research_interests or profile.domain, 80)]
        log.info("agent=query task=plan papers=%s blogs=%s", len(papers), len(blogs))
        for query in papers:
            log.info("agent=query kind=paper query=%s", query)
        for query in blogs:
            log.info("agent=query kind=blog query=%s", query)
        return papers, blogs

    def adjacent(self, profile: Profile) -> list[str]:
        payload = self.llm.chat_json(_ADJACENT, _profile_text(profile), task="adjacent")
        papers = _strings(payload.get("paper_queries"), 3)
        if not papers:
            papers = [clean_text(profile.domain, 80)]
        log.info("agent=query task=adjacent papers=%s", len(papers))
        for query in papers:
            log.info("agent=query kind=adjacent query=%s", query)
        return papers


def _profile_text(profile: Profile) -> str:
    return (
        f"Domain: {profile.domain}\n"
        f"Interests: {profile.research_interests}\n"
        f"Goals: {profile.goals}\n"
        f"Skills: {profile.key_skills}"
    )


def _strings(value, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    queries = []
    for item in value:
        text = clean_text(str(item), 120)
        if text:
            queries.append(text)
        if len(queries) == limit:
            break
    return queries
