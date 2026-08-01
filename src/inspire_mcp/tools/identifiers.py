from __future__ import annotations

from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from inspire_mcp.identifiers import normalize_identifier, query_for_identifier
from inspire_mcp.models import DetailLevel, ExternalIdentifierType, IdentifierResolutionResult
from inspire_mcp.projections import (
    canonical_recid,
    project_author,
    project_literature,
    source_url,
)
from inspire_mcp.registry import AUTHORS, LITERATURE
from inspire_mcp.runtime import AppContext
from inspire_mcp.tools.common import identity_data


def register_identifier_tools(mcp: MCPServer) -> None:
    annotations = ToolAnnotations(read_only_hint=True, open_world_hint=True)

    @mcp.tool(title="Resolve an INSPIRE external identifier", annotations=annotations)
    async def resolve_external_identifier(
        identifier: Annotated[
            str, Field(description="DOI, arXiv ID, ORCID, or the corresponding URL.")
        ],
        ctx: Context[AppContext],
        identifier_type: ExternalIdentifierType = "auto",
        detail: Literal["identity", "summary", "record"] = "identity",
    ) -> IdentifierResolutionResult:
        """Resolve DOI, arXiv, or ORCID to a canonical INSPIRE record identity."""
        resolved = normalize_identifier(identifier, identifier_type)
        if resolved.kind == "recid":
            raise ValueError("This tool resolves external identifiers, not numeric recids.")
        record_type = "authors" if resolved.kind == "orcid" else "literature"
        if detail == "identity":
            fields = (
                [
                    "control_number",
                    "dois",
                    "arxiv_eprints",
                    "texkeys",
                    "report_numbers",
                    "external_system_identifiers",
                ]
                if record_type == "literature"
                else ["control_number", "ids"]
            )
        elif record_type == "literature":
            fields = LITERATURE.fields_for("compact" if detail == "summary" else "standard")
        else:
            fields = AUTHORS.fields_for("compact" if detail == "summary" else "standard")
        record = await ctx.request_context.lifespan_context.client.find_record(
            record_type,
            query_for_identifier(record_type, resolved),
            fields=fields,
        )
        if detail == "identity":
            data = identity_data(record, record_type)
        elif record_type == "literature":
            projection: DetailLevel = "compact" if detail == "summary" else "standard"
            data = project_literature(record, projection)[0]
        else:
            projection = "compact" if detail == "summary" else "standard"
            data = project_author(record, projection, include_email=False)[0]
        return IdentifierResolutionResult(
            identifier_type=resolved.kind,
            normalized_identifier=resolved.value,
            record_type=record_type,
            canonical_id=f"{record_type}:{canonical_recid(record)}",
            detail=detail,
            data=data,
            source_url=source_url(record, record_type),
        )
