"""
Speech-to-text for Buddy GO and voice search.

No speech provider is enabled by default. Browser speech recognition is deliberately not used because it routes
audio to third-party clouds (e.g. Google's) that Click does not use. To enable voice, implement `SpeechProvider`
with an approved vendor and set CLICK_SPEECH_PROVIDER to its dotted path: the Customer App detects it through
/customer/assistant/capabilities and starts recording; nothing else changes.
"""

from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string

MAX_AUDIO_BYTES = 2 * 1024 * 1024  # ~60 s of compressed speech
AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"}


class SpeechUnavailable(Exception):
    pass


class SpeechProvider(Protocol):
    def transcribe(self, audio: bytes, content_type: str, language: str) -> str: ...


def speech_enabled() -> bool:
    return bool(settings.CLICK_SPEECH_PROVIDER)


def get_speech_provider() -> SpeechProvider:
    if not settings.CLICK_SPEECH_PROVIDER:
        raise SpeechUnavailable()
    return import_string(settings.CLICK_SPEECH_PROVIDER)()
