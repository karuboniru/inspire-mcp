from __future__ import annotations

import importlib
from collections.abc import Iterator

import httpx2 as httpx
import pytest
from mcp.server.auth.provider import AccessToken

from inspire_mcp import cli, server
from inspire_mcp.auth import OIDCTokenVerifier
from inspire_mcp.config import Settings

ISSUER = "https://auth.example.com/realm"
RESOURCE = "https://inspire.example.com/mcp"


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with monkeypatch.context() as patch:
        patch.setenv("INSPIRE_MCP_OIDC_ISSUER", ISSUER)
        patch.setenv("INSPIRE_MCP_PUBLIC_URL", RESOURCE)
        yield


def test_auth_configuration_requires_both_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INSPIRE_MCP_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("INSPIRE_MCP_PUBLIC_URL", raising=False)
    assert Settings.from_env().oidc_issuer is None
    monkeypatch.setenv("INSPIRE_MCP_OIDC_ISSUER", ISSUER)
    with pytest.raises(ValueError, match="Set both"):
        Settings.from_env()
    monkeypatch.delenv("INSPIRE_MCP_OIDC_ISSUER")
    monkeypatch.setenv("INSPIRE_MCP_PUBLIC_URL", RESOURCE)
    with pytest.raises(ValueError, match="Set both"):
        Settings.from_env()


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://auth.example.com",
        "https://user@auth.example.com",
        "https://auth.example.com/#fragment",
        "https://auth.example.com/?query=yes",
    ],
)
def test_auth_configuration_rejects_invalid_url(url: str) -> None:
    with pytest.raises(ValueError):
        Settings(oidc_issuer=url, public_url=RESOURCE)
    with pytest.raises(ValueError):
        Settings(oidc_issuer=ISSUER, public_url=url)


@pytest.mark.anyio
async def test_http_auth_discovery_and_enforcement(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def verify(_self: OIDCTokenVerifier, token: str) -> AccessToken | None:
        if token == "valid":
            return AccessToken(token=token, client_id="client", scopes=[], resource=RESOURCE)
        return None

    monkeypatch.setattr(OIDCTokenVerifier, "verify_token", verify)
    try:
        importlib.reload(server)
        app = server.mcp.streamable_http_app(stateless_http=True, json_response=True)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
            ) as client,
        ):
            response = await client.post("/mcp")
            assert response.status_code == 401
            assert (
                'resource_metadata="https://inspire.example.com/.well-known/'
                'oauth-protected-resource/mcp"'
            ) in response.headers["www-authenticate"]
            metadata = await client.get("/.well-known/oauth-protected-resource/mcp")
            assert metadata.status_code == 200
            assert metadata.json()["resource"] == RESOURCE
            assert metadata.json()["authorization_servers"] == [ISSUER]
            assert (
                await client.post("/mcp", headers={"Authorization": "Bearer invalid"})
            ).status_code == 401
            response = await client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer valid",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                },
            )
            assert response.status_code == 200
            assert "result" in response.json()
    finally:
        with monkeypatch.context() as patch:
            patch.delenv("INSPIRE_MCP_OIDC_ISSUER")
            patch.delenv("INSPIRE_MCP_PUBLIC_URL")
            importlib.reload(server)


def test_public_bind_with_auth(auth_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.append(kwargs))
    cli.main(["--transport", "streamable-http", "--host", "0.0.0.0"])
    assert calls[0]["transport"] == "streamable-http"


def test_public_bind_without_auth_requires_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INSPIRE_MCP_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("INSPIRE_MCP_PUBLIC_URL", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--transport", "streamable-http", "--host", "0.0.0.0"])
    assert exc.value.code == 2


@pytest.mark.parametrize(
    ("issuer", "resource"),
    [
        (ISSUER, None),
        (None, RESOURCE),
        ("", None),
        (None, ""),
        ("", ""),
        (ISSUER, ""),
        ("", RESOURCE),
    ],
)
@pytest.mark.parametrize("allow_public", [False, True])
def test_partial_auth_never_starts_unauthenticated(
    monkeypatch: pytest.MonkeyPatch,
    issuer: str | None,
    resource: str | None,
    allow_public: bool,
) -> None:
    for name, value in (
        ("INSPIRE_MCP_OIDC_ISSUER", issuer),
        ("INSPIRE_MCP_PUBLIC_URL", resource),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    def unexpected_run(**kwargs: object) -> None:
        pytest.fail("Server must not start with incomplete authentication configuration")

    monkeypatch.setattr(server.mcp, "run", unexpected_run)
    args = ["--transport", "streamable-http", "--host", "0.0.0.0"]
    if allow_public:
        args.append("--allow-public-http")
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2
