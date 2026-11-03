from __future__ import annotations

import time
from typing import Any

import httpx2 as httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from inspire_mcp import auth
from inspire_mcp.auth import OIDCTokenVerifier

ISSUER = "https://identity.example/tenant"
RESOURCE = "https://mcp.example/mcp"
JWKS_URI = "https://identity.example/keys"


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_jwk(key: rsa.RSAPrivateKey, kid: str = "first") -> dict[str, Any]:
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {**jwk, "kid": kid, "use": "sig", "alg": "RS256"}


def make_token(key: Any, *, claims: dict[str, Any] | None = None, **headers: Any) -> str:
    payload = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "sub": "researcher",
        "exp": int(time.time()) + 300,
        "scope": "read write",
        "client_id": "research-client",
    }
    payload.update(claims or {})
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "first", **headers})


class Provider:
    def __init__(self, key: rsa.RSAPrivateKey) -> None:
        self.metadata: Any = {"issuer": ISSUER, "jwks_uri": JWKS_URI}
        self.jwks: Any = {"keys": [public_jwk(key)]}
        self.requests: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if str(request.url) == ISSUER + "/.well-known/openid-configuration":
            return httpx.Response(200, json=self.metadata)
        if str(request.url) == JWKS_URI:
            return httpx.Response(200, json=self.jwks)
        raise AssertionError(f"Unexpected URL: {request.url}")


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch, signing_key: rsa.RSAPrivateKey) -> Provider:
    provider = Provider(signing_key)
    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        auth.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(provider.handle), **kwargs),
    )
    return provider


@pytest.mark.anyio
async def test_verifies_signed_token_and_caches_provider_keys(
    signing_key: rsa.RSAPrivateKey, provider: Provider
) -> None:
    verifier = OIDCTokenVerifier(ISSUER, RESOURCE)
    assert provider.requests == []
    token = make_token(signing_key)
    access = await verifier.verify_token(token)
    assert access is not None
    assert access.token == token
    assert access.client_id == "research-client"
    assert access.scopes == ["read", "write"]
    assert access.subject == "researcher"
    assert access.resource == RESOURCE
    assert access.claims is not None and access.claims["iss"] == ISSUER
    assert access.expires_at is not None and access.expires_at > time.time()
    assert await verifier.verify_token(token) is not None
    assert len(provider.requests) == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://another.example"},
        {"aud": "https://another.example/mcp"},
        {"exp": 1},
        {"exp": "9999999999"},
        {"exp": True},
        {"exp": float("inf")},
        {"sub": ""},
        {"sub": 123},
        {"nbf": int(time.time()) + 3600},
        {"iat": int(time.time()) + 3600},
        {"aud": [RESOURCE, 123]},
        {"scope": ["read"]},
        {"scope": None},
        {"scp": "read"},
        {"client_id": 123},
    ],
)
async def test_rejects_invalid_claims(
    signing_key: rsa.RSAPrivateKey, provider: Provider, claims: dict[str, Any]
) -> None:
    assert await OIDCTokenVerifier(ISSUER, RESOURCE).verify_token(
        make_token(signing_key, claims=claims)
    ) is None


@pytest.mark.anyio
@pytest.mark.parametrize("missing", ["exp", "iss", "aud", "sub"])
async def test_rejects_missing_required_claims(
    signing_key: rsa.RSAPrivateKey, provider: Provider, missing: str
) -> None:
    claims = {"iss": ISSUER, "aud": RESOURCE, "sub": "researcher", "exp": time.time() + 300}
    del claims[missing]
    token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "first"})
    assert await OIDCTokenVerifier(ISSUER, RESOURCE).verify_token(token) is None


@pytest.mark.anyio
async def test_rejects_wrong_signature(signing_key: rsa.RSAPrivateKey, provider: Provider) -> None:
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert await OIDCTokenVerifier(ISSUER, RESOURCE).verify_token(make_token(wrong_key)) is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "token", ["malformed", "", jwt.encode({"sub": "user"}, "symmetric-secret-with-32-characters")]
)
async def test_rejects_malformed_or_symmetric_tokens_without_discovery(
    token: str, provider: Provider
) -> None:
    assert await OIDCTokenVerifier(ISSUER, RESOURCE).verify_token(token) is None
    assert provider.requests == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "metadata",
    [
        {"issuer": ISSUER + "/", "jwks_uri": JWKS_URI},
        {"issuer": ISSUER, "jwks_uri": "http://identity.example/keys"},
        {"issuer": ISSUER, "jwks_uri": "https://user:password@identity.example/keys"},
        {"issuer": ISSUER},
        [],
    ],
)
async def test_rejects_untrusted_discovery(
    signing_key: rsa.RSAPrivateKey, provider: Provider, metadata: Any
) -> None:
    provider.metadata = metadata
    assert await OIDCTokenVerifier(ISSUER, RESOURCE).verify_token(make_token(signing_key)) is None
    assert len(provider.requests) == 1


@pytest.mark.anyio
async def test_ignores_token_key_urls(signing_key: rsa.RSAPrivateKey, provider: Provider) -> None:
    token = make_token(signing_key, jku="https://attacker.example/keys")
    assert await OIDCTokenVerifier(ISSUER, RESOURCE).verify_token(token) is not None
    assert provider.requests == [ISSUER + "/.well-known/openid-configuration", JWKS_URI]


@pytest.mark.anyio
async def test_refreshes_unknown_key_after_rotation(
    signing_key: rsa.RSAPrivateKey, provider: Provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(auth, "monotonic", lambda: clock[0])
    verifier = OIDCTokenVerifier(ISSUER, RESOURCE)
    assert await verifier.verify_token(make_token(signing_key)) is not None
    rotated_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    provider.jwks = {"keys": [public_jwk(rotated_key, "second")]}
    token = make_token(rotated_key, kid="second")
    assert await verifier.verify_token(token) is None
    assert len(provider.requests) == 2
    clock[0] += 31
    assert await verifier.verify_token(token) is not None
    assert provider.requests[-1] == JWKS_URI
    assert len(provider.requests) == 3


@pytest.mark.anyio
async def test_verifies_ec_signature(provider: Provider) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
    provider.jwks = {"keys": [{**jwk, "kid": "ec", "alg": "ES256"}]}
    claims = {"iss": ISSUER, "aud": RESOURCE, "sub": "user", "exp": time.time() + 300}
    token = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "ec"})
    access = await OIDCTokenVerifier(ISSUER, RESOURCE).verify_token(token)
    assert access is not None
    assert access.client_id == "user"
    assert access.scopes == []


@pytest.mark.anyio
async def test_network_failure_rejects_token(
    signing_key: rsa.RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(*args: Any, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("provider unavailable")

    monkeypatch.setattr(httpx.AsyncClient, "get", fail)
    assert await OIDCTokenVerifier(ISSUER, RESOURCE).verify_token(make_token(signing_key)) is None
