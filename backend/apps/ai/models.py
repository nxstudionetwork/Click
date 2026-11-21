"""
Buddy's records. Conversations belong to one customer (every query is scoped to the authenticated customer).

  Conversation         a chat: title (generated, renameable), archived flag, and a small explicit `context`
                       ({"topic", "query"}) so follow-ups like "only vegetarian" refine the last search — no hidden
                       long-term memory, no customer-state dump
  ConversationMessage  what was said and the cards/actions Buddy showed (factual card data came from Click APIs);
                       likely secrets (card numbers, CVV/OTP/UPI PIN mentions) are redacted before saving
  ActionExecution      every action Buddy ran or prepared: typed key, validated args, permission tier, status —
                       confirmation-required actions wait here until the customer confirms (and expire)
  BuddyEvent           product analytics without message content (opened, mode chosen, action outcome, latency)
"""

from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


class Conversation(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="buddy_conversations")
    title = models.CharField(max_length=80, blank=True)
    title_custom = models.BooleanField(default=False)
    mode = models.CharField(max_length=4, choices=[("man", "Man"), ("go", "Go")], default="man")
    archived = models.BooleanField(default=False)
    context = models.JSONField(default=dict, blank=True, help_text='Explicit, small: {"topic": "food", "query": "..."}.')
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        indexes = [models.Index(fields=["customer", "archived", "-last_message_at"], name="ai_conv_customer_idx")]


class ConversationMessage(BaseModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=[("user", "User"), ("assistant", "Assistant")])
    content = models.TextField()
    cards = models.JSONField(default=list, blank=True)
    actions = models.JSONField(default=list, blank=True)
    attachment = models.JSONField(default=dict, blank=True, help_text='A referenced Click item: {"kind": "order", "id": "...", "label": "..."}.')
    via_voice = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]


class ActionExecution(BaseModel):
    class Status(models.TextChoices):
        DONE = "done", "Done"
        AWAITING = "awaiting_confirmation", "Waiting for confirmation"
        CONFIRMED = "confirmed", "Confirmed and done"
        CANCELLED = "cancelled", "Cancelled by the customer"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="buddy_actions")
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name="action_runs")
    action = models.CharField(max_length=40)
    tier = models.CharField(max_length=10, choices=[("safe", "Safe"), ("confirm", "Needs confirmation"), ("high", "High risk")])
    args = models.JSONField(default=dict)
    status = models.CharField(max_length=24, choices=Status.choices)
    summary = models.CharField(max_length=300, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=300, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "status"], name="ai_action_customer_idx")]


class BuddyEvent(BaseModel):
    KINDS = ["opened", "mode_man", "mode_go", "message", "action_requested", "action_completed", "action_failed", "navigated",
             "voice_started", "voice_success", "voice_failed", "mic_denied"]

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="buddy_events")
    kind = models.CharField(max_length=20)
    detail = models.CharField(max_length=60, blank=True, help_text="An action key or route — never message text.")
    latency_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["kind", "created_at"], name="ai_event_kind_idx")]
