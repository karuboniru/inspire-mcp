from __future__ import annotations

import argparse
import ipaddress
import os
from collections.abc import Sequence

from inspire_mcp import __version__


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the INSPIRE MCP server.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport (default: stdio).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP listen host.")
    parser.add_argument("--port", type=int, default=8000, help="HTTP listen port.")
    parser.add_argument("--path", default="/mcp", help="Streamable HTTP endpoint path.")
    parser.add_argument(
        "--allow-public-http",
        action="store_true",
        help="Allow binding Streamable HTTP to a non-loopback host without authentication.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default=os.getenv("INSPIRE_MCP_LOG_LEVEL", "INFO").upper(),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (
        args.transport == "streamable-http"
        and not _is_loopback(args.host)
        and not args.allow_public_http
    ):
        parser.error(
            "Refusing a public HTTP bind without --allow-public-http. "
            "Deploy behind authentication and TLS."
        )
    os.environ["INSPIRE_MCP_LOG_LEVEL"] = args.log_level

    from inspire_mcp.server import mcp

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            streamable_http_path=args.path,
        )
