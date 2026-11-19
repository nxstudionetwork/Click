"""
Production-safe Business OS bootstrap. Creates the organization (if missing), installs the system role templates and
default approval policies, and — when asked — the first System Administrator as an INVITED account.

    python manage.py os_bootstrap --org-code click --org-name "Click" --admin-email ceo@click.in --admin-name "First Admin"

The administrator sets their own password from the printed invitation link (no default password, no backdoor),
and the System Administrator role requires MFA before its permissions take effect in production.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.access.auth_views import invite_token
from apps.access.defaults import install
from apps.access.models import OSAccount, RoleAssignment
from apps.organization.models import Organization
from apps.users.models import User


class Command(BaseCommand):
    help = "Create/refresh the Business OS organization, system roles and policies; optionally invite the first administrator."

    def add_arguments(self, parser):
        parser.add_argument("--org-code", default="click")
        parser.add_argument("--org-name", default="Click")
        parser.add_argument("--currency", default="INR")
        parser.add_argument("--timezone", default="Asia/Kolkata")
        parser.add_argument("--admin-email")
        parser.add_argument("--admin-name", default="")

    @transaction.atomic
    def handle(self, *args, **o):
        org, created = Organization.objects.get_or_create(code=o["org_code"], defaults={
            "name": o["org_name"], "base_currency": o["currency"], "timezone": o["timezone"]})
        self.stdout.write(f"Organization: {org.name} ({'created' if created else 'exists'})")
        roles = install(org)
        self.stdout.write(f"System roles: {', '.join(sorted(roles))}")
        if o["admin_email"]:
            email = o["admin_email"].strip().lower()
            user = User.objects.filter(email__iexact=email).first()
            if user and hasattr(user, "os_account"):
                raise CommandError("That person already has a Business OS account.")
            if user is None:
                user = User.objects.create_user(email, None, full_name=o["admin_name"] or email.split("@")[0])
                user.set_unusable_password()
                user.save()
            acct = OSAccount.objects.create(user=user, organization=org, status=OSAccount.Status.INVITED, invited_at=timezone.now())
            for key in ("os-admin", "employee"):
                RoleAssignment.objects.create(user=user, role=roles[key], note="Bootstrap administrator")
            self.stdout.write(self.style.SUCCESS(f"Administrator invited. Open within 7 days: <business-os-url>/invite/{invite_token(acct)}"))
