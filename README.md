# inspire-mcp-more

An extensible Model Context Protocol server for the public
[INSPIRE REST API](https://github.com/inspirehep/rest-api-doc).

It provides structured tools for literature, authors, DOI/arXiv/ORCID resolution,
citation export, and the INSPIRE bibliography generator. Responses offer bounded detail
levels so an MCP client can trade metadata completeness for model context size.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)

## Install

Install globally from a checkout:

```bash
uv tool install .
```

Install from Git:

```bash
uv tool install git+https://github.com/karuboniru/inspire-mcp
```

Run without a persistent install:

```bash
uvx --from git+https://github.com/karuboniru/inspire-mcp inspire-mcp
```

## Run

The default transport is stdio:

```bash
inspire-mcp
```

For a local Streamable HTTP endpoint:

```bash
inspire-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

The endpoint is `http://127.0.0.1:8000/mcp` by default. Binding to a non-loopback
address requires `--allow-public-http`; production deployments should add authentication
and TLS in front of the server.

Example MCP host configuration:

```json
{
  "mcpServers": {
    "inspire": {
      "command": "inspire-mcp"
    }
  }
}
```

## Tools

| Tool | Purpose |
| --- | --- |
| `search_literature` | Search literature with INSPIRE query syntax |
| `get_literature` | Read a paper by recid, DOI, or arXiv ID |
| `list_literature_authors` | Page through embedded paper authors |
| `list_literature_references` | Page through a paper's references |
| `export_literature` | Export BibTeX, LaTeX, or CV HTML |
| `search_authors` | Search public author records |
| `get_author` | Read an author by recid or ORCID |
| `resolve_external_identifier` | Resolve DOI, arXiv, or ORCID to an INSPIRE recid |
| `generate_bibliography` | Generate a bibliography from TeX citation commands |

The `inspire://capabilities` resource describes supported values and limits.

## Detail levels

- `compact`: identity and discovery fields, optimized for model context.
- `standard`: research-oriented metadata with bounded author arrays.
- `detailed`: broad public metadata with explicit `truncated_fields` markers.

Large arrays are never byte-truncated. Use `list_literature_authors` and
`list_literature_references` to retrieve them in pages.

Author searches never expose email addresses. A single author record requires both
`detail="detailed"` and `include_email=true` before public email fields are included.

## Configuration

| Environment variable | Default |
| --- | --- |
| `INSPIRE_API_BASE_URL` | `https://inspirehep.net/api/` |
| `INSPIRE_TIMEOUT_SECONDS` | `30` |
| `INSPIRE_CONNECT_TIMEOUT_SECONDS` | `5` |
| `INSPIRE_RATE_LIMIT_REQUESTS` | `12` |
| `INSPIRE_RATE_LIMIT_WINDOW_SECONDS` | `5` |
| `INSPIRE_MAX_RETRIES` | `2` |
| `INSPIRE_MAX_TEX_BYTES` | `1000000` |
| `INSPIRE_MAX_EXPORT_CHARACTERS` | `1000000` |
| `INSPIRE_CACHE_TTL_SECONDS` | `300` |
| `INSPIRE_CACHE_MAX_ENTRIES` | `256` |
| `INSPIRE_DOWNLOAD_HOSTS` | `inspirehep.net,s3.cern.ch` |
| `INSPIRE_MCP_LOG_LEVEL` | `INFO` |

INSPIRE documents an upstream limit of 15 requests per 5 seconds per IP. This server
uses a lower default to preserve headroom and retries HTTP 429 responses conservatively.

Successful GET, search, and export responses are cached in each server process. Concurrent
identical requests share one upstream request. Set `INSPIRE_CACHE_TTL_SECONDS=0` to disable
the cache. Multi-process deployments maintain one independent cache per worker.

Generated bibliography content is currently served by INSPIRE through CERN object storage.
The default download allowlist therefore contains both `inspirehep.net` and the exact host
`s3.cern.ch`; arbitrary external download hosts remain blocked.

## Development

```bash
uv sync --all-groups
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

The default tests use mocked HTTP responses. Live INSPIRE POST requests are not performed
by the test suite.

## INSPIRE terms

Use of the upstream API is governed by the
[INSPIRE terms of use](https://inspirehep.net/help/knowledge-base/terms-of-use/).
Bulk collection of email addresses is not allowed.
