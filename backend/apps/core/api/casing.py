"""snake_case (Python/DB) <-> camelCase (JSON API contract) conversion."""

import re
from typing import Any

_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def to_camel(key: str) -> str:
    head, *rest = key.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def to_snake(key: str) -> str:
    return _CAMEL_RE.sub("_", key).lower()


def transform_keys(data: Any, fn) -> Any:
    if isinstance(data, dict):
        return {(fn(k) if isinstance(k, str) else k): transform_keys(v, fn) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [transform_keys(v, fn) for v in data]
    return data
