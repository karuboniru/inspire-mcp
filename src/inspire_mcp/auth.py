"""Verification of access tokens issued by an external OIDC provider."""

from __future__ import annotations

import asyncio
import math
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import httpx2 as httpx
import jwt
from mcp.server.auth.provider import AccessToken

_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"})
_JWKS_CACHE_SECONDS = 300
_DISCOVERY_CACHE_SECONDS = 3600
_MIN_REFRESH_SECONDS = 30


def _https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )


class OIDCTokenVerifier:
    """Discover and cache public signing keys without performing startup I/O.

    Unknown key IDs can refresh the JWKS at most once every 30 seconds, allowing
    key rotation without letting arbitrary bearer tokens trigger unbounded I/O.
    """

    def __init__(self, issuer: str, resource_url: str) -> None:
        if not _https_url(issuer) or urlsplit(issuer).query:
            raise ValueError("OIDC issuer must be an HTTPS URL without a query or fragment")
        self._issuer = issuer
        self._resource_url = resource_url
        self._discovery_url = issuer.rstrip("/") + "/.well-known/openid-configuration"
        self._jwks_uri: str | None = None
        self._discovery_expires_at = 0.0
        self._keys: list[dict[str, Any]] | None = None
        self._jwks_expires_at = 0.0
        self._last_jwks_refresh = 0.0
        self._lock = asyncio.Lock()

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if not isinstance(algorithm, str) or algorithm not in _ALGORITHMS:
                return None
            if "crit" in header or header.get("b64") is False:
                return None
            kid = header.get("kid")
            if kid is not None and (not isinstance(kid, str) or not kid):
                return None
            key = await self._get_key(kid, algorithm)
            if key is None:
                return None
            claims = jwt.decode(
                token,
                key.key,
                algorithms=[algorithm],
                issuer=self._issuer,
                audience=self._resource_url,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
            return self._access_token(token, claims)
        except (httpx.HTTPError, jwt.PyJWTError, ValueError, TypeError, OverflowError, KeyError):
            # Invalid tokens and unavailable or malformed provider data fail closed.
            return None

    async def _get_key(self, kid: str | None, algorithm: str) -> jwt.PyJWK | None:
        async with self._lock:
            now = monotonic()
            refreshed = self._keys is None or now >= self._jwks_expires_at
            if refreshed:
                await self._refresh_keys()
            key = self._select_key(kid, algorithm)
            if (
                key is None
                and not refreshed
                and now - self._last_jwks_refresh >= _MIN_REFRESH_SECONDS
            ):
                await self._refresh_keys()
                key = self._select_key(kid, algorithm)
            return key

    async def _refresh_keys(self) -> None:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            if self._jwks_uri is None or monotonic() >= self._discovery_expires_at:
                response = await client.get(self._discovery_url)
                response.raise_for_status()
                metadata = response.json()
                if not isinstance(metadata, dict) or metadata.get("issuer") != self._issuer:
                    raise ValueError("OIDC discovery issuer does not match configured issuer")
                jwks_uri = metadata.get("jwks_uri")
                if not isinstance(jwks_uri, str) or not _https_url(jwks_uri):
                    raise ValueError("OIDC JWKS URI must use HTTPS")
                self._jwks_uri = jwks_uri
                self._discovery_expires_at = monotonic() + _DISCOVERY_CACHE_SECONDS
            response = await client.get(self._jwks_uri)
            response.raise_for_status()
            jwks = response.json()
            if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
                raise ValueError("OIDC JWKS must contain a list of keys")
            if not all(isinstance(key, dict) for key in jwks["keys"]):
                raise ValueError("OIDC JWKS keys must be objects")
            self._keys = jwks["keys"]
            self._last_jwks_refresh = monotonic()
            self._jwks_expires_at = self._last_jwks_refresh + _JWKS_CACHE_SECONDS

    def _select_key(self, kid: str | None, algorithm: str) -> jwt.PyJWK | None:
        matches = []
        for key in self._keys or []:
            if kid is not None and key.get("kid") != kid:
                continue
            if key.get("use", "sig") != "sig" or key.get("alg", algorithm) != algorithm:
                continue
            expected_type = "RSA" if algorithm.startswith("RS") else "EC"
            if key.get("kty") != expected_type:
                continue
            if expected_type == "EC" and key.get("crv") != {
                "ES256": "P-256",
                "ES384": "P-384",
                "ES512": "P-521",
            }[algorithm]:
                continue
            operations = key.get("key_ops")
            if operations is not None and (
                not isinstance(operations, list)
                or not all(isinstance(item, str) for item in operations)
                or "verify" not in operations
            ):
                continue
            matches.append(key)
        if len(matches) != 1:
            return None
        return jwt.PyJWK.from_dict(matches[0], algorithm=algorithm)

    def _access_token(self, token: str, claims: dict[str, Any]) -> AccessToken:
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject:
            raise ValueError("Token subject must be a nonempty string")
        audience = claims["aud"]
        if not (
            isinstance(audience, str)
            or (
                isinstance(audience, list)
                and audience
                and all(isinstance(item, str) and item for item in audience)
            )
        ):
            raise ValueError("Token audience must be a string or a list of strings")
        for name in ("exp", "iat", "nbf"):
            if name in claims:
                value = claims[name]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int | float)
                    or not math.isfinite(value)
                ):
                    raise ValueError("Token dates must be finite numbers")
        for name in ("client_id", "azp"):
            if name in claims and (not isinstance(claims[name], str) or not claims[name]):
                raise ValueError("Token client identifier must be a nonempty string")
        scope = claims.get("scope")
        scp = claims.get("scp")
        if "scope" in claims and not isinstance(scope, str):
            raise ValueError("Token scope must be a string")
        if "scp" in claims and (
            not isinstance(scp, list) or not all(isinstance(item, str) and item for item in scp)
        ):
            raise ValueError("Token scp must be a list of strings")
        scopes = scope.split() if scope is not None else scp or []
        return AccessToken(
            token=token,
            client_id=claims.get("client_id", claims.get("azp", subject)),
            scopes=scopes,
            expires_at=int(claims["exp"]),
            resource=self._resource_url,
            subject=subject,
            claims=claims,
        )
