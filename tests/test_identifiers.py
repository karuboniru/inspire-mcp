from __future__ import annotations

import pytest

from inspire_mcp.errors import IdentifierError
from inspire_mcp.identifiers import normalize_identifier, query_for_identifier


@pytest.mark.parametrize(
    ("value", "kind", "normalized"),
    [
        ("https://doi.org/10.1103/PhysRevLett.19.1264", "doi", "10.1103/PhysRevLett.19.1264"),
        ("arXiv:1207.7214", "arxiv", "1207.7214"),
        ("https://arxiv.org/abs/hep-th/9711200", "arxiv", "hep-th/9711200"),
        ("https://orcid.org/0000-0002-9079-593X", "orcid", "0000-0002-9079-593X"),
        ("451647", "recid", "451647"),
    ],
)
def test_normalize_identifier(value: str, kind: str, normalized: str) -> None:
    result = normalize_identifier(value)
    assert result.kind == kind
    assert result.value == normalized


def test_invalid_identifier_is_actionable() -> None:
    with pytest.raises(IdentifierError, match="Could not recognize"):
        normalize_identifier("not an identifier")


def test_identifier_query_uses_schema_fields() -> None:
    assert (
        query_for_identifier("literature", normalize_identifier("10.1103/PhysRevLett.19.1264"))
        == 'dois.value:"10.1103/PhysRevLett.19.1264"'
    )
    assert (
        query_for_identifier("authors", normalize_identifier("0000-0002-9079-593X"))
        == 'ids.value:"0000-0002-9079-593X"'
    )
