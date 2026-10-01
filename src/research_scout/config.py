from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

TIMEOUT_SECONDS = 20.0
MAX_RETRIES = 2
FETCH_BYTE_CAP = 500_000
CANDIDATE_MULTIPLIER = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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
        for path in (self.data_dir, self.results_dir, self.logs_dir, self.metrics_dir):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def user_agent(self) -> str:
        agent = "ResearchScout/0.1"
        if self.openalex_mailto:
            return f"{agent} (mailto:{self.openalex_mailto})"
        return agent
