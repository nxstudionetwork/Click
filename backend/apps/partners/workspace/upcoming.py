"""Workspace for categories whose customer service doesn't exist on Click yet. Home says so; nothing is invented."""

from .base import Provider


class UpcomingProvider(Provider):
    kind = "upcoming"

    def connection(self):
        up = self.config.get("upcoming") or {}
        service = up.get("service", "This service")
        what = up.get("what", "your work")
        return "upcoming", (f"{service} isn’t open to customers yet. When it launches, {what} will appear here "
                            f"automatically.")
