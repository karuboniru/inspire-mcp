from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast
from urllib.parse import urlsplit

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


@dataclass(frozen=True, slots=True)
class Settings:
    api_base_url: str = "https://inspirehep.net/api/"
    timeout_seconds: float = 30.0
    connect_timeout_seconds: float = 5.0
    rate_limit_requests: int = 12
    rate_limit_window_seconds: float = 5.0
    max_retries: int = 2
    max_tex_bytes: int = 1_000_000
    max_export_characters: int = 1_000_000
    cache_ttl_seconds: float = 300.0
    cache_max_entries: int = 256
    download_hosts: tuple[str, ...] = ("inspirehep.net", "s3.cern.ch")
    log_level: LogLevel = "INFO"
    oidc_issuer: str | None = None
    public_url: str | None = None

    def __post_init__(self) -> None:
        # Presence (including an empty value) opts into authentication. Incomplete
        # or invalid configuration must stop startup, never disable authentication.
        if (self.oidc_issuer is None) != (self.public_url is None):
            raise ValueError(
                "Authentication requested: Set both INSPIRE_MCP_OIDC_ISSUER and "
                "INSPIRE_MCP_PUBLIC_URL; refusing to start without authentication."
            )
        for name, value in (
            ("INSPIRE_MCP_OIDC_ISSUER", self.oidc_issuer),
            ("INSPIRE_MCP_PUBLIC_URL", self.public_url),
        ):
            if value is None:
                continue
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or any(char.isspace() for char in value)
            ):
                raise ValueError(f"{name} must be an HTTPS URL without credentials/query/fragment.")
            # Accessing port also validates a malformed or out-of-range port.
            _ = parsed.port

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        base_url = os.getenv("INSPIRE_API_BASE_URL", defaults.api_base_url)
        log_level = os.getenv("INSPIRE_MCP_LOG_LEVEL", defaults.log_level).upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Invalid INSPIRE_MCP_LOG_LEVEL: {log_level!r}")
        download_hosts = tuple(
            host.strip().lower()
            for host in os.getenv(
                "INSPIRE_DOWNLOAD_HOSTS", ",".join(defaults.download_hosts)
            ).split(",")
            if host.strip()
        )
        return cls(
            api_base_url=base_url.rstrip("/") + "/",
            timeout_seconds=_env_float("INSPIRE_TIMEOUT_SECONDS", defaults.timeout_seconds),
            connect_timeout_seconds=_env_float(
                "INSPIRE_CONNECT_TIMEOUT_SECONDS", defaults.connect_timeout_seconds
            ),
            rate_limit_requests=_env_int(
                "INSPIRE_RATE_LIMIT_REQUESTS", defaults.rate_limit_requests
            ),
            rate_limit_window_seconds=_env_float(
                "INSPIRE_RATE_LIMIT_WINDOW_SECONDS", defaults.rate_limit_window_seconds
            ),
            max_retries=_env_int("INSPIRE_MAX_RETRIES", defaults.max_retries),
            max_tex_bytes=_env_int("INSPIRE_MAX_TEX_BYTES", defaults.max_tex_bytes),
            max_export_characters=_env_int(
                "INSPIRE_MAX_EXPORT_CHARACTERS", defaults.max_export_characters
            ),
            cache_ttl_seconds=_env_float("INSPIRE_CACHE_TTL_SECONDS", defaults.cache_ttl_seconds),
            cache_max_entries=_env_int("INSPIRE_CACHE_MAX_ENTRIES", defaults.cache_max_entries),
            download_hosts=download_hosts,
            log_level=cast(LogLevel, log_level),
            oidc_issuer=os.getenv("INSPIRE_MCP_OIDC_ISSUER"),
            public_url=os.getenv("INSPIRE_MCP_PUBLIC_URL"),
        )
