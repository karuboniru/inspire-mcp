from __future__ import annotations

import asyncio
from typing import Any

import httpx2
import pytest

from inspire_mcp.client import InspireClient
from inspire_mcp.config import Settings
from inspire_mcp.errors import InspireResponseError


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "api_base_url": "https://inspire.test/api/",
        "rate_limit_requests": 100,
        "rate_limit_window_seconds": 0.01,
        "max_retries": 1,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.anyio
async def test_search_encodes_fields_and_sort() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/api/literature"
        assert request.url.params["q"] == "topcite 1000+"
        assert request.url.params["fields"] == "titles,authors.full_name"
        assert request.url.params["sort"] == "mostcited"
        return httpx2.Response(200, json={"hits": {"hits": [], "total": 0}, "links": {}})

    async with InspireClient(_settings(), transport=httpx2.MockTransport(handler)) as client:
        payload = await client.search_records(
            "literature",
            "topcite 1000+",
            page=1,
            size=10,
            fields=["titles", "authors.full_name"],
            sort="mostcited",
        )
    assert payload["hits"]["total"] == 0


@pytest.mark.anyio
async def test_rate_limit_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx2.Response(429)
        return httpx2.Response(200, json={"metadata": {"control_number": 1}})

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("inspire_mcp.client.asyncio.sleep", no_sleep)
    async with InspireClient(_settings(), transport=httpx2.MockTransport(handler)) as client:
        record = await client.get_record("literature", "1")
    assert calls == 2
    assert record["metadata"]["control_number"] == 1


@pytest.mark.anyio
async def test_read_timeout_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        raise httpx2.ReadTimeout("slow upstream", request=request)

    async with InspireClient(_settings(), transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(InspireResponseError, match="did not respond within"):
            await client.get_record("literature", "1")
    assert calls == 1


@pytest.mark.anyio
async def test_identical_gets_share_cached_response() -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(200, json={"metadata": {"control_number": 1}})

    async with InspireClient(_settings(), transport=httpx2.MockTransport(handler)) as client:
        first, second = await asyncio.gather(
            client.get_record("literature", "1"),
            client.get_record("literature", "1"),
        )
        third = await client.get_record("literature", "1")
    assert calls == 1
    assert first == second == third


@pytest.mark.anyio
async def test_bibliography_uses_multipart_and_downloads_content() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/api/bibliography-generator":
            assert request.url.params["format"] == "bibtex"
            assert "multipart/form-data" in request.headers["Content-Type"]
            assert b"Maldacena:1997re" in request.content
            return httpx2.Response(
                200,
                json={
                    "data": {
                        "download_url": "https://inspire.test/generated/output.bib",
                        "errors": [],
                    }
                },
            )
        assert request.url.path == "/generated/output.bib"
        return httpx2.Response(
            200,
            text="@article{Maldacena:1997re}",
            headers={"Content-Type": "application/x-bibtex"},
        )

    async with InspireClient(_settings(), transport=httpx2.MockTransport(handler)) as client:
        payload = await client.generate_bibliography(r"\\cite{Maldacena:1997re}", "bibtex")
        result = await client.download_generated_file(payload["data"]["download_url"])
    assert result.content.startswith("@article")


@pytest.mark.anyio
async def test_cern_s3_is_an_allowed_bibliography_host() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "s3.cern.ch"
        return httpx2.Response(200, text="@article{Example}")

    async with InspireClient(_settings(), transport=httpx2.MockTransport(handler)) as client:
        result = await client.download_generated_file(
            "https://s3.cern.ch/inspire-bibliography/output.bib"
        )
    assert result.content == "@article{Example}"


@pytest.mark.anyio
async def test_untrusted_bibliography_host_is_rejected() -> None:
    async with InspireClient(
        _settings(), transport=httpx2.MockTransport(lambda _request: httpx2.Response(200))
    ) as client:
        with pytest.raises(InspireResponseError, match="unexpected download host"):
            await client.download_generated_file("https://example.com/output.bib")
