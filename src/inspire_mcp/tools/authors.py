from __future__ import annotations

from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from inspire_mcp.identifiers import (
    endpoint_for_identifier,
    normalize_identifier,
    query_for_identifier,
)
from inspire_mcp.models import (
    AuthorIdentifierType,
    DetailLevel,
    RecordResult,
    SearchResult,
)
from inspire_mcp.projections import canonical_recid, project_author, source_url
from inspire_mcp.registry import AUTHORS
from inspire_mcp.runtime import AppContext
from inspire_mcp.tools.common import search_envelope


async def _get_author_record(
    ctx: Context[AppContext],
    identifier: str,
    identifier_type: AuthorIdentifierType,
    detail: DetailLevel | None = None,
) -> tuple[dict[str, Any], str]:
    resolved = normalize_identifier(identifier, identifier_type)
    if resolved.kind not in {"recid", "orcid"}:
        raise ValueError("Author records can be read only by recid or ORCID.")
    client = ctx.request_context.lifespan_context.client
    if detail in {"compact", "standard"}:
        record = await client.find_record(
            "authors",
            query_for_identifier("authors", resolved),
            fields=AUTHORS.fields_for(detail),
        )
    else:
        endpoint = endpoint_for_identifier("authors", resolved)
        record = await client.get_record(endpoint, resolved.value)
    return record, resolved.value


def register_author_tools(mcp: MCPServer) -> None:
    annotations = ToolAnnotations(read_only_hint=True, open_world_hint=True)

    @mcp.tool(title="Search INSPIRE authors", annotations=annotations)
    async def search_authors(
        query: Annotated[
            str,
            Field(
                min_length=1,
                description=(
                    "ElasticSearch query such as 'ids.value:INSPIRE-00140145' "
                    "or 'name.value:Hawking'."
                ),
            ),
        ],
        ctx: Context[AppContext],
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=1, le=50)] = 10,
        detail: DetailLevel = "compact",
    ) -> SearchResult:
        """Search public INSPIRE author records; email addresses are always excluded."""
        if detail == "detailed" and page_size > 10:
            raise ValueError("Detailed author searches are limited to 10 results per page.")
        client = ctx.request_context.lifespan_context.client
        payload = await client.search_records(
            "authors",
            query,
            page=page,
            size=page_size,
            fields=AUTHORS.fields_for(detail),
        )
        records, total, next_url, self_url = search_envelope(payload)
        items = [project_author(record, detail, include_email=False)[0] for record in records]
        return SearchResult(
            record_type="authors",
            detail=detail,
            query=query,
            total=total,
            page=page,
            page_size=page_size,
            items=items,
            next_url=next_url,
            source_url=self_url,
        )

    @mcp.tool(title="Get an INSPIRE author record", annotations=annotations)
    async def get_author(
        identifier: Annotated[str, Field(description="INSPIRE author recid or ORCID.")],
        ctx: Context[AppContext],
        identifier_type: AuthorIdentifierType = "auto",
        detail: DetailLevel = "standard",
        include_email: bool = False,
    ) -> RecordResult:
        """Read one author record, with explicit opt-in for public email addresses."""
        if include_email and detail != "detailed":
            raise ValueError("include_email requires detail='detailed'.")
        record, requested = await _get_author_record(ctx, identifier, identifier_type, detail)
        data, truncated = project_author(record, detail, include_email=include_email)
        recid = canonical_recid(record)
        return RecordResult(
            record_type="authors",
            detail=detail,
            canonical_id=f"authors:{recid}",
            requested_identifier=requested,
            updated=str(record["updated"]) if record.get("updated") else None,
            data=data,
            truncated_fields=truncated,
            source_url=source_url(record, "authors"),
        )
