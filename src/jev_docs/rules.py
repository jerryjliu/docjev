"""Human-readable category configuration."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from .errors import JevDocsError
from .schemas import RuleSet


def load_rules(path: str | Path) -> RuleSet:
    try:
        return RuleSet.model_validate(yaml.safe_load(Path(path).read_text()))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise JevDocsError(
            f"Invalid rules file: {Path(path).name}. Use unique category IDs and descriptions."
        ) from exc
