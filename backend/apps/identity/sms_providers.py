"""
Real SMS senders for Click.'s OTP. Click. generates, hashes, expires and rate-limits every code itself; a sender only
delivers the text. Pick one with CLICK_SMS_PROVIDER and give it its keys through environment variables (never code):

  CLICK_SMS_PROVIDER=msg91    MSG91_AUTH_KEY, MSG91_TEMPLATE_ID (DLT-approved OTP template; its variable is `otp`),
                              optional MSG91_SENDER_ID. India's usual choice (DLT compliant).
  CLICK_SMS_PROVIDER=twilio   TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM (or TWILIO_MESSAGING_SERVICE_SID).

A sender whose keys are missing refuses to start, so requesting a code says "phone sign-in unavailable" instead of
pretending a text was sent. Delivery failures raise, and the OTP layer then voids that code.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.parse
import urllib.request

from .sms import SmsUnavailable

logger = logging.getLogger("click.otp")
TIMEOUT = 8


def _need(*names: str) -> list[str]:
    values = [os.environ.get(n, "").strip() for n in names]
    missing = [n for n, v in zip(names, values) if not v]
    if missing:
        raise SmsUnavailable(f"missing settings: {', '.join(missing)}")
    return values


def _post(url: str, data: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — fixed provider URL
            return json.loads(r.read().decode("utf-8") or "{}")
    except Exception as e:  # noqa: BLE001
        logger.error("sms provider request failed: %s", e)
        raise SmsUnavailable("provider request failed") from e


def code_in(text: str) -> str:
    m = re.search(r"\b(\d{4,8})\b", text)
    if not m:
        raise SmsUnavailable("no code in message")
    return m.group(1)


class Msg91Sender:
    """MSG91 Flow API with a DLT-approved OTP template (India)."""

    name = "msg91"
    URL = "https://control.msg91.com/api/v5/flow"

    def __init__(self):
        self.auth_key, self.template_id = _need("MSG91_AUTH_KEY", "MSG91_TEMPLATE_ID")
        self.sender = os.environ.get("MSG91_SENDER_ID", "").strip()

    def send(self, phone: str, text: str) -> None:
        body = {"template_id": self.template_id, "short_url": "0",
                "recipients": [{"mobiles": phone.lstrip("+"), "otp": code_in(text)}]}
        if self.sender:
            body["sender"] = self.sender
        r = _post(self.URL, json.dumps(body).encode(), {"authkey": self.auth_key, "Content-Type": "application/json", "Accept": "application/json"})
        if str(r.get("type", "")).lower() == "error":
            raise SmsUnavailable(f"msg91 rejected the message: {r.get('message', '')}")


class TwilioSender:
    name = "twilio"

    def __init__(self):
        self.sid, self.token = _need("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")
        self.sender = os.environ.get("TWILIO_FROM", "").strip()
        self.service = os.environ.get("TWILIO_MESSAGING_SERVICE_SID", "").strip()
        if not (self.sender or self.service):
            raise SmsUnavailable("missing settings: TWILIO_FROM or TWILIO_MESSAGING_SERVICE_SID")

    def send(self, phone: str, text: str) -> None:
        fields = {"To": phone, "Body": text}
        fields.update({"MessagingServiceSid": self.service} if self.service else {"From": self.sender})
        auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
        r = _post(f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json", urllib.parse.urlencode(fields).encode(),
                  {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
        if r.get("error_code"):
            raise SmsUnavailable(f"twilio rejected the message: {r.get('error_message', '')}")


SENDERS = {"msg91": Msg91Sender, "twilio": TwilioSender}
