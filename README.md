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
address requires OIDC authentication (below) or `--allow-public-http`. Production
deployments should terminate TLS at a reverse proxy.

### OIDC authentication for HTTP

To use an existing authorization server that supports CIMD and issues signed JWT
access tokens, set both variables:

```bash
export INSPIRE_MCP_OIDC_ISSUER=https://auth.example.com/realms/example
export INSPIRE_MCP_PUBLIC_URL=https://inspire.example.com/mcp
inspire-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

Use the exact issuer URL (including any path or trailing slash), and the externally
visible MCP endpoint URL. Both must use HTTPS. Configure the identity provider to
issue access tokens with `aud` containing `INSPIRE_MCP_PUBLIC_URL`. Its access
tokens must include `iss`, `aud`, `exp`, and `sub`, and use RS256/384/512 or
ES256/384/512 signatures. Opaque tokens and encrypted JWTs are not supported.

The server discovers the issuer's public signing keys using OIDC discovery and
JWKS, caches them, and verifies tokens. **No JWT secret or private key is needed**:
the identity provider signs tokens; this server only verifies them. Discovery and
JWKS endpoints must be reachable from the server.

Unauthenticated HTTP requests receive a 401 with an OAuth resource metadata URL.
Proxy `/.well-known/oauth-protected-resource` and its subpaths to this service as
well as `/mcp`, preserving the `Authorization` and `WWW-Authenticate` headers.
Clients discover the external authorization server and authenticate there. Enable
CIMD and the appropriate client/resource access policies at that provider; this
server does not implement client registration or an authorization server itself.
Any valid access token for this resource grants access to all tools; there is no
additional per-user or per-scope policy in this minimal integration.

Only leaving both variables unset permits unauthenticated HTTP behavior. The presence
of either variable requires authentication: missing or empty values stop startup,
even with `--allow-public-http`. Stdio does not require tokens or contact the issuer.

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

## Container deployment

Build a minimal runtime image with Podman (Python dependencies are installed by
`uv sync --locked --no-dev --no-editable`):

```bash
podman build -t localhost/inspire-mcp:local .
podman run -d --name inspire-mcp --restart unless-stopped \
  -p 127.0.0.1:8000:8000 localhost/inspire-mcp:local
```

Docker can run the same image. The container defaults to a single process serving
Streamable HTTP on `0.0.0.0:8000/mcp`, as UID/GID 10001. The runtime contains no uv,
source checkout, development dependencies, or build cache. No persistent volume is
required. Pass application configuration using `-e INSPIRE_...=...` as listed below.

Connect your TLS reverse proxy to port 8000 and configure clients with
`https://<your-domain>/mcp`. Enable the OIDC configuration above or use authentication
at the proxy.
The loopback port mapping above is suitable for a proxy on the same host; for a
containerized proxy, put both containers on a private network and proxy to
`http://inspire-mcp:8000/mcp` without publishing the backend port. Preserve streaming
responses (disable proxy buffering) and allow sufficient upstream response time.
Configure allowed public hosts/origins at your proxy, and keep the backend private.

Keep one replica for personal/small-team use: caches and upstream rate limits are
local to each process. Container arguments replace the default command; when
overriding them, include all required HTTP flags:

```bash
podman run --rm -p 127.0.0.1:8001:8001 localhost/inspire-mcp:local \
  --transport streamable-http --host 0.0.0.0 --port 8001 --allow-public-http
```

The container workflow builds and smoke-tests Linux amd64 and arm64 images on native
GitHub runners. Pull requests build only; pushes to `main`, release tags `v*`, and
manual runs publish to `ghcr.io/<owner>/<repository>`. `latest` follows `main`;
`sha-<full-commit-sha>` identifies a commit. Release tags are also published.
After the workflow has published an image, deploy it by replacing
`localhost/inspire-mcp:local` above with your GHCR image reference. Private GHCR
packages require `podman login ghcr.io` before pulling.

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
| `INSPIRE_MCP_OIDC_ISSUER` | Unset (authentication disabled) |
| `INSPIRE_MCP_PUBLIC_URL` | Unset (required with OIDC issuer; also the token audience) |

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
