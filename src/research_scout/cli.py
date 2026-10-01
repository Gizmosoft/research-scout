import sys

from rich.console import Console
from rich.table import Table

from research_scout.agents.jev_scorer import JevScorer
from research_scout.agents.query import QueryAgent
from research_scout.agents.relevancy import LlamaScorer
from research_scout.config import Settings
from research_scout.orchestrator import Orchestrator
from research_scout.telemetry.jev_client import JevClient
from research_scout.telemetry.logging import log, new_run_id, setup_logging
from research_scout.telemetry.metrics import RunMetrics, write_metrics
from research_scout.telemetry.ollama_client import OllamaClient
from research_scout.workers.intake import IntakeWorker
from research_scout.workers.retrieval import RetrievalWorker
from research_scout.workers.writer import Writer

BANNER = """
+----------------------------------------------+
|              RESEARCH SCOUT                  |
|     find papers and blogs in one run         |
+----------------------------------------------+
"""


def main() -> None:
    settings = Settings()
    settings.ensure_dirs()
    run_id = new_run_id()
    log_path = settings.logs_dir / f"session-{run_id}.log"
    metrics_path = settings.metrics_dir / f"run-{run_id}.json"
    setup_logging(log_path)
    console = Console()
    console.print(BANNER)
    use_jev = settings.scorer == "jev"
    metrics = RunMetrics(
        run_id=run_id,
        model=settings.jev_model if use_jev else settings.ollama_model,
        provider="jev" if use_jev else "ollama",
        query_model=settings.ollama_model,
        prompt_cost_per_million=settings.cost_per_million_prompt_tokens,
        completion_cost_per_million=settings.cost_per_million_completion_tokens,
        scorer_provider="jev" if use_jev else "ollama",
        scorer_requested_model=settings.jev_model if use_jev else settings.ollama_model,
        scorer_base_url=settings.jev_base_url if use_jev else "",
        scorer_input_cost_per_million=settings.jev_cost_per_million_input_tokens,
        scorer_output_cost_per_million=settings.jev_cost_per_million_output_tokens,
    )
    llm = OllamaClient(settings.ollama_host, settings.ollama_model, metrics)
    retrieval = RetrievalWorker(settings, metrics)
    jev = None
    try:
        if not llm.ready():
            log.info("startup failed reason=ollama_or_model")
            console.print(
                f"Ollama is not reachable at {settings.ollama_host}, "
                f"or {settings.ollama_model} is not installed."
            )
            write_metrics(metrics_path, metrics)
            raise SystemExit(1)
        if use_jev:
            jev = JevClient(settings, metrics)
            if not jev.ready():
                log.info(
                    "startup failed reason=jev base_url=%s model=%s",
                    settings.jev_base_url,
                    settings.jev_model,
                )
                console.print(
                    f"Jev is not reachable at {settings.jev_base_url}, "
                    "or JEV_API_KEY is missing or rejected."
                )
                write_metrics(metrics_path, metrics)
                raise SystemExit(1)
            scorer = JevScorer(jev)
        else:
            scorer = LlamaScorer(llm)
        intake = IntakeWorker(settings)
        writer = Writer(settings)
        query_agent = QueryAgent(llm)
        log.info("spawn worker=intake")
        log.info("spawn worker=retrieval sources=openalex,arxiv,semantic_scholar,web")
        log.info("spawn agent=query model=%s", settings.ollama_model)
        if use_jev:
            log.info(
                "spawn agent=relevancy provider=jev model=%s base_url=%s",
                settings.jev_model,
                settings.jev_base_url,
            )
        else:
            log.info("spawn agent=relevancy provider=ollama model=%s", settings.ollama_model)
        log.info("spawn worker=writer")
        orchestrator = Orchestrator(
            settings,
            query_agent,
            retrieval,
            scorer,
            writer,
            metrics,
            log_path,
            metrics_path,
        )
        profile = intake.run()
        with console.status("Planning searches", spinner="dots") as status:
            result = orchestrator.run(profile, on_status=status.update)
    except SystemExit:
        raise
    except Exception:
        console.print(f"Run failed. See {log_path}")
        raise SystemExit(1) from None
    finally:
        retrieval.close()
        if jev is not None:
            jev.close()

    table = Table(title="Run complete")
    table.add_column("Result")
    table.add_column("Value")
    rows = [
        ("Papers written", str(result.papers_written)),
        ("Blogs written", str(result.blogs_written)),
        ("Blogs rejected", str(result.blogs_rejected)),
        ("Duplicates skipped", str(result.duplicates_skipped)),
        ("Paper shortfall", str(result.papers_shortfall)),
        ("Results", str(result.results_path)),
        ("Log", str(result.log_path)),
        ("Metrics", str(result.metrics_path)),
    ]
    for label, value in rows:
        table.add_row(label, value)
    console.print(table)


if __name__ == "__main__":
    sys.exit(main())
