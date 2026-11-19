"""
DEVELOPMENT MOCK DATA for Click Business OS. Refuses to run unless DEBUG (or tests).

    python manage.py seed_os_dev

Creates the Click organization structure, departments, designations, employees and one persona per role so the
permission system can be tried end to end (sign in on the OS login screen with 'Development personas', or with the
email + the printed development password). Repeatable: rows are upserted by natural keys.
"""

import os
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import RequestFactory
from django.utils import timezone

from apps.access.defaults import install
from apps.access.models import AccountKind, OSAccount, RoleAssignment
from apps.organization.models import Department, Organization, OrgUnit, Team
from apps.people.models import Designation, Employee
from apps.users.models import User

DEV_PASSWORD = os.environ.get("CLICK_OS_DEV_PASSWORD", "ClickOS-dev-2026!")

UNITS = [  # code, name, type, parent code, city
    ("IN", "Click India", "business_unit", None, ""),
    ("SOUTH", "South India", "region", "IN", ""),
    ("TG", "Telangana", "state", "SOUTH", ""),
    ("HYD", "Hyderabad", "city", "TG", "Hyderabad"),
    ("HYD-BR", "Hyderabad Branch", "branch", "HYD", "Hyderabad"),
    ("CORP", "Click Corporate Office", "office", "HYD", "Hyderabad"),
    ("AP", "Andhra Pradesh", "state", "SOUTH", ""),
    ("VJA", "Vijayawada", "city", "AP", "Vijayawada"),
    ("VJA-WH", "Vijayawada Warehouse", "warehouse", "VJA", "Vijayawada"),
    ("NORTH", "North India", "region", "IN", ""),
    ("DL", "Delhi", "state", "NORTH", ""),
    ("NDL", "New Delhi", "city", "DL", "New Delhi"),
    ("DEL-BR", "Delhi Branch", "branch", "NDL", "New Delhi"),
]
DEPARTMENTS = [("LEAD", "Leadership"), ("FIN", "Finance"), ("HR", "People & HR"), ("OPS", "Operations"),
               ("PTN", "Partner Management"), ("TECH", "Technology"), ("CX", "Customer Experience")]
DESIGNATIONS = [("CEO", "Chief Executive Officer", 10), ("HEAD", "Head of Department", 8), ("MGR", "Manager", 6),
                ("ENG", "Engineer", 4), ("EXEC", "Executive", 3)]
PERSONAS = [  # email, name, employee id, designation, department, unit, roles [(role, anchor unit)], manager email, persona label
    ("ananya.rao@click.dev", "Ananya Rao", "CLK-E-0001", "CEO", "LEAD", "CORP", [("executive", None)], None, "CEO / Executive"),
    ("vikram.shah@click.dev", "Vikram Shah", "CLK-E-0002", "HEAD", "TECH", "CORP", [("os-admin", None)], "ananya.rao@click.dev", "System Administrator"),
    ("priya.menon@click.dev", "Priya Menon", "CLK-E-0003", "HEAD", "FIN", "CORP", [("finance-head", None)], "ananya.rao@click.dev", "Finance Head"),
    ("karthik.reddy@click.dev", "Karthik Reddy", "CLK-E-0004", "MGR", "FIN", "HYD-BR", [("finance-manager", None)], "priya.menon@click.dev", "Finance Manager - South"),
    ("sneha.iyer@click.dev", "Sneha Iyer", "CLK-E-0005", "HEAD", "HR", "CORP", [("hr-manager", None)], "ananya.rao@click.dev", "HR Manager"),
    ("rahul.verma@click.dev", "Rahul Verma", "CLK-E-0006", "HEAD", "OPS", "CORP", [("operations-manager", None)], "ananya.rao@click.dev", "Operations Manager"),
    ("meera.nair@click.dev", "Meera Nair", "CLK-E-0007", "MGR", "PTN", "CORP", [("partner-manager", None)], "rahul.verma@click.dev", "Partner Manager"),
    ("arjun.kumar@click.dev", "Arjun Kumar", "CLK-E-0008", "MGR", "OPS", "HYD-BR", [("branch-manager", None)], "rahul.verma@click.dev", "Branch Manager - Hyderabad"),
    ("divya.patel@click.dev", "Divya Patel", "CLK-E-0009", "EXEC", "OPS", "HYD-BR", [], "arjun.kumar@click.dev", "Employee - Hyderabad"),
    ("rohit.gupta@click.dev", "Rohit Gupta", "CLK-E-0010", "EXEC", "OPS", "DEL-BR", [], "rahul.verma@click.dev", "Employee - Delhi"),
    ("farah.khan@click.dev", "Farah Khan", "CLK-E-0011", "MGR", "FIN", "CORP", [("auditor", None)], "priya.menon@click.dev", "Internal Auditor"),
]


class Command(BaseCommand):
    help = "Load DEVELOPMENT Business OS data (organization, employees, role personas). DEVELOPMENT ONLY."

    def handle(self, *args, **opts):
        if not (settings.DEBUG or settings.TESTING):
            raise CommandError("seed_os_dev only runs with DJANGO_DEBUG=true. It must never run against production.")
        with transaction.atomic():
            org = self.seed()
        self.stdout.write(self.style.SUCCESS(f"Business OS dev data ready for {org.name}."))
        self.stdout.write(f"  Sign in at http://localhost:5177 with 'Development personas', or any persona email + password {DEV_PASSWORD} (dev only).")
        for email, name, *_rest, label in PERSONAS:
            self.stdout.write(f"  {label:<28} {name:<16} {email}")

    def seed(self) -> Organization:
        org, _ = Organization.objects.get_or_create(code="click", defaults={"name": "Click", "legal_name": "Click Technologies Pvt Ltd"})
        roles = install(org)
        units: dict[str, OrgUnit] = {}
        for code, name, kind, parent, city in UNITS:
            u = OrgUnit.objects.filter(organization=org, code=code).first() or OrgUnit(organization=org, code=code)
            u.name, u.unit_type, u.parent, u.city = name, kind, units.get(parent), city
            u.save()
            units[code] = u
        depts = {}
        for code, name in DEPARTMENTS:
            depts[code], _ = Department.objects.update_or_create(organization=org, code=code, defaults={"name": name})
        hyd_ops, _ = Team.objects.update_or_create(department=depts["OPS"], code="HYD-OPS", defaults={"name": "Hyderabad Operations", "org_unit": units["HYD-BR"]})
        desig = {}
        for code, name, grade in DESIGNATIONS:
            desig[code], _ = Designation.objects.update_or_create(organization=org, code=code, defaults={"name": name, "grade": grade})

        people: dict[str, User] = {}
        for email, name, emp_id, d_code, dept, unit, role_specs, mgr, label in PERSONAS:
            user = User.objects.filter(email__iexact=email).first() or User.objects.create_user(email, DEV_PASSWORD, full_name=name)
            if not user.has_usable_password():
                user.set_password(DEV_PASSWORD)
                user.save()
            emp, _ = Employee.objects.update_or_create(organization=org, employee_id=emp_id, defaults={
                "user": user, "full_name": name, "work_email": email, "designation": desig[d_code], "department": depts[dept],
                "org_unit": units[unit], "team": hyd_ops if unit == "HYD-BR" and dept == "OPS" else None,
                "manager": Employee.objects.filter(user__email=mgr).first() if mgr else None,
                "joined_on": date(2026, 1, 5) if emp_id != "CLK-E-0010" else timezone.now().date() - timedelta(days=12)})
            acct, created = OSAccount.objects.get_or_create(user=user, defaults={"organization": org, "kind": AccountKind.EMPLOYEE,
                                                                                 "status": OSAccount.Status.ACTIVE})
            acct.status = OSAccount.Status.ACTIVE
            acct.preferences = {**(acct.preferences or {}), "dev_persona": label}
            if created:
                acct.onboarding_completed_at = timezone.now() if emp_id != "CLK-E-0009" else None  # Divya shows first-login onboarding
            acct.save()
            for key in ["employee"] + [r for r, _ in role_specs]:
                RoleAssignment.objects.get_or_create(user=user, role=roles[key], is_active=True, defaults={"note": "Development seed"})
            people[email] = user

        self._samples(org, people)
        return org

    def _samples(self, org, people):
        from apps.workflows.engine import submit
        from apps.workflows.models import ApprovalRequest, Task

        divya, arjun, rohit = people["divya.patel@click.dev"], people["arjun.kumar@click.dev"], people["rohit.gupta@click.dev"]
        now = timezone.now()
        if not Task.objects.filter(assignee=divya).exists():
            Task.objects.create(organization=org, title="Close yesterday’s delivery exceptions", assignee=divya, created_by=arjun,
                                priority="high", due_at=now + timedelta(hours=6))
            Task.objects.create(organization=org, title="Update the Hyderabad shift roster", assignee=divya, created_by=arjun,
                                due_at=now + timedelta(days=3))
            Task.objects.create(organization=org, title="Review partner onboarding checklist", assignee=divya, created_by=divya,
                                priority="low", due_at=now - timedelta(days=1))
        if not ApprovalRequest.objects.filter(organization=org).exists():
            rf = RequestFactory()
            for user, title, amount in ((divya, "Client visit travel — Hyderabad", Decimal("12500")),
                                        (rohit, "Delhi branch printer replacement", Decimal("18900")),
                                        (divya, "Partner meet-up venue booking", Decimal("68000"))):
                req = rf.post("/")
                req.user = user
                submit(req, "finance.expense", title=title, amount=amount, description="Development sample request.")
