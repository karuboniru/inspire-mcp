from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from inspire_mcp.models import BibliographyResult
from inspire_mcp.runtime import AppContext


def register_bibliography_tools(mcp: MCPServer) -> None:
    annotations = ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    )

    @mcp.tool(title="Generate a bibliography from TeX", annotations=annotations)
    async def generate_bibliography(
        tex_source: Annotated[
            str,
            Field(
                min_length=1,
                description="TeX source containing \\cite{...} commands understood by INSPIRE.",
            ),
        ],
        ctx: Context[AppContext],
        format: Literal["bibtex", "latex_eu", "latex_us"] = "bibtex",
        detail: Literal["link", "content", "diagnostic"] = "content",
    ) -> BibliographyResult:
        """Generate BibTeX or formatted LaTeX bibliography content from TeX citations."""
        runtime = ctx.request_context.lifespan_context
        if len(tex_source.encode("utf-8")) > runtime.settings.max_tex_bytes:
            raise ValueError(f"TeX input exceeds the {runtime.settings.max_tex_bytes}-byte limit.")
        payload = await runtime.client.generate_bibliography(tex_source, format)
        data = payload.get("data", {})
        if not isinstance(data, dict):
            raise ValueError("INSPIRE returned an invalid bibliography response.")
        errors_value = data.get("errors", [])
        errors: list[Any] = errors_value if isinstance(errors_value, list) else [errors_value]
        download_url = str(data["download_url"]) if data.get("download_url") else None
        if detail == "link" or not download_url:
            return BibliographyResult(
                format=format,
                detail=detail,
                errors=errors,
                download_url=download_url,
                upstream_data=data if detail == "diagnostic" else None,
            )
        response = await runtime.client.download_generated_file(download_url)
        max_chars = runtime.settings.max_export_characters
        truncated = len(response.content) > max_chars
        return BibliographyResult(
            format=format,
            detail=detail,
            errors=errors,
            download_url=download_url if detail == "diagnostic" else None,
            content=response.content[:max_chars],
            content_type=response.content_type if detail == "diagnostic" else None,
            truncated=truncated,
            upstream_data=data if detail == "diagnostic" else None,
        )
