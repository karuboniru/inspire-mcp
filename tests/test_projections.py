from __future__ import annotations

from typing import Any

from inspire_mcp.projections import project_author, project_literature


def test_compact_literature_is_bounded(literature_record: dict[str, Any]) -> None:
    data, truncated = project_literature(literature_record, "compact")
    assert data["recid"] == "451647"
    assert data["authors_total"] == 150
    assert len(data["authors"]) == 5
    assert truncated == ["metadata.authors"]


def test_detailed_literature_reports_truncated_arrays(
    literature_record: dict[str, Any],
) -> None:
    data, truncated = project_literature(literature_record, "detailed")
    assert len(data["metadata"]["authors"]) == 100
    assert len(data["metadata"]["references"]) == 25
    assert truncated == ["metadata.authors", "metadata.references"]


def test_author_email_requires_explicit_opt_in(author_record: dict[str, Any]) -> None:
    hidden, _ = project_author(author_record, "detailed", include_email=False)
    visible, _ = project_author(author_record, "detailed", include_email=True)
    assert "email_addresses" not in hidden["metadata"]
    assert visible["metadata"]["email_addresses"][0]["value"] == "private@example.invalid"
