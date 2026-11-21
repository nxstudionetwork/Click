"""
Click serves India: every phone number it signs in, verifies or saves is an Indian mobile number, stored in E.164
form (+91 followed by the 10-digit number, starting 6-9). Accepted input: "9876543210", "98765 43210", "098765 43210",
"+91 98765 43210", "91-98765-43210".
"""

from __future__ import annotations

import re

from apps.core.api.exceptions import DomainError

INDIA_DIAL = "+91"
MOBILE = re.compile(r"^[6-9]\d{9}$")
E164_IN = re.compile(r"^\+91[6-9]\d{9}$")
MESSAGE = "Enter a valid 10-digit Indian mobile number."


def parse_indian_mobile(raw: str | None) -> str | None:
    """The E.164 form (+91XXXXXXXXXX) of an Indian mobile number, or None when it isn't one."""
    digits = re.sub(r"\D", "", raw or "")
    if (raw or "").strip().startswith("+") and not digits.startswith("91"):
        return None  # another country's code
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return f"{INDIA_DIAL}{digits}" if MOBILE.match(digits) else None


def normalize_indian_mobile(raw: str | None) -> str:
    phone = parse_indian_mobile(raw)
    if not phone:
        raise DomainError(MESSAGE, code="invalid_phone")
    return phone


def display(e164: str) -> str:
    """+919876543210 -> +91 98765 43210"""
    if E164_IN.match(e164 or ""):
        return f"+91 {e164[3:8]} {e164[8:]}"
    return e164 or ""
