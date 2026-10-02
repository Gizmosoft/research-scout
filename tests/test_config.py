from pathlib import Path

from research_scout.cli import main
from research_scout.config import Settings, _SETUP_ENV_VARS, init_config


def _home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def test_user_config_is_read_and_local_env_overrides_it(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    init_config()
    config = Path.home() / ".config" / "research-scout" / "config.env"
    config.write_text("JEV_API_KEY=from-home\nOLLAMA_MODEL=from-home\n", encoding="utf-8")
    (tmp_path / ".env").write_text("OLLAMA_MODEL=from-cwd\n", encoding="utf-8")

    settings = Settings(_env_file=None)
    untouched = settings.ollama_model
    settings = Settings()

    assert untouched == "llama3:latest"
    assert settings.jev_api_key == "from-home"
    assert settings.ollama_model == "from-cwd"


def test_shell_env_overrides_config_files(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    init_config()
    config = Path.home() / ".config" / "research-scout" / "config.env"
    config.write_text("JEV_API_KEY=from-home\n", encoding="utf-8")
    monkeypatch.setenv("JEV_API_KEY", "from-shell")

    assert Settings().jev_api_key == "from-shell"


def test_init_writes_config_once(tmp_path, monkeypatch, capsys):
    _home(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["research-scout", "init"])

    main()
    first = capsys.readouterr().out
    path = Path.home() / ".config" / "research-scout" / "config.env"
    assert path.exists()
    assert "Wrote" in first
    assert "JEV_API_KEY=" in path.read_text()

    path.write_text("JEV_API_KEY=keep-me\n", encoding="utf-8")
    main()
    second = capsys.readouterr().out
    assert "already exists" in second
    assert path.read_text() == "JEV_API_KEY=keep-me\n"


def test_unconfigured_run_asks_for_init(tmp_path, monkeypatch, capsys):
    _home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["research-scout"])
    for name in _SETUP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(AssertionError("prompted")))

    try:
        main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected exit")

    output = capsys.readouterr().out
    assert "research-scout init" in output
    assert not (tmp_path / "logs").exists()
    assert not (tmp_path / "metrics").exists()
    assert not (tmp_path / "data").exists()


def test_packaged_install_creates_users_and_results_only(tmp_path, monkeypatch):
    monkeypatch.setattr("research_scout.config.running_from_source", lambda: False)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
        logs_dir=tmp_path / "logs",
        metrics_dir=tmp_path / "metrics",
    )
    settings.ensure_dirs()
    assert settings.write_telemetry is False
    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "results").is_dir()
    assert not (tmp_path / "logs").exists()
    assert not (tmp_path / "metrics").exists()
