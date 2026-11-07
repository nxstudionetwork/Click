import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db
MSG = {"messages": [{"role": "user", "content": "Where is my order?"}]}


class EchoProvider:
    def reply(self, messages, context):
        return f"{context.surface}:{len(context.facts['recent_orders'])}:{messages[-1].content}"


def test_ai_unavailable_without_provider(auth_api):
    r = auth_api.post("/api/v1/customer/assistant/messages", MSG)
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_unavailable"


@override_settings(CLICK_AI_PROVIDER="apps.ai.tests.EchoProvider")
def test_ai_uses_configured_provider_with_customer_scoped_context(auth_api):
    r = auth_api.post("/api/v1/customer/assistant/messages", MSG)
    assert r.json()["message"] == {"role": "assistant", "content": "customer:0:Where is my order?"}


def test_ai_validates_input(auth_api):
    assert auth_api.post("/api/v1/customer/assistant/messages", {"messages": []}).status_code == 400


def test_ai_requires_customer(api):
    assert api.post("/api/v1/customer/assistant/messages", MSG).status_code == 401
