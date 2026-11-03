from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings

from inspire_mcp import __version__
from inspire_mcp.auth import OIDCTokenVerifier
from inspire_mcp.client import InspireClient
from inspire_mcp.config import Settings
from inspire_mcp.runtime import AppContext
from inspire_mcp.tools.authors import register_author_tools
from inspire_mcp.tools.bibliography import register_bibliography_tools
from inspire_mcp.tools.identifiers import register_identifier_tools
from inspire_mcp.tools.literature import register_literature_tools


@asynccontextmanager
async def app_lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
    settings = Settings.from_env()
    async with InspireClient(settings) as client:
        yield AppContext(client=client, settings=settings)


settings = Settings.from_env()
mcp = MCPServer(
    "INSPIRE HEP",
    version=__version__,
    instructions=(
        "Search and read INSPIRE literature and author records, resolve DOI/arXiv/ORCID "
        "identifiers, export citations, and generate bibliographies. Prefer compact detail for "
        "discovery and request larger detail only when needed."
    ),
    lifespan=app_lifespan,
    log_level=settings.log_level,
    auth=(
        AuthSettings.model_validate(
            {"issuer_url": settings.oidc_issuer, "resource_server_url": settings.public_url}
        )
        if settings.oidc_issuer is not None
        else None
    ),
    token_verifier=(
        OIDCTokenVerifier(settings.oidc_issuer, settings.public_url)
        if settings.oidc_issuer is not None and settings.public_url is not None
        else None
    ),
)

register_literature_tools(mcp)
register_author_tools(mcp)
register_identifier_tools(mcp)
register_bibliography_tools(mcp)


@mcp.resource("inspire://capabilities", title="INSPIRE MCP capabilities")
def capabilities() -> str:
    """Describe supported records, identifiers, formats, and detail levels."""
    return json.dumps(
        {
            "record_types": ["literature", "authors"],
            "external_identifiers": ["doi", "arxiv", "orcid"],
            "literature_search_sorts": ["default", "mostrecent", "mostcited"],
            "literature_export_formats": ["bibtex", "latex-eu", "latex-us", "cv"],
            "bibliography_formats": ["bibtex", "latex_eu", "latex_us"],
            "detail_levels": {
                "compact": "Token-efficient identity and discovery fields.",
                "standard": "Research-oriented metadata with bounded arrays.",
                "detailed": "Broad public metadata with explicit truncation markers.",
            },
            "privacy": (
                "Author searches omit email addresses. Single-author email access requires "
                "detail='detailed' and include_email=true."
            ),
            "limits": {
                "upstream": "INSPIRE allows 15 requests per 5 seconds per IP.",
                "server": "This server defaults to 12 requests per 5 seconds.",
            },
        },
        ensure_ascii=True,
        indent=2,
    )


if __name__ == "__main__":
    mcp.run()
