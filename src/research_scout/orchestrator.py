import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from research_scout.agents.relevancy import Scorer
from research_scout.config import Settings
from research_scout.models import Item, Profile, title_key
from research_scout.telemetry.metrics import RunMetrics, stage, write_metrics
from research_scout.workers.writer import Known, Writer

log = logging.getLogger("research_scout")

_STATUS = {
    "query": "Planning searches",
    "retrieve": "Searching papers and blogs",
    "score": "Scoring matches",
    "adjacent_query": "Planning adjacent topics",
    "adjacent_retrieve": "Searching adjacent topics",
    "adjacent_score": "Scoring adjacent papers",
    "write": "Saving results",
}


@dataclass
class RunResult:
    papers_written: int
    blogs_written: int
    blogs_rejected: int
    duplicates_skipped: int
    papers_shortfall: int
    results_path: Path
    log_path: Path
    metrics_path: Path


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        query_agent,
        retrieval,
        scorer: Scorer,
        writer: Writer,
        metrics: RunMetrics,
        log_path: Path,
        metrics_path: Path,
    ):
        self.settings = settings
        self.query_agent = query_agent
        self.retrieval = retrieval
        self.scorer = scorer
        self.writer = writer
        self.metrics = metrics
        self.log_path = log_path
        self.metrics_path = metrics_path
        self.on_status = None

    def run(
        self,
        profile: Profile,
        on_status: Callable[[str], None] | None = None,
    ) -> RunResult:
        self.on_status = on_status
        self.metrics.username = profile.username
        log.info("orchestrator start username=%s", profile.username)
        results_path = self.writer.ensure_file(profile.username)
        known = self.writer.known(profile.username)
        log.info("worker=writer known papers_or_blogs=%s", len(known.ids))
        try:
            papers, blogs = self._gather(profile, known)
            chosen = papers + blogs
            with self._step("write"):
                self.writer.append(profile.username, chosen)
            self._record(papers, blogs)
            log.info(
                "write papers=%s blogs=%s rejected_blogs=%s shortfall=%s",
                self.metrics.papers_written,
                self.metrics.blogs_written,
                self.metrics.blogs_rejected,
                self.metrics.papers_shortfall,
            )
        except Exception as exc:
            self.metrics.success = False
            log.info("run failed error=%s", type(exc).__name__)
            raise
        finally:
            write_metrics(self.metrics_path, self.metrics)
        return RunResult(
            papers_written=self.metrics.papers_written,
            blogs_written=self.metrics.blogs_written,
            blogs_rejected=self.metrics.blogs_rejected,
            duplicates_skipped=self.metrics.duplicates_skipped,
            papers_shortfall=self.metrics.papers_shortfall,
            results_path=results_path,
            log_path=self.log_path,
            metrics_path=self.metrics_path,
        )

    def _gather(self, profile: Profile, known: Known) -> tuple[list[Item], list[Item]]:
        with self._step("query"):
            paper_queries, blog_queries = self.query_agent.plan(profile)
        with self._step("retrieve"):
            found = self.retrieval.collect(paper_queries, blog_queries, "direct")
        fresh, skipped = split_new(found, known)
        self.metrics.duplicates_skipped += skipped
        log.info("dedup skipped=%s", skipped)
        with self._step("score"):
            self.scorer.score_batch(profile, fresh)
        papers, blogs, rejected = select_items(fresh, self.settings)
        self.metrics.blogs_rejected += rejected

        if len(papers) < self.settings.paper_target:
            short = self.settings.paper_target - len(papers)
            log.info("adjacent shortfall=%s", short)
            with self._step("adjacent_query"):
                extra_queries = self.query_agent.adjacent(profile)
            with self._step("adjacent_retrieve"):
                more = self.retrieval.collect(extra_queries, [], "adjacent")
            more_fresh, skipped_more = split_new(more, known, papers)
            self.metrics.duplicates_skipped += skipped_more
            log.info("dedup skipped=%s", skipped_more)
            with self._step("adjacent_score"):
                self.scorer.score_batch(profile, more_fresh)
            cap_adjacent_scores(papers, more_fresh)
            extra, _, _ = select_items(more_fresh, self.settings, papers_only=True)
            papers.extend(extra[:short])

        return papers[: self.settings.paper_target], blogs[: self.settings.blog_target]

    def _step(self, name: str):
        if self.on_status:
            self.on_status(_STATUS[name])
        return stage(self.metrics, name)

    def _record(self, papers: list[Item], blogs: list[Item]) -> None:
        self.metrics.papers_written = len(papers)
        self.metrics.blogs_written = len(blogs)
        self.metrics.adjacent_papers_written = sum(item.relation == "adjacent" for item in papers)
        self.metrics.papers_shortfall = max(0, self.settings.paper_target - len(papers))
        self.metrics.score_paper = [item.relevancy_score for item in papers]
        self.metrics.score_blog = [item.relevancy_score for item in blogs]
        self.metrics.success = True


def split_new(found: list[Item], known: Known, *already: list[Item]) -> tuple[list[Item], int]:
    seen_ids = set(known.ids)
    batch_titles: set[str] = set()
    for group in already:
        for item in group:
            seen_ids.add(item.canonical_id)
            if item.kind == "paper":
                batch_titles.add(title_key(item.title))
    fresh: list[Item] = []
    skipped = 0
    for item in found:
        key = title_key(item.title) if item.kind == "paper" else ""
        if item.canonical_id in known.ids or (key and key in known.titles):
            skipped += 1
            reason = "already_stored" if item.canonical_id in known.ids else "same_title"
            log.info("dedup skip kind=%s title=%s reason=%s", item.kind, _title(item.title), reason)
            continue
        if item.canonical_id in seen_ids or (key and key in batch_titles):
            continue
        seen_ids.add(item.canonical_id)
        if key:
            batch_titles.add(key)
        fresh.append(item)
    return fresh, skipped


def select_items(
    items: list[Item],
    settings: Settings,
    *,
    papers_only: bool = False,
) -> tuple[list[Item], list[Item], int]:
    papers = sorted(
        (item for item in items if item.kind == "paper"),
        key=lambda item: item.relevancy_score,
        reverse=True,
    )
    if papers_only:
        return papers, [], 0
    blogs = [item for item in items if item.kind == "blog"]
    rejected_blogs = [item for item in blogs if item.relevancy_score < settings.blog_min_score]
    for item in rejected_blogs:
        log.info(
            "reject kind=blog title=%s score=%s min=%s band=%s reason=%s",
            _title(item.title),
            item.relevancy_score,
            settings.blog_min_score,
            item.band or "weak",
            item.reason or "score below minimum",
        )
    rejected = len(rejected_blogs)
    kept = sorted(
        (item for item in blogs if item.relevancy_score >= settings.blog_min_score),
        key=lambda item: item.relevancy_score,
        reverse=True,
    )
    return papers, kept, rejected


def cap_adjacent_scores(direct_papers: list[Item], candidates: list[Item]) -> None:
    direct_scores = [item.relevancy_score for item in direct_papers if item.kind == "paper"]
    ceiling = min(direct_scores) - 1 if direct_scores else 60
    ceiling = max(0, min(60, ceiling))
    for item in candidates:
        if item.kind == "paper" and item.relation == "adjacent":
            original = item.relevancy_score
            item.band = "adjacent"
            item.relevancy_score = min(item.relevancy_score, ceiling)
            if item.relevancy_score != original:
                log.info(
                    "score cap title=%s from=%s to=%s band=adjacent",
                    _title(item.title),
                    original,
                    item.relevancy_score,
                )


def _title(title: str) -> str:
    text = " ".join(title.split())
    return text if len(text) <= 80 else text[:77] + "..."
