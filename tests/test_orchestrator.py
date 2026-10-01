import csv
import json

from research_scout.agents.query import QueryAgent
from research_scout.telemetry.ollama_client import OllamaClient
from research_scout.config import Settings
from research_scout.models import Item, Profile
from research_scout.orchestrator import Orchestrator, cap_adjacent_scores, split_new
from research_scout.telemetry.logging import setup_logging
from research_scout.telemetry.metrics import RunMetrics
from research_scout.workers.writer import Writer


class FakeQuery:
    def plan(self, profile):
        return ["direct papers"], ["direct blogs"]

    def adjacent(self, profile):
        return ["adjacent papers"]


class FakeRetrieval:
    def __init__(self, direct, adjacent):
        self.direct = direct
        self.adjacent = adjacent
        self.relations = []

    def collect(self, paper_queries, blog_queries, relation):
        self.relations.append(relation)
        return list(self.direct if relation == "direct" else self.adjacent)


class FakeScorer:
    def __init__(self, scores):
        self.scores = scores

    def score_batch(self, profile, items):
        for item in items:
            score, band, reason = self.scores[item.canonical_id]
            item.relevancy_score = score
            item.band = band
            item.reason = reason


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat_json(self, system, user, task=""):
        return self.replies.pop(0)


def _settings(tmp_path) -> Settings:
    settings = Settings(
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
        logs_dir=tmp_path / "logs",
        metrics_dir=tmp_path / "metrics",
        paper_target=2,
        blog_target=1,
        blog_min_score=70,
        _env_file=None,
    )
    settings.ensure_dirs()
    return settings


def _profile() -> Profile:
    return Profile(
        username="ada_1",
        domain="machine learning",
        research_interests="research agents",
        goals="find papers",
        key_skills="python",
        created_at="2026-01-01T00:00:00Z",
    )


def _paper(canonical_id, title, relation="direct") -> Item:
    return Item(
        kind="paper",
        canonical_id=canonical_id,
        title=title,
        authors="Ada",
        source="openalex",
        venue_or_site="Venue",
        published_date="2024-01-01",
        url=f"https://example.com/{canonical_id}",
        excerpt="Abstract text.",
        query="agents",
        relation=relation,
    )


def _blog(canonical_id, title) -> Item:
    return Item(
        kind="blog",
        canonical_id=canonical_id,
        title=title,
        authors="Grace",
        source="example.com",
        url="https://example.com/notes",
        excerpt="Practical notes.",
        query="agents",
    )


def _run(tmp_path, retrieval, scores):
    settings = _settings(tmp_path)
    log_path = settings.logs_dir / "session-test.log"
    metrics_path = settings.metrics_dir / "run-test.json"
    setup_logging(log_path)
    metrics = RunMetrics(run_id="test", model="llama3:latest")
    writer = Writer(settings)
    orchestrator = Orchestrator(
        settings,
        FakeQuery(),
        retrieval,
        FakeScorer(scores),
        writer,
        metrics,
        log_path,
        metrics_path,
    )
    result = orchestrator.run(_profile())
    return result, metrics_path, log_path


def test_run_writes_new_rows_caps_adjacent_and_rejects_weak_blogs(tmp_path):
    direct = [
        _paper("doi:10.1/old", "Old Paper"),
        _paper("doi:10.1/new", "New Paper"),
        _blog("url:https://example.com/good", "Good notes"),
        _blog("url:https://example.com/weak", "Weak notes"),
    ]
    adjacent = [_paper("doi:10.1/adj", "Nearby Paper", relation="adjacent")]
    writer = Writer(_settings(tmp_path))
    writer.append("ada_1", [_paper("doi:10.1/old", "Old Paper")])
    scores = {
        "doi:10.1/new": (85, "direct", "on topic"),
        "doi:10.1/adj": (95, "direct", "nearby topic"),
        "url:https://example.com/good": (80, "direct", "useful notes"),
        "url:https://example.com/weak": (40, "weak", "loose overlap"),
    }
    result, metrics_path, log_path = _run(tmp_path, FakeRetrieval(direct, adjacent), scores)

    with result.results_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_id = {row["canonical_id"]: row for row in rows}
    assert result.papers_written == 2
    assert result.blogs_written == 1
    assert result.blogs_rejected == 1
    assert result.duplicates_skipped == 1
    assert result.papers_shortfall == 0
    assert by_id["doi:10.1/new"]["band"] == "direct"
    assert int(by_id["doi:10.1/new"]["relevancy_score"]) == 85
    assert by_id["doi:10.1/adj"]["band"] == "adjacent"
    assert int(by_id["doi:10.1/adj"]["relevancy_score"]) < 85
    assert int(by_id["doi:10.1/adj"]["relevancy_score"]) <= 60
    assert "url:https://example.com/weak" not in by_id
    assert by_id["url:https://example.com/good"]["venue_or_site"] == ""

    body = json.loads(metrics_path.read_text())
    assert body["success"] is True
    assert body["prompt_tokens"] == 0
    assert "score" in body["stages_ms"]
    assert "adjacent_score" in body["stages_ms"]
    assert body["retrieval"] == {"index": 0, "web": 0}
    assert body["papers_written"] == 2
    assert body["blogs_rejected"] == 1
    assert body["scores"]["paper"]["max"] == 85
    log_text = log_path.read_text()
    assert "shortfall=0" in log_text
    assert "reject kind=blog title=Weak notes score=40 min=70 band=weak reason=loose overlap" in log_text
    assert "dedup skip kind=paper title=Old Paper reason=already_stored" in log_text
    assert "score cap title=Nearby Paper from=95 to=60 band=adjacent" in log_text

    before = len(rows)
    _run(tmp_path, FakeRetrieval(direct, adjacent), scores)
    with result.results_path.open(newline="", encoding="utf-8") as handle:
        after = list(csv.DictReader(handle))
    assert len(after) == before


def test_shortfall_is_logged_when_search_is_exhausted(tmp_path):
    result, metrics_path, log_path = _run(tmp_path, FakeRetrieval([], []), {})
    body = json.loads(metrics_path.read_text())
    assert result.papers_written == 0
    assert result.papers_shortfall == 2
    assert body["papers_shortfall"] == 2
    assert "shortfall=2" in log_path.read_text()
    assert result.results_path.exists()


def test_same_title_is_treated_as_duplicate(tmp_path):
    settings = _settings(tmp_path)
    writer = Writer(settings)
    writer.append("ada_1", [_paper("doi:10.1/a", "Same Title")])
    fresh, skipped = split_new(
        [_paper("doi:10.1/b", "Same Title!")],
        writer.known("ada_1"),
    )
    assert fresh == []
    assert skipped == 1


def test_adjacent_cap_stays_below_direct_scores():
    direct = [_paper("doi:10.1/a", "Direct")]
    direct[0].relevancy_score = 50
    adjacent = [_paper("doi:10.1/b", "Adjacent", relation="adjacent")]
    adjacent[0].relevancy_score = 90
    adjacent[0].band = "direct"
    cap_adjacent_scores(direct, adjacent)
    assert adjacent[0].band == "adjacent"
    assert adjacent[0].relevancy_score == 49


def test_query_agent_falls_back_when_queries_are_empty():
    agent = QueryAgent(ScriptedLLM([{"paper_queries": [], "blog_queries": ["lab notes"]}]))
    papers, blogs = agent.plan(_profile())
    assert papers == ["research agents"]
    assert blogs == ["lab notes"]


def test_llm_call_logs_latency_and_tokens(tmp_path):
    settings = _settings(tmp_path)
    log_path = settings.logs_dir / "llm.log"
    setup_logging(log_path)
    metrics = RunMetrics(run_id="llm", model="llama3:latest")
    client = OllamaClient("http://127.0.0.1:11434", "llama3:latest", metrics)

    class FakeChat:
        def chat(self, **kwargs):
            return {
                "message": {"content": '{"ok": true}'},
                "prompt_eval_count": 12,
                "eval_count": 4,
                "load_duration": 0,
                "prompt_eval_duration": 0,
                "eval_duration": 0,
            }

    client._client = FakeChat()
    assert client.chat_json("system", "user", task="plan") == {"ok": True}
    text = log_path.read_text()
    assert "llm task=plan" in text
    assert "latency_ms=" in text
    assert "prompt_tokens=12" in text
    assert "completion_tokens=4" in text


def test_metrics_record_tokens_and_cost():
    metrics = RunMetrics(
        run_id="r",
        model="llama3:latest",
        prompt_cost_per_million=2,
        completion_cost_per_million=3,
    )
    metrics.add_llm(
        prompt_tokens=1_000_000,
        completion_tokens=10,
        load_ns=1_000_000,
        prompt_eval_ns=2_000_000,
        eval_ns=1_000_000_000,
    )
    body = metrics.to_dict()
    assert body["prompt_tokens"] == 1_000_000
    assert body["completion_tokens"] == 10
    assert body["tokens_per_second"] == 10
    assert body["ollama_load_ms"] == 1
    assert body["estimated_cost_usd"] == 2.00003
    assert "duration_ms" in body
