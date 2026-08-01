from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

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
    CollectionPageResult,
    DetailLevel,
    ExportResult,
    LiteratureIdentifierType,
    RecordResult,
    SearchResult,
)
from inspire_mcp.projections import (
    canonical_recid,
    project_embedded_author,
    project_literature,
    project_reference,
    source_url,
)
from inspire_mcp.registry import LITERATURE
from inspire_mcp.runtime import AppContext
from inspire_mcp.tools.common import search_envelope

Page = Annotated[int, Field(ge=1, description="One-based result page.")]
PageSize = Annotated[int, Field(ge=1, le=50, description="Results per page.")]
Offset = Annotated[int, Field(ge=0, description="Zero-based collection offset.")]
CollectionLimit = Annotated[int, Field(ge=1, le=100, description="Items to return.")]


async def _get_literature_record(
    ctx: Context[AppContext],
    identifier: str,
    identifier_type: LiteratureIdentifierType,
    detail: DetailLevel | None = None,
    fields: list[str] | None = None,
) -> tuple[dict[str, Any], str]:
    resolved = normalize_identifier(identifier, identifier_type)
    if resolved.kind == "orcid":
        raise ValueError("ORCID identifies an author, not a literature record.")
    client = ctx.request_context.lifespan_context.client
    if fields is not None:
        record = await client.find_record(
            "literature",
            query_for_identifier("literature", resolved),
            fields=fields,
        )
    elif detail in {"compact", "standard"}:
        record = await client.find_record(
            "literature",
            query_for_identifier("literature", resolved),
            fields=LITERATURE.fields_for(detail),
        )
    else:
        endpoint = endpoint_for_identifier("literature", resolved)
        record = await client.get_record(endpoint, resolved.value)
    return record, resolved.value


def register_literature_tools(mcp: MCPServer) -> None:
    annotations = ToolAnnotations(read_only_hint=True, open_world_hint=True)

    @mcp.tool(title="Search INSPIRE literature", annotations=annotations)
    async def search_literature(
        query: Annotated[
            str,
            Field(
                min_length=1,
                description=(
                    "INSPIRE query such as 'a E.Witten.1', 'topcite 1000+', or 'dois.value:*'."
                ),
            ),
        ],
        ctx: Context[AppContext],
        sort: Literal["default", "mostrecent", "mostcited"] = "default",
        page: Page = 1,
        page_size: PageSize = 10,
        detail: DetailLevel = "compact",
    ) -> SearchResult:
        """Search INSPIRE literature with bounded, model-oriented result detail."""
        if detail == "detailed" and page_size > 5:
            raise ValueError("Detailed literature searches are limited to 5 results per page.")
        client = ctx.request_context.lifespan_context.client
        payload = await client.search_records(
            "literature",
            query,
            page=page,
            size=page_size,
            fields=LITERATURE.fields_for(detail),
            sort=None if sort == "default" else sort,
        )
        records, total, next_url, self_url = search_envelope(payload)
        items = [project_literature(record, detail)[0] for record in records]
        return SearchResult(
            record_type="literature",
            detail=detail,
            query=query,
            total=total,
            page=page,
            page_size=page_size,
            items=items,
            next_url=next_url,
            source_url=self_url,
        )

    @mcp.tool(title="Get an INSPIRE literature record", annotations=annotations)
    async def get_literature(
        identifier: Annotated[
            str, Field(description="INSPIRE recid, DOI, DOI URL, arXiv ID, or arXiv URL.")
        ],
        ctx: Context[AppContext],
        identifier_type: LiteratureIdentifierType = "auto",
        detail: DetailLevel = "standard",
    ) -> RecordResult:
        """Read one literature record by INSPIRE recid, DOI, or arXiv identifier."""
        record, requested = await _get_literature_record(ctx, identifier, identifier_type, detail)
        data, truncated = project_literature(record, detail)
        recid = canonical_recid(record)
        return RecordResult(
            record_type="literature",
            detail=detail,
            canonical_id=f"literature:{recid}",
            requested_identifier=requested,
            updated=str(record["updated"]) if record.get("updated") else None,
            data=data,
            truncated_fields=truncated,
            source_url=source_url(record, "literature"),
        )

    @mcp.tool(title="List authors embedded in a paper", annotations=annotations)
    async def list_literature_authors(
        identifier: str,
        ctx: Context[AppContext],
        identifier_type: LiteratureIdentifierType = "auto",
        offset: Offset = 0,
        limit: CollectionLimit = 50,
        detail: Literal["names", "affiliations", "identifiers"] = "names",
    ) -> CollectionPageResult:
        """Page through a paper's embedded author list without returning a huge record."""
        author_fields = {
            "names": ["control_number", "authors.full_name"],
            "affiliations": [
                "control_number",
                "authors.full_name",
                "authors.affiliations",
            ],
            "identifiers": [
                "control_number",
                "authors.full_name",
                "authors.record",
                "authors.affiliations",
                "authors.ids",
                "authors.orcid",
            ],
        }
        record, _ = await _get_literature_record(
            ctx,
            identifier,
            identifier_type,
            fields=author_fields[detail],
        )
        metadata = record.get("metadata", {})
        authors = metadata.get("authors", []) if isinstance(metadata, dict) else []
        if not isinstance(authors, list):
            authors = []
        page_items = [
            project_embedded_author(author, detail)
            for author in authors[offset : offset + limit]
            if isinstance(author, dict)
        ]
        return CollectionPageResult(
            collection="literature_authors",
            canonical_id=f"literature:{canonical_recid(record)}",
            detail=detail,
            total=len(authors),
            offset=offset,
            limit=limit,
            items=page_items,
            has_more=offset + limit < len(authors),
            source_url=source_url(record, "literature"),
        )

    @mcp.tool(title="List references from a paper", annotations=annotations)
    async def list_literature_references(
        identifier: str,
        ctx: Context[AppContext],
        identifier_type: LiteratureIdentifierType = "auto",
        offset: Offset = 0,
        limit: Annotated[int, Field(ge=1, le=50)] = 25,
        detail: DetailLevel = "compact",
    ) -> CollectionPageResult:
        """Page through a paper's references with selectable detail."""
        record, _ = await _get_literature_record(
            ctx,
            identifier,
            identifier_type,
            fields=["control_number", "references"],
        )
        metadata = record.get("metadata", {})
        references = metadata.get("references", []) if isinstance(metadata, dict) else []
        if not isinstance(references, list):
            references = []
        page_items = [
            project_reference(reference, detail)
            for reference in references[offset : offset + limit]
            if isinstance(reference, dict)
        ]
        return CollectionPageResult(
            collection="literature_references",
            canonical_id=f"literature:{canonical_recid(record)}",
            detail=detail,
            total=len(references),
            offset=offset,
            limit=limit,
            items=page_items,
            has_more=offset + limit < len(references),
            source_url=source_url(record, "literature"),
        )

    @mcp.tool(title="Export an INSPIRE literature record", annotations=annotations)
    async def export_literature(
        identifier: str,
        ctx: Context[AppContext],
        identifier_type: LiteratureIdentifierType = "auto",
        format: Literal["bibtex", "latex-eu", "latex-us", "cv"] = "bibtex",
        detail: Literal["content", "diagnostic"] = "content",
    ) -> ExportResult:
        """Export one paper in an INSPIRE-supported citation format."""
        resolved = normalize_identifier(identifier, identifier_type)
        if resolved.kind == "orcid":
            raise ValueError("ORCID identifies an author and cannot be exported as literature.")
        endpoint = endpoint_for_identifier("literature", resolved)
        client = ctx.request_context.lifespan_context.client
        export_task = asyncio.create_task(client.export_record(endpoint, resolved.value, format))
        if resolved.kind == "recid":
            response = await export_task
            recid = resolved.value
        else:
            record_task = asyncio.create_task(
                client.find_record(
                    "literature",
                    query_for_identifier("literature", resolved),
                    fields=["control_number"],
                )
            )
            response, record = await asyncio.gather(export_task, record_task)
            recid = canonical_recid(record)
        max_chars = ctx.request_context.lifespan_context.settings.max_export_characters
        truncated = len(response.content) > max_chars
        return ExportResult(
            canonical_id=f"literature:{recid}",
            format=format,
            detail=detail,
            content=response.content[:max_chars],
            content_type=response.content_type if detail == "diagnostic" else None,
            source_url=response.url,
            truncated=truncated,
        )
