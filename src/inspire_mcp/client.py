from __future__ import annotations

import asyncio
import json
import logging
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from functools import partial
from time import monotonic
from typing import Any, TypeVar, cast
from urllib.parse import quote, urljoin, urlparse

import httpx2

from inspire_mcp import __version__
from inspire_mcp.config import Settings
from inspire_mcp.errors import (
    InspireNotFoundError,
    InspireRateLimitError,
    InspireResponseError,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = monotonic()
                while self._timestamps and now - self._timestamps[0] >= self._window_seconds:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._max_requests:
                    self._timestamps.append(now)
                    return
                delay = self._window_seconds - (now - self._timestamps[0])
            await asyncio.sleep(max(delay, 0.01))


class AsyncTTLCache:
    def __init__(self, ttl_seconds: float, max_entries: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._values: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._inflight: dict[Hashable, asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, key: Hashable, factory: Callable[[], Awaitable[T]]) -> T:
        if self._ttl_seconds <= 0 or self._max_entries <= 0:
            return await factory()

        async with self._lock:
            now = monotonic()
            cached = self._values.get(key)
            if cached is not None:
                expires_at, value = cached
                if expires_at > now:
                    self._values.move_to_end(key)
                    return cast(T, value)
                del self._values[key]

            task = self._inflight.get(key)
            if task is None:
                task = asyncio.ensure_future(factory())
                self._inflight[key] = task
                task.add_done_callback(partial(self._complete, key))

        return cast(T, await asyncio.shield(task))

    def _complete(self, key: Hashable, task: asyncio.Future[Any]) -> None:
        self._inflight.pop(key, None)
        if task.cancelled() or task.exception() is not None:
            return
        self._values[key] = (monotonic() + self._ttl_seconds, task.result())
        self._values.move_to_end(key)
        while len(self._values) > self._max_entries:
            self._values.popitem(last=False)


@dataclass(frozen=True, slots=True)
class TextResponse:
    content: str
    content_type: str | None
    url: str


class InspireClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: Any | None = None,
    ) -> None:
        self.settings = settings
        self._limiter = SlidingWindowLimiter(
            settings.rate_limit_requests, settings.rate_limit_window_seconds
        )
        self._cache = AsyncTTLCache(settings.cache_ttl_seconds, settings.cache_max_entries)
        self._client = httpx2.AsyncClient(
            base_url=settings.api_base_url,
            timeout=httpx2.Timeout(
                settings.timeout_seconds,
                connect=settings.connect_timeout_seconds,
            ),
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "User-Agent": f"inspire-mcp-more/{__version__}",
            },
            transport=transport,
        )

    async def __aenter__(self) -> InspireClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        response: Any | None = None
        for attempt in range(self.settings.max_retries + 1):
            await self._limiter.acquire()
            try:
                response = await self._client.request(method, url, **kwargs)
            except httpx2.ReadTimeout as exc:
                raise InspireResponseError(
                    0,
                    f"INSPIRE did not respond within {self.settings.timeout_seconds:g} seconds.",
                ) from exc
            except (httpx2.TimeoutException, httpx2.NetworkError) as exc:
                if method != "GET" or attempt >= self.settings.max_retries:
                    raise InspireResponseError(0, f"Could not connect to INSPIRE: {exc}") from exc
                await asyncio.sleep(0.5 * 2**attempt)
                continue

            if response.status_code == 429:
                if attempt >= self.settings.max_retries:
                    raise InspireRateLimitError(
                        "INSPIRE rate limit was exceeded after retrying. Try again later."
                    )
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = max(float(retry_after), 5.0) if retry_after else 5.0
                except ValueError:
                    delay = 5.0
                await asyncio.sleep(delay)
                continue
            if response.status_code in {502, 503, 504} and attempt < self.settings.max_retries:
                await asyncio.sleep(0.5 * 2**attempt)
                continue
            break

        if response is None:
            raise InspireResponseError(0, "INSPIRE returned no response.")
        if response.status_code == 404:
            raise InspireNotFoundError(f"INSPIRE record not found: {response.url}")
        if response.status_code >= 400:
            detail = response.text[:1000]
            try:
                payload = response.json()
                detail = json.dumps(payload, ensure_ascii=False)[:1000]
            except Exception:
                payload = None
            raise InspireResponseError(
                response.status_code,
                f"INSPIRE returned HTTP {response.status_code}: {detail}",
                payload,
            )
        return response

    async def get_record(self, endpoint: str, identifier: str) -> dict[str, Any]:
        async def fetch() -> dict[str, Any]:
            encoded = quote(identifier, safe="/:.")
            response = await self._request("GET", f"{endpoint}/{encoded}")
            return dict(response.json())

        return await self._cache.get_or_create(("record", endpoint, identifier), fetch)

    async def search_records(
        self,
        record_type: str,
        query: str,
        *,
        page: int,
        size: int,
        fields: list[str] | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        async def fetch() -> dict[str, Any]:
            params: dict[str, str | int] = {"q": query, "page": page, "size": size}
            if fields:
                params["fields"] = ",".join(fields)
            if sort:
                params["sort"] = sort
            response = await self._request("GET", record_type, params=params)
            return dict(response.json())

        key = ("search", record_type, query, page, size, tuple(fields or ()), sort)
        return await self._cache.get_or_create(key, fetch)

    async def find_record(
        self, record_type: str, query: str, *, fields: list[str]
    ) -> dict[str, Any]:
        payload = await self.search_records(
            record_type,
            query,
            page=1,
            size=1,
            fields=fields,
        )
        hits_wrapper = payload.get("hits", {})
        hits = hits_wrapper.get("hits", []) if isinstance(hits_wrapper, dict) else []
        if not isinstance(hits, list) or not hits or not isinstance(hits[0], dict):
            raise InspireNotFoundError(f"No {record_type} record matched {query!r}.")
        return hits[0]

    async def export_record(
        self, endpoint: str, identifier: str, export_format: str
    ) -> TextResponse:
        async def fetch() -> TextResponse:
            encoded = quote(identifier, safe="/:.")
            response = await self._request(
                "GET",
                f"{endpoint}/{encoded}",
                params={"format": export_format},
                headers={"Accept": "*/*"},
            )
            return TextResponse(
                content=response.text,
                content_type=response.headers.get("Content-Type"),
                url=str(response.url),
            )

        return await self._cache.get_or_create(
            ("export", endpoint, identifier, export_format), fetch
        )

    async def generate_bibliography(self, tex_source: str, output_format: str) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "bibliography-generator",
            params={"format": output_format},
            files={
                "file": (
                    "input.tex",
                    tex_source.encode("utf-8"),
                    "application/x-tex",
                )
            },
        )
        return dict(response.json())

    async def download_generated_file(self, download_url: str) -> TextResponse:
        absolute_url = urljoin(self.settings.api_base_url, download_url)
        parsed_base = urlparse(self.settings.api_base_url)
        parsed_download = urlparse(absolute_url)
        if parsed_download.scheme != "https":
            raise InspireResponseError(0, "INSPIRE returned a non-HTTPS download URL.")
        hostname = parsed_download.hostname
        allowed_host = hostname == parsed_base.hostname or (
            hostname is not None
            and any(
                hostname == allowed or hostname.endswith(f".{allowed}")
                for allowed in self.settings.download_hosts
            )
        )
        if not allowed_host:
            raise InspireResponseError(
                0, f"INSPIRE returned an unexpected download host: {parsed_download.hostname}"
            )
        response = await self._request("GET", absolute_url, headers={"Accept": "*/*"})
        return TextResponse(
            content=response.text,
            content_type=response.headers.get("Content-Type"),
            url=str(response.url),
        )
