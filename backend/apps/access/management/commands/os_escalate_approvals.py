"""Remind approvers about approval steps past their deadline (run every 15 minutes from the scheduler)."""

from django.core.management.base import BaseCommand

from apps.workflows.engine import escalate_overdue


class Command(BaseCommand):
    help = "Escalate overdue Business OS approval steps."

    def handle(self, *args, **opts):
        self.stdout.write(f"Escalated {escalate_overdue()} overdue approval step(s).")
