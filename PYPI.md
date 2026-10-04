# Research Scout

Research Scout is a local command-line tool that finds new research papers and a few high-quality blogs based on your preferences. Each run plans searches with Llama 3 through [Ollama](https://ollama.com), scores relevancy with [Jev](https://typesafe.ai), and appends the matches to a CSV file.

The package does not include Ollama or any API keys. Those stay on your machine.

## Release
Version 1.0.1

## Requirements

- Python 3.11 or newer
- [Ollama](https://ollama.com) running locally, with `llama3:latest` pulled
- A Jev API key, for relevancy scoring
- A Brave Search API key, for open-web papers and blogs

OpenAlex, arXiv, and the public Semantic Scholar API are used without a key.

## Install

```bash
pip install research-scout
```

`pip install research_scout` installs the same package.

## Configure

Run the command once to create the config file:

```bash
research-scout init
```

This writes `~/.config/research-scout/config.env`. Open that file and set:

- `JEV_API_KEY`
- `BRAVE_SEARCH_API_KEY`
- `OLLAMA_HOST` and `OLLAMA_MODEL`, if Ollama is not at `http://127.0.0.1:11434` with `llama3:latest`

Pull the model once:

```bash
ollama pull llama3:latest
```

If you run `research-scout` before any configuration exists, it stops and tells you to run `research-scout init` first. Configuration means any one of these:

- `research-scout init` has been run
- a `.env` file is in the directory where you run the command
- the settings are already exported in the shell

Settings are read in this order. Later sources win:

1. `~/.config/research-scout/config.env`
2. `.env` in the current directory
3. Variables exported in the shell

`SCORER` defaults to `jev`. Set `SCORER=llama` to score just with the local Ollama model instead.

## Run

```bash
research-scout
```

The first run asks for a username and a profile: domain, research interests, goals, and key skills. A username is 1–32 letters, numbers, underscores, or hyphens. The profile is stored in `data/users.csv` in the directory where you ran the command. Later runs reuse that profile and do not let you edit it.

Matches are appended to `results/<username>.csv` in that same directory. `DATA_DIR` and `RESULTS_DIR` default to `data` and `results`. Set either one to an absolute path if you want the files somewhere else.

An installed copy writes only those two locations. It does not create log or metrics files.

## Source Code  

Source code for **Research Scout** can be found [here](https://github.com/Gizmosoft/research-scout).
