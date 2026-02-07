# Robotheus

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![Tests](https://github.com/thepetk/robotheus/actions/workflows/ci.yaml/badge.svg)](https://github.com/thepetk/robotheus/actions/workflows/ci.yaml)
[![Release](https://img.shields.io/github/v/release/thepetk/robotheus)](https://github.com/thepetk/robotheus/releases/latest)

Multi-provider AI Prometheus exporter. Collects usage and cost metrics from AI providers and exposes them in Prometheus format.

Currently supported providers:

- **OpenAI** — token usage, request counts, and cost data via the Organization API

## Metrics

All metrics are Prometheus counters.

### OpenAI

| Metric                            | Labels                               | Description                                   |
| --------------------------------- | ------------------------------------ | --------------------------------------------- |
| `robotheus_openai_requests_total` | `model, project, api_key`            | Total API requests                            |
| `robotheus_openai_tokens_total`   | `model, project, api_key, direction` | Total tokens (direction: `input` or `output`) |
| `robotheus_openai_cost_usd_total` | `project`                            | Total cost in USD                             |

## Quickstart

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

### Run locally

```bash
export OPENAI_API_KEY="sk-..."
uv run robotheus
```

### CLI flags

| Flag                   | Default | Description                                     |
| ---------------------- | ------- | ----------------------------------------------- |
| `--web.listen-address` | `:9185` | Listen address                                  |
| `--scrape.interval`    | `60`    | Collection interval in seconds                  |
| `--log.level`          | `info`  | Log level (`debug`, `info`, `warning`, `error`) |

### Environment variables

| Variable         | Required | Description            |
| ---------------- | -------- | ---------------------- |
| `OPENAI_API_KEY` | Yes      | OpenAI API key         |
| `OPENAI_ORG_ID`  | No       | OpenAI Organization ID |

### Docker

```bash
docker run -e OPENAI_API_KEY="sk-..." -p 9185:9185 ghcr.io/thepetk/robotheus:latest
```

## Development

```bash
# install dependencies
uv sync --all-extras

# run tests
make test

# run linter
make ruff

# run type checker
make ty

# install pre-commit hooks
make pre-commit-install
```

## Contributing

You're more than welcome to contribute to the project. Feel free to open a PR!
