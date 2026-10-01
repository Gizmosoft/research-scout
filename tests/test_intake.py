import csv

from research_scout.config import Settings
from research_scout.models import Profile
from research_scout.workers.intake import IntakeWorker


def _settings(tmp_path) -> Settings:
    settings = Settings(
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
        logs_dir=tmp_path / "logs",
        metrics_dir=tmp_path / "metrics",
        _env_file=None,
    )
    settings.ensure_dirs()
    return settings


def test_new_user_is_stored_once(tmp_path, monkeypatch, capsys):
    answers = iter(["-", "ada_1", "machine learning", "agents", "publish", "python"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    worker = IntakeWorker(_settings(tmp_path))

    created = worker.run()
    again_answers = iter(["ada_1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(again_answers))
    reused = worker.run()

    with (tmp_path / "data" / "users.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["username"] == "ada_1"
    assert rows[0]["research_interests"] == "agents"
    assert reused.created_at == created.created_at
    assert reused.model_dump() == created.model_dump()
    assert "cannot be edited" in capsys.readouterr().out


def test_single_character_username(tmp_path, monkeypatch):
    answers = iter(["a", "nlp", "parsing", "write", "python"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    profile = IntakeWorker(_settings(tmp_path)).run()
    assert profile.username == "a"


def test_profile_round_trip_fields(tmp_path, monkeypatch):
    answers = iter(["ada_1", "nlp", "parsing", "write", "python"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    profile = IntakeWorker(_settings(tmp_path)).run()
    assert isinstance(profile, Profile)
    assert profile.domain == "nlp"
