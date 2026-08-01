from __future__ import annotations

from typing import Any

import pytest
from mcp import Client

from inspire_mcp.client import InspireClient
from inspire_mcp.server import mcp


@pytest.mark.anyio
async def test_server_advertises_expected_tools() -> None:
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.list_tools()
    names = {tool.name for tool in result.tools}
    assert names == {
        "search_literature",
        "get_literature",
        "list_literature_authors",
        "list_literature_references",
        "export_literature",
        "search_authors",
        "get_author",
        "resolve_external_identifier",
        "generate_bibliography",
    }


@pytest.mark.anyio
async def test_get_literature_returns_structured_content(
    monkeypatch: pytest.MonkeyPatch, literature_record: dict[str, Any]
) -> None:
    async def fake_find_record(
        _self: InspireClient, _record_type: str, _query: str, *, fields: list[str]
    ) -> dict[str, Any]:
        assert fields
        return literature_record

    monkeypatch.setattr(InspireClient, "find_record", fake_find_record)
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "get_literature",
            {"identifier": "451647", "detail": "compact"},
        )
    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["canonical_id"] == "literature:451647"
    assert result.structured_content["data"]["authors_total"] == 150
