"""
Where one-time codes are sent. Click owns the OTP itself (generation, hashing, expiry, attempt limits); a sender only
delivers the text. Add the SMS provider you choose as a class with `send(phone_e164, text)` and point
CLICK_SMS_PROVIDER at it — nothing else changes.

  ""          no sender configured: requesting a code fails with "phone sign-in unavailable" (production default)
  "console"   development only: the code is written to the API log instead of being texted
  "msg91" / "twilio"           ready-made senders in sms_providers.py (keys from environment variables)
  "dotted.path.ToYourSender"   any other provider (credentials come from environment variables, never from code)
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger("click.otp")


class SmsUnavailable(Exception):
    pass


class ConsoleSmsSender:
    """Development only. Hard-wired off when DEBUG is off."""

    name = "console"

    def send(self, phone: str, text: str) -> None:
        if not settings.DEBUG:
            raise SmsUnavailable("console sender is development-only")
        logger.warning("[development SMS] to %s: %s", phone, text)
        print(f"\n[development SMS] to {phone}: {text}\n", flush=True)


def current():
    """The configured sender, or None when phone sign-in can't send codes (no provider, or its keys are missing)."""
    path = settings.CLICK_SMS_PROVIDER
    if not path:
        return None
    if path == "console":
        return ConsoleSmsSender() if settings.DEBUG else None
    from .sms_providers import SENDERS

    try:
        return SENDERS[path]() if path in SENDERS else import_string(path)()
    except SmsUnavailable as e:
        logger.error("SMS provider %s is not ready: %s", path, e)
        return None
