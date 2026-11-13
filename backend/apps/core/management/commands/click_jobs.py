"""
Runs Click.'s scheduled jobs once. Schedule it (cron / Windows Task Scheduler / your platform's scheduler):

    every 5 minutes:  python manage.py click_jobs --frequent
    daily (early):    python manage.py click_jobs --daily

Each job is idempotent, so a late or repeated run is harmless.
"""

from django.core.management.base import BaseCommand


def frequent() -> dict:
    from apps.payments.gateway import expire_unpaid
    from apps.wallet.services import expire_topups

    return {"unpaid_orders_cancelled": expire_unpaid(), "topups_expired": expire_topups()}


def daily() -> dict:
    from apps.giftcards.services import run_due as giftcards_due
    from apps.pharma.views import run_due as pharma_due
    from apps.rewards import services as rewards
    from apps.wallet import services as wallet

    return {"wallet_credit_expired": wallet.sweep_expired(), "wallet_reminders": wallet.remind_expiring(), "points_expired": rewards.sweep_expired(),
            "gift_cards": giftcards_due(), "refill_reminders": pharma_due()}


class Command(BaseCommand):
    help = "Run Click.'s scheduled jobs (unpaid checkouts, top-ups, expiries, reminders, gift card delivery)."

    def add_arguments(self, parser):
        parser.add_argument("--frequent", action="store_true")
        parser.add_argument("--daily", action="store_true")

    def handle(self, *args, **opts):
        run_all = not opts["frequent"] and not opts["daily"]
        if opts["frequent"] or run_all:
            self.stdout.write(f"frequent: {frequent()}")
        if opts["daily"] or run_all:
            self.stdout.write(f"daily: {daily()}")
