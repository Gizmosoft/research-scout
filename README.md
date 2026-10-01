# Research Scout

Local CLI that appends new research papers and a few high-quality blogs for one user on every run. Query planning uses Llama 3 through Ollama. Relevancy scoring uses Jev, TypeSafe's System One model, and returns a calibrated probability plus a rubric label. Set `SCORER=llama` to score with Llama 3 instead.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
ollama pull llama3:latest
```

Set `BRAVE_SEARCH_API_KEY` in `.env` for open-web papers and blogs. Set `JEV_API_KEY` (or `TYPESAFE_API_KEY`) for relevancy scoring. OpenAlex, arXiv, and the public Semantic Scholar API run without a key. Semantic Scholar calls are spaced to stay within the free shared limit.

## Run

From the repo root:

```bash
python -m research_scout
```

or `research-scout`.

The first run asks for a username and profile and stores them in `data/users.csv`. Later runs reuse that profile and append new rows to `results/<username>.csv`. Profiles cannot be edited.

Each run writes `logs/session-<id>.log` and `metrics/run-<id>.json`.
