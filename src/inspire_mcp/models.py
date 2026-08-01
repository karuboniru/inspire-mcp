from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DetailLevel = Literal["compact", "standard", "detailed"]
LiteratureIdentifierType = Literal["auto", "recid", "doi", "arxiv"]
AuthorIdentifierType = Literal["auto", "recid", "orcid"]
ExternalIdentifierType = Literal["auto", "doi", "arxiv", "orcid"]


class RecordResult(BaseModel):
    record_type: str
    detail: str
    canonical_id: str
    requested_identifier: str
    updated: str | None = None
    data: dict[str, Any]
    truncated_fields: list[str] = Field(default_factory=list)
    source_url: str


class SearchResult(BaseModel):
    record_type: str
    detail: str
    query: str
    total: int
    page: int
    page_size: int
    items: list[dict[str, Any]]
    next_url: str | None = None
    source_url: str


class CollectionPageResult(BaseModel):
    collection: str
    canonical_id: str
    detail: str
    total: int
    offset: int
    limit: int
    items: list[dict[str, Any]]
    has_more: bool
    source_url: str


class ExportResult(BaseModel):
    canonical_id: str
    format: str
    detail: str
    content: str
    content_type: str | None = None
    source_url: str
    truncated: bool = False


class IdentifierResolutionResult(BaseModel):
    identifier_type: str
    normalized_identifier: str
    record_type: str
    canonical_id: str
    detail: str
    data: dict[str, Any]
    source_url: str


class BibliographyResult(BaseModel):
    format: str
    detail: str
    errors: list[Any]
    download_url: str | None = None
    content: str | None = None
    content_type: str | None = None
    truncated: bool = False
    upstream_data: dict[str, Any] | None = None
