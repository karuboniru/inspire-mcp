from __future__ import annotations

from dataclasses import dataclass

from inspire_mcp.models import DetailLevel


@dataclass(frozen=True, slots=True)
class RecordAdapter:
    record_type: str
    compact_fields: tuple[str, ...]
    standard_fields: tuple[str, ...]
    detailed_fields: tuple[str, ...]

    def fields_for(self, detail: DetailLevel) -> list[str]:
        return list(getattr(self, f"{detail}_fields"))


LITERATURE = RecordAdapter(
    record_type="literature",
    compact_fields=(
        "control_number",
        "titles",
        "authors.full_name",
        "collaborations",
        "document_type",
        "preprint_date",
        "publication_info",
        "arxiv_eprints",
        "dois",
        "texkeys",
        "citation_count",
        "citation_count_without_self_citations",
    ),
    standard_fields=(
        "control_number",
        "titles",
        "authors.full_name",
        "authors.record",
        "authors.ids",
        "authors.affiliations.value",
        "collaborations",
        "abstracts",
        "document_type",
        "preprint_date",
        "publication_info",
        "arxiv_eprints",
        "dois",
        "report_numbers",
        "texkeys",
        "external_system_identifiers",
        "inspire_categories",
        "citation_count",
        "citation_count_without_self_citations",
        "core",
        "curated",
        "refereed",
        "citeable",
    ),
    detailed_fields=(
        "control_number",
        "titles",
        "authors.full_name",
        "authors.record",
        "authors.ids",
        "authors.affiliations.value",
        "collaborations",
        "abstracts",
        "document_type",
        "preprint_date",
        "publication_info",
        "arxiv_eprints",
        "dois",
        "report_numbers",
        "texkeys",
        "external_system_identifiers",
        "inspire_categories",
        "keywords",
        "citation_count",
        "citation_count_without_self_citations",
        "core",
        "curated",
        "refereed",
        "citeable",
        "documents",
        "figures",
        "funding_info",
        "accelerator_experiments",
    ),
)

AUTHORS = RecordAdapter(
    record_type="authors",
    compact_fields=("control_number", "name", "ids", "positions", "status", "stub"),
    standard_fields=(
        "control_number",
        "name",
        "ids",
        "positions",
        "status",
        "stub",
        "advisors",
        "project_membership",
        "inspire_categories",
        "awards",
        "urls",
    ),
    detailed_fields=(
        "control_number",
        "name",
        "ids",
        "positions",
        "status",
        "stub",
        "advisors",
        "project_membership",
        "inspire_categories",
        "awards",
        "urls",
        "public_notes",
    ),
)

RECORD_ADAPTERS = {
    LITERATURE.record_type: LITERATURE,
    AUTHORS.record_type: AUTHORS,
}
