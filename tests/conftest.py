from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def literature_record() -> dict[str, Any]:
    return {
        "id": "451647",
        "created": "1997-11-28T00:00:00+00:00",
        "updated": "2025-11-03T22:19:31+00:00",
        "revision_id": 108,
        "links": {
            "json": "https://inspirehep.net/api/literature/451647?format=json",
            "bibtex": "https://inspirehep.net/api/literature/451647?format=bibtex",
        },
        "metadata": {
            "control_number": 451647,
            "titles": [{"title": "The Large N limit"}],
            "authors": [
                {
                    "full_name": f"Author, {index}",
                    "ids": [{"schema": "INSPIRE ID", "value": f"ID-{index}"}],
                    "affiliations": [{"value": "Example U."}],
                }
                for index in range(150)
            ],
            "abstracts": [{"value": "An abstract."}],
            "arxiv_eprints": [{"value": "hep-th/9711200", "categories": ["hep-th"]}],
            "dois": [{"value": "10.4310/ATMP.1998.v2.n2.a1"}],
            "texkeys": ["Maldacena:1997re"],
            "publication_info": [{"year": 1998, "journal_title": "Adv.Theor.Math.Phys."}],
            "document_type": ["article"],
            "citation_count": 22000,
            "references": [
                {
                    "reference": {
                        "label": str(index + 1),
                        "authors": [{"full_name": "Reference, A."}],
                    }
                }
                for index in range(30)
            ],
        },
    }


@pytest.fixture
def author_record() -> dict[str, Any]:
    return {
        "id": "0000-0002-9079-593X",
        "updated": "2024-04-18T18:11:51+00:00",
        "links": {"json": "https://inspirehep.net/api/authors/1006450?format=json"},
        "metadata": {
            "control_number": 1006450,
            "name": {
                "value": "Hawking, Stephen William",
                "preferred_name": "Stephen W. Hawking",
            },
            "ids": [
                {"schema": "ORCID", "value": "0000-0002-9079-593X"},
                {"schema": "INSPIRE BAI", "value": "Stephen.W.Hawking.1"},
            ],
            "positions": [{"institution": "Cambridge U.", "rank": "SENIOR"}],
            "status": "deceased",
            "stub": False,
            "email_addresses": [{"value": "private@example.invalid", "current": True}],
        },
    }
