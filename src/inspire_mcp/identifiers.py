from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote, urlparse

from inspire_mcp.errors import IdentifierError

ResolvedKind = Literal["recid", "doi", "arxiv", "orcid"]

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
ARXIV_RE = re.compile(
    r"^(?:\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)$",
    re.IGNORECASE,
)
ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ResolvedIdentifier:
    kind: ResolvedKind
    value: str


def _strip_known_url(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    host = parsed.netloc.lower()
    path = unquote(parsed.path).lstrip("/")
    if host in {"doi.org", "dx.doi.org"}:
        return path
    if host in {"arxiv.org", "www.arxiv.org"}:
        return re.sub(r"^(?:abs|pdf)/", "", path).removesuffix(".pdf")
    if host in {"orcid.org", "www.orcid.org"}:
        return path
    return value


def normalize_identifier(value: str, requested_kind: str = "auto") -> ResolvedIdentifier:
    normalized = _strip_known_url(value.strip())
    normalized = re.sub(r"^(?:doi|arxiv|orcid)\s*:\s*", "", normalized, flags=re.I)

    if requested_kind == "recid":
        if not normalized.isdigit():
            raise IdentifierError("An INSPIRE recid must contain digits only.")
        return ResolvedIdentifier("recid", normalized)
    if requested_kind == "doi":
        if not DOI_RE.fullmatch(normalized):
            raise IdentifierError(f"Invalid DOI: {value!r}.")
        return ResolvedIdentifier("doi", normalized)
    if requested_kind == "arxiv":
        if not ARXIV_RE.fullmatch(normalized):
            raise IdentifierError(f"Invalid arXiv identifier: {value!r}.")
        return ResolvedIdentifier("arxiv", normalized)
    if requested_kind == "orcid":
        normalized = normalized.upper()
        if not ORCID_RE.fullmatch(normalized):
            raise IdentifierError(f"Invalid ORCID: {value!r}.")
        return ResolvedIdentifier("orcid", normalized)
    if requested_kind != "auto":
        raise IdentifierError(f"Unsupported identifier type: {requested_kind!r}.")

    if normalized.isdigit():
        return ResolvedIdentifier("recid", normalized)
    if DOI_RE.fullmatch(normalized):
        return ResolvedIdentifier("doi", normalized)
    if ARXIV_RE.fullmatch(normalized):
        return ResolvedIdentifier("arxiv", normalized)
    normalized = normalized.upper()
    if ORCID_RE.fullmatch(normalized):
        return ResolvedIdentifier("orcid", normalized)
    raise IdentifierError("Could not recognize the identifier. Specify identifier_type explicitly.")


def endpoint_for_identifier(record_type: str, identifier: ResolvedIdentifier) -> str:
    if identifier.kind == "recid":
        return record_type
    return identifier.kind


def query_for_identifier(record_type: str, identifier: ResolvedIdentifier) -> str:
    value = identifier.value.replace("\\", "\\\\").replace('"', '\\"')
    if identifier.kind == "recid":
        field = "recid" if record_type == "literature" else "control_number"
    elif identifier.kind == "doi":
        field = "dois.value"
    elif identifier.kind == "arxiv":
        field = "arxiv_eprints.value"
    elif identifier.kind == "orcid":
        field = "ids.value"
    else:
        raise IdentifierError(f"Unsupported identifier type: {identifier.kind!r}.")
    return f'{field}:"{value}"'
