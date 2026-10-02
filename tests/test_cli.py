import json

from research_scout.cli import main


def test_missing_ollama_prints_banner_and_skips_prompt(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("METRICS_DIR", str(tmp_path / "metrics"))
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:latest")

    def fail(prompt=""):
        raise AssertionError("prompted")

    monkeypatch.setattr("builtins.input", fail)
    monkeypatch.setattr("research_scout.cli.OllamaClient.ready", lambda self: False)

    try:
        main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected exit")

    output = capsys.readouterr().out
    assert "RESEARCH SCOUT" in output
    assert "llama3:latest" in output
    logs = list((tmp_path / "logs").glob("session-*.log"))
    metrics = list((tmp_path / "metrics").glob("run-*.json"))
    assert len(logs) == 1
    assert len(metrics) == 1
    body = json.loads(metrics[0].read_text())
    assert body["success"] is False
    assert "prompt_tokens" in body
    assert "startup failed" in logs[0].read_text()
