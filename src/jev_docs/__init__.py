"""Document decisions with Jev and page-aware OCR."""

__version__ = "0.1.0"

from .classify import aclassify_document, classify_document
from .documents import parse_document
from .rules import load_rules
from .schemas import CategoryRule, ClassificationResult, ParsedDocument, RuleSet, SplitResult
from .split import asplit_document, split_document

__all__ = ["CategoryRule", "ClassificationResult", "ParsedDocument", "RuleSet", "SplitResult",
           "aclassify_document", "asplit_document", "classify_document", "split_document",
           "load_rules", "parse_document"]
