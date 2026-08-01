from __future__ import annotations

from copy import deepcopy
from typing import Any

from inspire_mcp.models import DetailLevel


def _metadata(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def canonical_recid(record: dict[str, Any]) -> str:
    metadata = _metadata(record)
    value = metadata.get("control_number") or record.get("id")
    return str(value)


def source_url(record: dict[str, Any], record_type: str) -> str:
    links = record.get("links")
    if isinstance(links, dict) and isinstance(links.get("json"), str):
        return str(links["json"])
    return f"https://inspirehep.net/api/{record_type}/{canonical_recid(record)}"


def _first_title(metadata: dict[str, Any]) -> str | None:
    for title in metadata.get("titles", []):
        if isinstance(title, dict) and title.get("title"):
            return str(title["title"])
    return None


def _author_name(author: Any) -> str | None:
    if not isinstance(author, dict):
        return None
    value = author.get("full_name")
    return str(value) if value else None


def _publication_year(metadata: dict[str, Any]) -> int | str | None:
    preprint_date = metadata.get("preprint_date") or metadata.get("earliest_date")
    if preprint_date:
        return str(preprint_date).split("-", maxsplit=1)[0]
    for publication in metadata.get("publication_info", []):
        if isinstance(publication, dict) and publication.get("year") is not None:
            year = publication["year"]
            if isinstance(year, (int, str)):
                return year
    return None


def _identifier_values(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item["value"]) for item in items if isinstance(item, dict) and item.get("value")]


def _bounded_metadata(
    metadata: dict[str, Any], limits: dict[str, int]
) -> tuple[dict[str, Any], list[str]]:
    result = deepcopy(metadata)
    truncated: list[str] = []
    for field, default_limit in limits.items():
        value = result.get(field)
        if isinstance(value, list) and len(value) > default_limit:
            result[field] = value[:default_limit]
            truncated.append(f"metadata.{field}")
    result.pop("email_addresses", None)
    return result, truncated


def project_literature(
    record: dict[str, Any], detail: DetailLevel
) -> tuple[dict[str, Any], list[str]]:
    metadata = _metadata(record)
    authors = metadata.get("authors", []) if isinstance(metadata.get("authors"), list) else []
    author_names = [name for author in authors if (name := _author_name(author))]
    collaborations = [
        str(item["value"])
        for item in metadata.get("collaborations", [])
        if isinstance(item, dict) and item.get("value")
    ]
    compact = {
        "recid": canonical_recid(record),
        "title": _first_title(metadata),
        "year": _publication_year(metadata),
        "authors": author_names[:5],
        "authors_total": len(authors),
        "collaborations": collaborations,
        "document_type": metadata.get("document_type", []),
        "publication_info": metadata.get("publication_info", [])[:1],
        "arxiv": _identifier_values(metadata.get("arxiv_eprints")),
        "dois": _identifier_values(metadata.get("dois")),
        "texkeys": list(metadata.get("texkeys", [])),
        "citation_count": metadata.get("citation_count"),
        "citation_count_without_self_citations": metadata.get(
            "citation_count_without_self_citations"
        ),
    }
    truncated = ["metadata.authors"] if len(authors) > 5 else []
    if detail == "compact":
        return compact, truncated

    if detail == "standard":
        standard = compact | {
            "titles": metadata.get("titles", []),
            "authors": authors[:20],
            "abstract": (metadata.get("abstracts") or [None])[0],
            "publication_info": metadata.get("publication_info", []),
            "arxiv_eprints": metadata.get("arxiv_eprints", []),
            "dois": metadata.get("dois", []),
            "report_numbers": metadata.get("report_numbers", []),
            "external_system_identifiers": metadata.get("external_system_identifiers", []),
            "inspire_categories": metadata.get("inspire_categories", []),
            "flags": {
                key: metadata.get(key)
                for key in ("core", "curated", "refereed", "citeable")
                if key in metadata
            },
            "links": record.get("links", {}),
        }
        return standard, ["metadata.authors"] if len(authors) > 20 else []

    bounded, detailed_truncated = _bounded_metadata(
        metadata,
        {
            "authors": 100,
            "references": 25,
            "raw_references": 25,
            "figures": 20,
            "documents": 20,
            "keywords": 100,
        },
    )
    return {
        "id": record.get("id"),
        "uuid": record.get("uuid"),
        "created": record.get("created"),
        "updated": record.get("updated"),
        "revision_id": record.get("revision_id"),
        "metadata": bounded,
        "links": record.get("links", {}),
    }, detailed_truncated


def _author_display_name(metadata: dict[str, Any]) -> str | None:
    name = metadata.get("name")
    if not isinstance(name, dict):
        return None
    value = name.get("preferred_name") or name.get("value")
    return str(value) if value else None


def _current_positions(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    positions = metadata.get("positions", [])
    if not isinstance(positions, list):
        return []
    current = [item for item in positions if isinstance(item, dict) and item.get("current")]
    return current or [item for item in positions[:1] if isinstance(item, dict)]


def project_author(
    record: dict[str, Any], detail: DetailLevel, *, include_email: bool = False
) -> tuple[dict[str, Any], list[str]]:
    metadata = _metadata(record)
    compact = {
        "recid": canonical_recid(record),
        "name": metadata.get("name"),
        "display_name": _author_display_name(metadata),
        "ids": metadata.get("ids", []),
        "current_positions": _current_positions(metadata),
        "status": metadata.get("status"),
        "stub": metadata.get("stub"),
    }
    if detail == "compact":
        return compact, []
    if detail == "standard":
        return compact | {
            "positions": metadata.get("positions", []),
            "advisors": metadata.get("advisors", []),
            "project_membership": metadata.get("project_membership", []),
            "inspire_categories": metadata.get("inspire_categories", []),
            "awards": metadata.get("awards", []),
            "urls": metadata.get("urls", []),
            "public_notes": metadata.get("public_notes", []),
        }, []

    bounded, truncated = _bounded_metadata(
        metadata,
        {
            "positions": 100,
            "advisors": 100,
            "project_membership": 100,
            "awards": 100,
            "urls": 100,
            "public_notes": 100,
        },
    )
    if include_email:
        bounded["email_addresses"] = deepcopy(metadata.get("email_addresses", []))
    return {
        "id": record.get("id"),
        "uuid": record.get("uuid"),
        "created": record.get("created"),
        "updated": record.get("updated"),
        "revision_id": record.get("revision_id"),
        "metadata": bounded,
        "links": record.get("links", {}),
    }, truncated


def project_embedded_author(author: dict[str, Any], detail: str) -> dict[str, Any]:
    result: dict[str, Any] = {"full_name": author.get("full_name")}
    record = author.get("record")
    if isinstance(record, dict):
        result["record"] = record
    if detail in {"affiliations", "identifiers"}:
        result["affiliations"] = author.get("affiliations", [])
    if detail == "identifiers":
        result["ids"] = author.get("ids", [])
        result["orcid"] = author.get("orcid")
    return result


def project_reference(reference: dict[str, Any], detail: str) -> dict[str, Any]:
    data = reference.get("reference", {})
    if not isinstance(data, dict):
        data = {}
    if detail == "compact":
        authors = data.get("authors", []) if isinstance(data.get("authors"), list) else []
        return {
            "label": data.get("label"),
            "title": data.get("title"),
            "authors": [
                author.get("full_name") for author in authors[:3] if isinstance(author, dict)
            ],
            "publication_info": data.get("publication_info"),
            "record": reference.get("record"),
        }
    if detail == "standard":
        return {
            "reference": data,
            "record": reference.get("record"),
            "curated_relation": reference.get("curated_relation"),
        }
    return deepcopy(reference)
