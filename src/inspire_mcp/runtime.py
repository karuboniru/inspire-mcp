from __future__ import annotations

from dataclasses import dataclass

from inspire_mcp.client import InspireClient
from inspire_mcp.config import Settings


@dataclass(frozen=True, slots=True)
class AppContext:
    client: InspireClient
    settings: Settings
