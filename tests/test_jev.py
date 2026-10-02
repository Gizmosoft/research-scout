import json

import httpx

from research_scout.agents.jev_scorer import ITEMS_PER_CALL, RUBRIC, JevScorer
from research_scout.cli import main
from research_scout.config import Settings
from research_scout.models import Item, Profile
from research_scout.telemetry.jev_client import JevClient
from research_scout.telemetry.logging import setup_logging
from research_scout.telemetry.metrics import RunMetrics


def _profile() -> Profile:
    return Profile(
        username="a",
        domain="regulatory publishing",
        research_interests="eCTD",
        goals="faster submissions",
        key_skills="writing",
        created_at="2026-01-01T00:00:00Z",
    )


def _item(number: int) -> Item:
    return Item(
        kind="blog",
        canonical_id=f"url:https://example.com/posts/{number}",
        title=f"Note {number}",
        url=f"https://example.com/posts/{number}",
        excerpt="Practical notes on eCTD publishing.",
    )


def _settings(**overrides) -> Settings:
    values = {
        "jev_api_key": "secret-key",
        "jev_base_url": "https://jev.test",
        "jev_model": "jev-latest",
        "jev_cost_per_million_input_tokens": 0.042,
        "scorer": "jev",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _ScriptedJev:
    def __init__(self, answers_for):
        self.calls = []
        self._answers_for = answers_for

    def ask(self, state, questions, *, task):
        self.calls.append({"state": state, "questions": questions, "task": task})
        return {"model": "jev-1.13.0", "answers": self._answers_for(questions)}


def test_one_score_question_maps_position_and_likely_level():
    blog = _item(1)
    blog.canonical_id = "url:https://example.com/very/long/blog/path"

    def answers_for(questions):
        assert list(questions) == ["i0"]
        question = questions["i0"]
        assert question["type"] == "score"
        assert question["criteria"] == [RUBRIC["weak"], RUBRIC["adjacent"], RUBRIC["direct"]]
        text = json.dumps(question)
        assert text.count(blog.title) == 1
        assert "very/long/blog" not in text
        return {
            "i0": {
                "type": "score",
                "score": 1.68,
                "probabilities": {"0": 0.05, "1": 0.11, "2": 0.84},
            }
        }

    client = _ScriptedJev(answers_for)
    JevScorer(client).score_batch(_profile(), [blog])

    assert blog.relevancy_score == 84
    assert blog.band == "direct"
    assert blog.reason == RUBRIC["direct"]
    assert client.calls[0]["state"]["domain"] == "regulatory publishing"
    assert "url" not in json.dumps(client.calls[0]["questions"])


def test_large_pool_is_one_parallel_call_per_chunk():
    items = [_item(number) for number in range(ITEMS_PER_CALL + 1)]

    def answers_for(questions):
        answers = {}
        for key in questions:
            index = int(key[1:])
            answers[f"i{index}"] = {
                "type": "score",
                "score": 0.8,
                "probabilities": {"0": 0.7, "1": 0.2, "2": 0.1},
            }
        return answers

    client = _ScriptedJev(answers_for)
    JevScorer(client).score_batch(_profile(), items)

    assert [len(call["questions"]) for call in client.calls] == [ITEMS_PER_CALL, 1]
    assert items[0].relevancy_score == 40
    assert items[0].reason == RUBRIC["weak"]
    assert items[-1].band == "weak"


def test_missing_answer_is_unavailable():
    item = _item(1)
    client = _ScriptedJev(lambda questions: {})
    JevScorer(client).score_batch(_profile(), [item])
    assert item.relevancy_score == 0
    assert item.band == "weak"
    assert item.reason == "score unavailable"


def test_client_records_jev_usage_and_hides_the_key(tmp_path, monkeypatch):
    monkeypatch.setattr("research_scout.telemetry.jev_client.time.sleep", lambda _seconds: None)
    log_path = tmp_path / "session.log"
    setup_logging(log_path)
    metrics = RunMetrics(
        run_id="jev",
        model="jev-latest",
        provider="jev",
        query_model="llama3:latest",
        scorer_provider="jev",
        scorer_requested_model="jev-latest",
        scorer_base_url="https://jev.test",
        scorer_input_cost_per_million=0.042,
        prompt_cost_per_million=2,
    )
    metrics.add_llm(
        prompt_tokens=1_000_000,
        completion_tokens=10,
        load_ns=0,
        prompt_eval_ns=0,
        eval_ns=1_000_000_000,
    )
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-key"
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {"i0-fit": {"type": "noul", "noul": 0.5}},
                "usage": {"input_tokens": 1_000_000, "output_tokens": 20},
            },
        )

    client = JevClient(_settings(), metrics)
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    payload = client.ask({"domain": "publishing"}, {"i0-fit": {"type": "noul"}}, task="score batch=1")
    client.close()

    assert payload["model"] == "jev-1.13.0"
    body = metrics.to_dict()
    assert body["model"] == "jev-1.13.0"
    assert body["query_model"] == "llama3:latest"
    assert body["llm_calls"] == 2
    assert body["prompt_tokens"] == 2_000_000
    assert body["retries"] == 1
    assert body["scorer"]["calls"] == 1
    assert body["scorer"]["requested_model"] == "jev-latest"
    assert body["scorer"]["model"] == "jev-1.13.0"
    assert body["scorer"]["base_url"] == "https://jev.test"
    assert body["scorer"]["prompt_tokens"] == 1_000_000
    assert body["scorer"]["completion_tokens"] == 20
    assert body["scorer"]["estimated_cost_usd"] == 0.042
    assert body["estimated_cost_usd"] == 2.042
    assert body["tokens_per_second"] == 10
    text = log_path.read_text()
    assert "llm provider=jev task=score batch=1" in text
    assert "model=jev-1.13.0" in text
    assert "prompt_tokens=1000000" in text
    assert "secret-key" not in text


def test_auth_failure_is_not_retried():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "no"})

    metrics = RunMetrics(run_id="jev", model="jev-latest", scorer_provider="jev")
    client = JevClient(_settings(), metrics)
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        client.ask({}, {"q": {"type": "noul"}}, task="score batch=1")
    except Exception as exc:
        assert type(exc).__name__ == "JevError"
    else:
        raise AssertionError("expected failure")
    assert metrics.retries == 0
    assert metrics.scorer_calls == 0
    client.close()


def test_missing_jev_key_exits_before_prompt(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("SCORER", "jev")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("METRICS_DIR", str(tmp_path / "metrics"))
    monkeypatch.setattr("research_scout.cli.OllamaClient.ready", lambda self: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(AssertionError("prompted")))

    try:
        main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected exit")

    output = capsys.readouterr().out
    assert "JEV_API_KEY" in output
    body = json.loads(next((tmp_path / "metrics").glob("run-*.json")).read_text())
    assert body["success"] is False
    assert body["provider"] == "jev"
    assert body["scorer"]["provider"] == "jev"
    assert body["scorer"]["requested_model"] == "jev-latest"
    assert body["scorer"]["base_url"] == "https://api.typesafe.ai"
    assert body["query_model"] == "llama3:latest"
    assert "startup failed reason=jev" in next((tmp_path / "logs").glob("session-*.log")).read_text()
