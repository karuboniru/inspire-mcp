from __future__ import annotations

from typing import Any


class InspireError(RuntimeError):
    """Base error for actionable INSPIRE failures."""


class InspireNotFoundError(InspireError):
    """The requested INSPIRE record does not exist."""


class InspireRateLimitError(InspireError):
    """INSPIRE continued to reject requests after retrying."""


class InspireResponseError(InspireError):
    def __init__(self, status_code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.data = data


class IdentifierError(InspireError):
    """An external identifier is invalid or ambiguous."""
