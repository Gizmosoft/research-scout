import os
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

TIMEOUT_SECONDS = 20.0
MAX_RETRIES = 2
FETCH_BYTE_CAP = 500_000
CANDIDATE_MULTIPLIER = 3

ENV_TEMPLATE = """\
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=llama3:latest
PAPER_TARGET=15
BLOG_TARGET=5
BLOG_MIN_SCORE=70
DATA_DIR=data
RESULTS_DIR=results
WEB_SEARCH_PROVIDER=brave
BRAVE_SEARCH_API_KEY=
OPENALEX_MAILTO=
COST_PER_MILLION_PROMPT_TOKENS=0
COST_PER_MILLION_COMPLETION_TOKENS=0
SCORER=jev
JEV_API_KEY=
JEV_BASE_URL=https://api.typesafe.ai
JEV_MODEL=jev-latest
JEV_COST_PER_MILLION_INPUT_TOKENS=0.042
JEV_COST_PER_MILLION_OUTPUT_TOKENS=0
"""


def config_dir() -> Path:
    return Path.home() / ".config" / "research-scout"


def config_file() -> Path:
    return config_dir() / "config.env"


def default_env_files() -> tuple[Path, Path]:
    """User config first, then .env in the working directory so the local file wins."""
    return (config_file(), Path.cwd() / ".env")


_SETUP_ENV_VARS = (
    "OLLAMA_HOST",
    "OLLAMA_MODEL",
    "JEV_API_KEY",
    "TYPESAFE_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "SCORER",
    "DATA_DIR",
    "RESULTS_DIR",
    "PAPER_TARGET",
    "BLOG_TARGET",
    "BLOG_MIN_SCORE",
)


def needs_init() -> bool:
    """True when no config file, working-directory .env, or shell settings exist."""
    if config_file().exists() or (Path.cwd() / ".env").exists():
        return False
    return not any(os.environ.get(name) for name in _SETUP_ENV_VARS)


def running_from_source() -> bool:
    """True for an editable install or a checkout that is not installed from PyPI."""
    try:
        from importlib.metadata import PackageNotFoundError, distribution
    except ImportError:  # pragma: no cover
        return True
    try:
        dist = distribution("research-scout")
    except PackageNotFoundError:
        return True
    direct = dist.read_text("direct_url.json") or ""
    return '"editable":true' in direct.replace(" ", "")


def _telemetry_default() -> bool:
    return running_from_source()


def init_config() -> tuple[Path, bool]:
    path = config_file()
    if path.exists():
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ENV_TEMPLATE, encoding="utf-8")
    return path, True


class Settings(BaseSettings):
    def __init__(self, **values):
        if "_env_file" not in values:
            values["_env_file"] = default_env_files()
        super().__init__(**values)

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3:latest"
    paper_target: int = Field(default=18, ge=1)
    blog_target: int = Field(default=5, ge=0)
    blog_min_score: int = Field(default=70, ge=0, le=100)
    data_dir: Path = Path("data")
    results_dir: Path = Path("results")
    logs_dir: Path = Path("logs")
    metrics_dir: Path = Path("metrics")
    write_telemetry: bool = Field(default_factory=_telemetry_default)
    web_search_provider: str = "brave"
    brave_search_api_key: str = ""
    openalex_mailto: str = ""
    cost_per_million_prompt_tokens: float = 0
    cost_per_million_completion_tokens: float = 0
    scorer: Literal["jev", "llama"] = "jev"
    jev_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("JEV_API_KEY", "TYPESAFE_API_KEY"),
    )
    jev_base_url: str = "https://api.typesafe.ai"
    jev_model: str = "jev-latest"
    jev_cost_per_million_input_tokens: float = 0.042
    jev_cost_per_million_output_tokens: float = 0

    def ensure_dirs(self) -> None:
        paths = [self.data_dir, self.results_dir]
        if self.write_telemetry:
            paths.extend((self.logs_dir, self.metrics_dir))
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)

    @property
    def user_agent(self) -> str:
        agent = "ResearchScout/1.0"
        if self.openalex_mailto:
            return f"{agent} (mailto:{self.openalex_mailto})"
        return agent
