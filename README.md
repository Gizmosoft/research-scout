# Research Scout

Local CLI that finds new research papers and a few high-quality blogs based on the user preferences on every run. Search planning uses Llama 3 through Ollama. Relevancy scoring uses Jev and returns a score and a short reason.

Ollama and the API keys stay on your machine. The package does not include them.

## Use the installed CLI

```bash
pip install research-scout
```

`pip install research_scout` installs the same package.

If you run `research-scout` before any configuration exists, it stops and tells you to run init. Configuration means one of these:

- `research-scout init` has been run
- a `.env` file is in the directory where you run the command
- the settings are already exported in the shell

Create the config file:

```bash
research-scout init
```

That writes `~/.config/research-scout/config.env`. Edit it and set:

- `JEV_API_KEY` for relevancy scoring
- `BRAVE_SEARCH_API_KEY` for open-web papers and blogs
- `OLLAMA_HOST` and `OLLAMA_MODEL` if Ollama is not on `http://127.0.0.1:11434` with `llama3:latest`

Pull the model once:

```bash
ollama pull llama3:latest
```

Then run:

```bash
research-scout
```

Settings are read in this order. Later sources win:

1. `~/.config/research-scout/config.env`
2. `.env` in the current directory
3. Variables exported in the shell

The first run asks for a username and profile. It stores that profile in `data/users.csv` and writes matches to `results/<username>.csv`. Later runs reuse the profile and append new rows. Profiles cannot be edited.

A PyPI install does not create `logs/` or `metrics/`.

OpenAlex, arXiv, and the public Semantic Scholar API run without a key.

## Build from source

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
ollama pull llama3:latest
```

Set `JEV_API_KEY` and `BRAVE_SEARCH_API_KEY` in `.env`. Set `SCORER=llama` to score with just Llama 3 instead. This checkout is an editable install, so each run also writes:

- `logs/session-<id>.log`
- `metrics/run-<id>.json`

Run the app with `research-scout` or `python -m research_scout`. Run the tests with:

```bash
pytest
```
