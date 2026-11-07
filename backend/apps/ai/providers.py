"""
Shared Click AI provider layer.

One AI platform for Customer, Partner and Business OS; each surface passes a
role-scoped context built on the backend, never trusting client-supplied data.
Providers are swappable via CLICK_AI_PROVIDER. No provider is configured by
default, in which case the API responds honestly with `ai_unavailable`.
Google Cloud / Gemini / Vertex AI are intentionally not supported.
"""

from dataclasses import dataclass
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string


@dataclass(frozen=True)
class AIMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class AIContext:
    surface: str  # "customer" | "partner" | "business_os"
    actor_id: str
    facts: dict  # backend-built, permission-filtered context (e.g. the customer's recent orders)


class AIProvider(Protocol):
    def reply(self, messages: list[AIMessage], context: AIContext) -> str: ...


class AIUnavailable(Exception):
    pass


def get_provider() -> AIProvider:
    path = settings.CLICK_AI_PROVIDER
    if not path:
        raise AIUnavailable()
    return import_string(path)()
