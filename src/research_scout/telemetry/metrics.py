import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path


log = logging.getLogger("research_scout")


def _stats(scores: list[int]) -> dict[str, float | int | None]:
    if not scores:
        return {"min": None, "mean": None, "max": None}
    return {
        "min": min(scores),
        "mean": round(sum(scores) / len(scores), 2),
        "max": max(scores),
    }


@dataclass
class RunMetrics:
    run_id: str
    model: str
    username: str = ""
    provider: str = "ollama"
    query_model: str = ""
    success: bool = False
    started: float = field(default_factory=time.perf_counter)
    stages_ms: dict[str, float] = field(default_factory=dict)
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    load_ns: int = 0
    prompt_eval_ns: int = 0
    eval_ns: int = 0
    scorer_provider: str = "ollama"
    scorer_requested_model: str = ""
    scorer_model: str = ""
    scorer_base_url: str = ""
    scorer_calls: int = 0
    scorer_prompt_tokens: int = 0
    scorer_completion_tokens: int = 0
    scorer_latency_ms: float = 0
    scorer_input_cost_per_million: float = 0
    scorer_output_cost_per_million: float = 0
    retrieval_index: int = 0
    retrieval_web: int = 0
    duplicates_skipped: int = 0
    adjacent_papers_written: int = 0
    papers_written: int = 0
    papers_shortfall: int = 0
    blogs_written: int = 0
    blogs_rejected: int = 0
    retries: int = 0
    score_paper: list[int] = field(default_factory=list)
    score_blog: list[int] = field(default_factory=list)
    prompt_cost_per_million: float = 0
    completion_cost_per_million: float = 0

    def add_retry(self) -> None:
        self.retries += 1

    def add_llm(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        load_ns: int,
        prompt_eval_ns: int,
        eval_ns: int,
    ) -> None:
        self.llm_calls += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.load_ns += load_ns
        self.prompt_eval_ns += prompt_eval_ns
        self.eval_ns += eval_ns

    def add_scorer(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        model: str = "",
    ) -> None:
        self.llm_calls += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.scorer_calls += 1
        self.scorer_prompt_tokens += prompt_tokens
        self.scorer_completion_tokens += completion_tokens
        self.scorer_latency_ms += latency_ms
        if model:
            self.scorer_model = model
            self.model = model

    def to_dict(self) -> dict:
        eval_seconds = self.eval_ns / 1_000_000_000
        ollama_completion = self.completion_tokens
        ollama_prompt = self.prompt_tokens
        scorer_cost = 0.0
        if self.scorer_provider == "jev":
            ollama_prompt -= self.scorer_prompt_tokens
            ollama_completion -= self.scorer_completion_tokens
            scorer_cost = (
                self.scorer_prompt_tokens / 1_000_000 * self.scorer_input_cost_per_million
                + self.scorer_completion_tokens / 1_000_000 * self.scorer_output_cost_per_million
            )
        tokens_per_second = round(ollama_completion / eval_seconds, 2) if eval_seconds else 0
        cost = (
            ollama_prompt / 1_000_000 * self.prompt_cost_per_million
            + ollama_completion / 1_000_000 * self.completion_cost_per_million
            + scorer_cost
        )
        return {
            "run_id": self.run_id,
            "username": self.username,
            "provider": self.provider,
            "model": self.model,
            "query_model": self.query_model,
            "success": self.success,
            "duration_ms": round((time.perf_counter() - self.started) * 1000, 1),
            "stages_ms": self.stages_ms,
            "llm_calls": self.llm_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "ollama_load_ms": round(self.load_ns / 1_000_000, 1),
            "ollama_prompt_eval_ms": round(self.prompt_eval_ns / 1_000_000, 1),
            "ollama_eval_ms": round(self.eval_ns / 1_000_000, 1),
            "tokens_per_second": tokens_per_second,
            "retrieval": {"index": self.retrieval_index, "web": self.retrieval_web},
            "duplicates_skipped": self.duplicates_skipped,
            "adjacent_papers_written": self.adjacent_papers_written,
            "papers_written": self.papers_written,
            "papers_shortfall": self.papers_shortfall,
            "blogs_written": self.blogs_written,
            "blogs_rejected": self.blogs_rejected,
            "scores": {"paper": _stats(self.score_paper), "blog": _stats(self.score_blog)},
            "retries": self.retries,
            "estimated_cost_usd": round(cost, 6),
            "scorer": {
                "provider": self.scorer_provider,
                "requested_model": self.scorer_requested_model or self.scorer_model,
                "model": self.scorer_model or self.scorer_requested_model,
                "base_url": self.scorer_base_url,
                "calls": self.scorer_calls,
                "prompt_tokens": self.scorer_prompt_tokens,
                "completion_tokens": self.scorer_completion_tokens,
                "latency_ms": round(self.scorer_latency_ms, 1),
                "estimated_cost_usd": round(scorer_cost, 6),
            },
        }


def write_metrics(path: Path, metrics: RunMetrics) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics.to_dict(), indent=2) + "\n", encoding="utf-8")


@contextmanager
def stage(metrics: RunMetrics, name: str):
    log.info("stage start name=%s", name)
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        metrics.stages_ms[name] = elapsed
        log.info("stage end name=%s latency_ms=%s", name, elapsed)
