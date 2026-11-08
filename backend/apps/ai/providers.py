"""
Shared Click AI provider layer.

One AI platform for Customer, Partner and Business OS; each surface passes a
role-scoped context built on the backend, never trusting client-supplied data.
Providers are swappable via CLICK_AI_PROVIDER. The default is Buddy basic mode
(apps.ai.buddy.ClickBasicBuddy), which answers only from real Click data via
apps.ai.tools. Set it to empty to disable AI (the API returns `ai_unavailable`).
Google Cloud / Gemini / Vertex AI are intentionally not supported.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

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
    customer: Any = None  # the authenticated customer; tools are scoped to it


@dataclass
class BuddyReply:
    content: str
    cards: list[dict] = field(default_factory=list)  # {"type": "store"|"product"|"event"|"order"|"booking"|"offer", ...}
    actions: list[dict] = field(default_factory=list)  # {"label", "path"} or {"label", "prompt"}


class AIProvider(Protocol):
    def reply(self, messages: list[AIMessage], context: AIContext) -> "BuddyReply | str": ...


class AIUnavailable(Exception):
    pass


def get_provider() -> AIProvider:
    path = settings.CLICK_AI_PROVIDER
    if not path:
        raise AIUnavailable()
    return import_string(path)()
