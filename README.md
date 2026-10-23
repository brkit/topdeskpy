# topdeskpy

A typed, synchronous Python client for selected TOPdesk operator APIs. Requires
Python 3.11 or later. Uses [HTTPX2](https://github.com/pydantic/httpx2) for connection
pooling, timeouts, Basic authentication, and TLS verification with the operating
system's certificate store.

Version 0.2 replaces the original client. Import `TopdeskClient` and use its
resource APIs; the old `Topdeskclient` interface and installation-specific
incident defaults have been removed.

## Installation

To use this checkout in another project managed with
[uv](https://docs.astral.sh/uv/):

```shell
uv add /path/to/topdeskpy
```

To work from this checkout:

```shell
uv sync --locked
```

Create an operator application password in TOPdesk with permissions for the
resources you need. Pass credentials explicitly. The library does not read
environment files or change the process environment.

The base URL can be the installation origin or its `/tas/api` URL, with or
without a trailing slash. The client uses `/services/knowledge-base-v1` at the
same origin for Knowledge Base requests. It closes connections on context exit;
otherwise, call `client.close()`.

## Examples

The API examples are in [examples.py](examples.py), split into VS Code `# %%`
code cells. Install the Python and Jupyter extensions, select the project
`.venv` as the kernel, and use **Run Cell**. Run the setup cell first; it reads
credentials from `.env` or the `TOPDESK_*` environment variables.

The examples include reads, incident and knowledge-item writes, asset template
discovery and writes, error handling, and connection cleanup. The asset setup
cell fills required dropdown fields from the template's active choices. Review
or change those values before running its write cell. Write examples archive
their records during cleanup when permanent deletion is unavailable.

## Supported operations

This is a starter client, not a wrapper for every TOPdesk endpoint.

| Resource | Operations |
| --- | --- |
| `client.general` | API/product versions, categories and category iteration, archiving/time-spent reasons, service window lookups |
| `client.incidents` | List/iterate, get/update by UUID or number, create, archive/unarchive, add actions, read/iterate action and request history, supported dropdown lookups |
| `client.knowledge_base` | List/iterate/get/create, update metadata and translations, translation creation/deletion, archive/unarchive, folder listing for migrated installations |
| `client.assets` | List/iterate/get, template/blank-card discovery, create/update, archive/unarchive, bulk delete with per-item results |

Methods return dictionaries with the original TOPdesk field names. Responses and
write payloads retain custom installation fields. Use `params={...}` for the
documented query parameters; `list()` returns one page, and `iter()` traverses
pages. Incident/history iterators use their respective offset parameter names;
knowledge items use the `item` envelope, and asset lists use `dataSet`. The
client requests the current v2 asset-list representation.

### Incidents

Reference values, mandatory fields, and permitted actions depend on the
installation and operator. For example, use an existing caller and choose the
appropriate archiving reason. Incident updates accept a field mapping rather
than JSON Patch operations. Incident deletion is not provided by this API.

### Knowledge Base

The two explorer versions use different update verbs and translation payloads.
The default `knowledge_base_mode="folders"` follows the downloaded specification
for the migrated folder explorer. Set `knowledge_base_mode="legacy"` in the
client constructor for installations that still use knowledge items as parents.
Mode selection is explicit and does not depend on the temporary migration-status
endpoint.

Use a language enabled on your installation. Knowledge items can be archived,
but the API does not provide permanent item deletion. Archived items cannot be
updated. `migrated()` exposes the optional migration-status endpoint, documented
as available through December 2026.

### Assets

Asset schemas vary by template. Discover a template with `assets.templates()`
and inspect `assets.blank(template_id)` for fields and mandatory values before
creating an asset.

Include any additional mandatory fields in the create payload. Supply the current
`@etag` for optimistic concurrency checks. A stale value produces HTTP 409.
HTTP 202 means the server ignored unknown asset fields; the client emits
`PartialUpdateWarning`. A successful HTTP response from bulk deletion can still
contain per-item failures, so inspect all four outcome lists.

## Errors and connection options

`APIError` exposes `status_code`, `method`, `path`, `body`, and the original
HTTPX2 `response`. `UnexpectedResponseError` reports invalid JSON or an unexpected
response shape. Network and timeout errors remain HTTPX2 exceptions.

Requests have a 30-second timeout by default. Pass `timeout=...` or an
`httpx2.Timeout` for finer control. Pass `verify=ssl_context` to configure a
private CA. Redirects are not followed, and requests are not automatically
retried, so a timed-out write cannot be silently duplicated. Pagination links
must stay on the configured installation origin.

## Development and live verification

```shell
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv build
```

The tests perform real API round trips, without mocked responses. Copy
`.env.example` to `.env` and set `TOPDESK_BASE_URL`, `TOPDESK_USERNAME`, and
`TOPDESK_PASSWORD`. The legacy `.env` keys `base_url`, `username`, and `password`
are also supported. The example cells and live tests use the same configuration
names.

The integration suite requires explicit opt-in and checks that the configured
HTTPS URL targets the designated test installation:

```shell
uv run pytest --live --live-host testdesk.brkint.dk
```

The suite also executes `examples.py` against the test installation and verifies
that its writes persist and its cleanup archives or deletes each created record.
To measure statement and branch coverage for both the client and the examples:

```shell
uv run pytest --live --live-host testdesk.brkint.dk --cov=topdeskpy --cov=examples --cov-branch --cov-report=term-missing
```

For an HTML report showing uncovered statements and branches, add
`--cov-report=html` and open `htmlcov/index.html`. Branch measurement is also
enabled in `pyproject.toml`, so it remains active when `--cov-branch` is omitted.

The latest run against the designated test installation passed **49 tests**.
For the client package alone, statement coverage is **322/332 (97%)** and branch
coverage is **72/80 (90%)**. The example file is reported separately; combining
its results with the client produces a different percentage.

| Area | Live verification |
| --- | --- |
| General | Versions, categories, reasons, service windows, filters, and missing records |
| Incidents | Every available dropdown, list/history wrappers, complete pagination, initial offsets, empty HTTP 204 responses, UUID/number access and updates, action visibility, archive options, and server validation errors |
| Assets | Required-field discovery, create/update, HTTP 202 partial-save warnings, persisted fields, stale ETags, complete pagination, offsets/seek queries, projection/filtering, archive/unarchive, and per-item deletion outcomes |
| Knowledge Base | Legacy item and translation lifecycle, number/UUID access, partial updates, clearing fields, complete pagination, conflicts, last-translation protection, archived mutation errors, and archive/unarchive idempotency |
| Transport and examples | Actual execution of all example cells, authentication rejection, URL forms, timeouts/TLS configuration, connection cleanup, response-shape checks using real API payloads, and local input rejection within live sessions |

HTTP responses are not mocked or fabricated. Input-validation guards run locally
as designed; their tests also verify valid requests against the instance. Write
tests register their created records for cleanup and verify the archived state.

Some implemented protocols are unavailable on this installation. Their real
error responses are tested, but a rejected request does not prove that the
operation would succeed on another installation:

- Incident caller/operator/group lookup routes return HTTP 404. All ten other
  implemented dropdowns return data.
- The legacy knowledge explorer returns HTTP 404 for folders and HTTP 405 for
  folder-mode PATCH updates. Folder-mode translation creation is interpreted as
  a legacy update and returns `translation_not_found` when no translation exists.
- The account cannot permanently delete assets. Bulk deletion is verified to
  distinguish `unauthorized` records from `missing` IDs. Successful deletion and
  the server's `failed` deletion outcome remain unverified.

Remaining uncovered client branches require malformed/contradictory responses,
repeated category pagination links, or the newer bare-array service-window
response. This instance returns unpaginated categories and a service-window
`results` envelope. Invalid JSON is likewise not produced by the tested APIs.
No coverage exclusions are used to hide these gaps. Coverage measures code
execution, not complete correctness of every TOPdesk behavior.

Without `--live`, these tests are skipped. With it, the suite creates uniquely
named incidents, knowledge items, and assets, verifies reads and writes, and
archives or deletes only its own records in cleanup. Incident and knowledge-item
cleanup leaves archived records because their APIs do not provide permanent
deletion. The supplied test account uses the legacy knowledge explorer and lacks
asset deletion permission; asset cleanup archives records when deletion reports
`unauthorized`. Folder-mode writes require verification on a migrated installation.

## API references

The implementation follows the downloaded specifications in `docs/swagger` and
the official [General](https://developers.topdesk.com/explorer/?page=general),
[Incident](https://developers.topdesk.com/explorer/?page=incident),
[Knowledge Base](https://developers.topdesk.com/explorer/?page=knowledge-base), and
[Asset Management](https://developers.topdesk.com/explorer/?page=assets)
documentation. The legacy Knowledge Base schema is available from TOPdesk's
[pre-migration specification](https://developers.topdesk.com/swagger/knowledge-base_before_explorer_migration.json).
