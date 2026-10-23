# topdeskpy

The original `Topdeskclient` is available on the
[`codex/legacy-v0.1` branch](https://github.com/brkit/topdeskpy/tree/codex/legacy-v0.1).

A Python 3.15 client for selected TOPdesk General, Incident, Knowledge Base, and
Asset Management APIs. Uses [HTTPX2](https://github.com/pydantic/httpx2).

## Getting started

```shell
uv sync --locked
```

Copy `.env.example` to `.env` and set the installation URL, operator username,
and application password.

Only run the [examples.py](examples.py) if using a test intance, since some examples write to Topdesk.

Open [examples.py](examples.py) in VS Code with the Python and Jupyter extensions.
Select `.venv` as the kernel, run the setup cell, then use **Run Cell** for the
examples you need. Write examples create records and archive or delete them
when finished.

## Client

`TopdeskClient` exposes `general`, `incidents`, `knowledge_base`, and `assets`.
Methods return dictionaries with TOPdesk field names. `list()` returns one page;
`iter()` reads all pages. Use a context manager or call `close()` when finished.

- Pass the installation origin or its `/tas/api` URL and an application password.
  TLS verification is enabled; the default request timeout is 30 seconds.
- Knowledge Base defaults to `knowledge_base_mode="folders"`. Use `"legacy"`
  for installations that have not migrated, including the test instance.
- Asset fields depend on the template. Include the current `@etag` when updating.
  HTTP 202 emits `PartialUpdateWarning` for ignored fields. Inspect each bulk
  deletion outcome; HTTP success does not mean every asset was deleted.
- HTTP errors raise `APIError`; network errors remain HTTPX2 exceptions.

## Development

```shell
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv build
```

Run the real API tests against the configured test instance:

```shell
uv run pytest --live --live-host <your-test-instance> --cov=topdeskpy --cov=examples
```

Tests are skipped without `--live`. Branch coverage is enabled by default.
The test account cannot permanently delete assets, so cleanup archives them.
Successful folder-mode writes and some response formats remain unverified.

## API documentation

[General](https://developers.topdesk.com/explorer/?page=general) ·
[Incidents](https://developers.topdesk.com/explorer/?page=incident) ·
[Knowledge Base](https://developers.topdesk.com/explorer/?page=knowledge-base) ·
[Assets](https://developers.topdesk.com/explorer/?page=assets)
