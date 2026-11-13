"""
Click phone OTP. A challenge holds a salted hash of a 6-digit code (never the code), expires after a few minutes,
allows a limited number of guesses and is used once. Requests are limited per phone and per IP, with a resend
cooldown. Verifying returns the same VerifiedIdentity the rest of sign-in already uses (provider "phone_otp",
subject = the E.164 number), so an existing account with that verified phone signs straight in.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.api.exceptions import DomainError

from . import sms
from .models import OtpChallenge
from .providers import IdentityError, VerifiedIdentity

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
PROVIDER = "phone_otp"


def _hash(challenge_id, code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()


def request_code(phone: str, ip: str | None) -> OtpChallenge:
    phone = (phone or "").replace(" ", "")
    if not E164.match(phone):
        raise DomainError("That phone number doesn’t look right.", code="invalid_phone")
    sender = sms.current()
    if sender is None:
        raise DomainError("Phone sign-in is temporarily unavailable. Please try again shortly.", code="otp_unavailable", status_code=503)
    now = timezone.now()
    recent = OtpChallenge.objects.filter(phone=phone, created_at__gte=now - timedelta(hours=1))
    last = recent.order_by("-created_at").first()
    if last and (now - last.created_at).total_seconds() < settings.CLICK_OTP_RESEND_SECONDS:
        wait = int(settings.CLICK_OTP_RESEND_SECONDS - (now - last.created_at).total_seconds()) + 1
        raise DomainError(f"Please wait {wait} seconds before requesting another code.", code="otp_cooldown", status_code=429, details={"retry_in": wait})
    if recent.count() >= settings.CLICK_OTP_MAX_PER_HOUR or (ip and OtpChallenge.objects.filter(ip=ip, created_at__gte=now - timedelta(hours=1)).count()
                                                                   >= settings.CLICK_OTP_MAX_PER_IP_HOUR):
        raise DomainError("Too many codes requested. Please try again later.", code="too_many_requests", status_code=429)
    code = f"{secrets.randbelow(10 ** 6):06d}"
    with transaction.atomic():
        OtpChallenge.objects.filter(phone=phone, used_at__isnull=True).update(used_at=now)  # only the newest code works
        ch = OtpChallenge.objects.create(phone=phone, ip=ip, code_hash="-", expires_at=now + timedelta(seconds=settings.CLICK_OTP_TTL_SECONDS))
        ch.code_hash = _hash(ch.id, code)
        ch.save(update_fields=["code_hash"])
    try:
        sender.send(phone, f"{code} is your Click. verification code. It expires in {settings.CLICK_OTP_TTL_SECONDS // 60} minutes. Never share it.")
    except Exception:  # noqa: BLE001 — a failed send must not leave a usable code behind
        OtpChallenge.objects.filter(pk=ch.pk).update(used_at=timezone.now())
        raise DomainError("We couldn’t send the code. Please try again.", code="otp_send_failed", status_code=503)
    return ch


class PhoneOtpVerifier:
    """Credential = "<challenge id>.<6-digit code>", produced by the app after the customer types the code."""

    name = PROVIDER

    def verify(self, credential: str) -> VerifiedIdentity:
        cid, _, code = (credential or "").partition(".")
        if not re.fullmatch(r"\d{6}", code):
            raise IdentityError("malformed code", public_code="invalid_code")
        failure = ""
        with transaction.atomic():  # failures are recorded first and raised after commit, so attempts always count
            ch = OtpChallenge.objects.select_for_update().filter(pk=cid).first() if re.fullmatch(r"[0-9a-f-]{36}", cid) else None
            if ch is None or ch.used_at or ch.expires_at <= timezone.now():
                failure = "code_expired"
            elif ch.attempts >= settings.CLICK_OTP_MAX_ATTEMPTS:
                failure = "too_many_attempts"
            else:
                ch.attempts += 1
                if hmac.compare_digest(ch.code_hash, _hash(ch.id, code)):
                    ch.used_at = timezone.now()
                else:
                    failure = "invalid_code"
                    if ch.attempts >= settings.CLICK_OTP_MAX_ATTEMPTS:
                        ch.used_at, failure = timezone.now(), "too_many_attempts"
                ch.save(update_fields=["attempts", "used_at"])
        if failure:
            raise IdentityError(failure, public_code=failure)
        return VerifiedIdentity(provider=PROVIDER, subject=ch.phone, phone_number=ch.phone)
