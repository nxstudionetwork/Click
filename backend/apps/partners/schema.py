"""Validation of category-specific partner details against the resolved field schema."""

from __future__ import annotations

import re
from typing import Any

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DEFAULT_MAX_LENGTH = {"text": 120, "textarea": 500}


def validate_details(fields: list[dict], data: Any) -> tuple[dict, dict]:
    """Return (cleaned, errors). Unknown keys are rejected; nothing is silently dropped."""
    if not isinstance(data, dict):
        return {}, {"details": ["Expected an object."]}

    known = {f["key"]: f for f in fields}
    errors: dict[str, list[str]] = {}
    cleaned: dict[str, Any] = {}

    for key in data:
        if key not in known:
            errors[key] = ["This field is not used for your category."]

    for key, field in known.items():
        value = data.get(key)
        empty = value is None or value == "" or value == []
        if empty:
            if field.get("required"):
                errors[key] = ["This field is required."]
            continue
        error, clean = _validate_value(field, value)
        if error:
            errors[key] = [error]
        else:
            cleaned[key] = clean

    return cleaned, errors


def _validate_value(field: dict, value: Any) -> tuple[str | None, Any]:
    kind = field["kind"]
    if kind in ("text", "textarea"):
        if not isinstance(value, str):
            return "Enter text.", None
        value = " ".join(value.split()) if kind == "text" else value.strip()
        limit = field.get("max_length", DEFAULT_MAX_LENGTH[kind])
        if len(value) > limit:
            return f"Use {limit} characters or fewer.", None
        if not value and field.get("required"):
            return "This field is required.", None
        return None, value
    if kind == "number":
        if isinstance(value, bool):
            return "Enter a whole number.", None
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return "Enter a whole number.", None
        if "min" in field and number < field["min"]:
            return f"Must be at least {field['min']}.", None
        if "max" in field and number > field["max"]:
            return f"Must be at most {field['max']}.", None
        return None, number
    if kind == "time":
        if not isinstance(value, str) or not TIME_RE.match(value):
            return "Enter a time like 09:30.", None
        return None, value
    allowed = {o["value"] for o in field.get("options", [])}
    if kind == "select":
        if value not in allowed:
            return "Choose one of the options.", None
        return None, value
    if kind == "multiselect":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            return "Choose one or more options.", None
        unique = list(dict.fromkeys(value))
        if any(v not in allowed for v in unique):
            return "Choose from the listed options.", None
        if len(unique) > field.get("max_items", len(allowed)):
            return f"Choose up to {field['max_items']}.", None
        return None, unique
    return "Unsupported field.", None
