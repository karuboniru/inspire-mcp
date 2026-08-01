from __future__ import annotations

from typing import Any

from inspire_mcp.projections import canonical_recid


def search_envelope(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int, str | None, str]:
    hits_wrapper = payload.get("hits", {})
    if not isinstance(hits_wrapper, dict):
        hits_wrapper = {}
    hits = hits_wrapper.get("hits", [])
    if not isinstance(hits, list):
        hits = []
    records = [item for item in hits if isinstance(item, dict)]
    total_value = hits_wrapper.get("total", 0)
    if isinstance(total_value, dict):
        total = int(total_value.get("value", 0))
    else:
        total = int(total_value or 0)
    links = payload.get("links", {})
    if not isinstance(links, dict):
        links = {}
    next_url = str(links["next"]) if links.get("next") else None
    self_url = str(links.get("self", ""))
    return records, total, next_url, self_url


def identity_data(record: dict[str, Any], record_type: str) -> dict[str, Any]:
    metadata = record.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    if record_type == "literature":
        return {
            "recid": canonical_recid(record),
            "dois": metadata.get("dois", []),
            "arxiv_eprints": metadata.get("arxiv_eprints", []),
            "texkeys": metadata.get("texkeys", []),
            "report_numbers": metadata.get("report_numbers", []),
            "external_system_identifiers": metadata.get("external_system_identifiers", []),
        }
    return {
        "recid": canonical_recid(record),
        "ids": metadata.get("ids", []),
    }
