import pytest

from jev_docs.schemas import CategoryRule, Page, ParsedDocument, ParserInfo, RuleSet


@pytest.fixture
def rules():
    return RuleSet(
        categories=[
            CategoryRule(id="invoice", description="A seller's request for payment"),
            CategoryRule(id="purchase_order", description="A buyer's authorization to purchase"),
        ]
    )


@pytest.fixture
def document():
    return ParsedDocument(
        source_name="neutral.pdf",
        source_sha256="a" * 64,
        canonical_path="unused.pdf",
        canonical_sha256="b" * 64,
        page_count=4,
        pages=[Page(number=i, text=f"Source content page {i}") for i in range(1, 5)],
        parser=ParserInfo(name="fixture", version="1"),
    )
