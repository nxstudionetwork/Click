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
from apps.access.models import AccountKind, OSAccount, Role, RoleAssignment
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
    ("ananya.rao@click.dev", "Ananya Rao", "EMP-000001", "CEO", "LEAD", "CORP", [("executive", None)], None, "CEO / Executive"),
    ("vikram.shah@click.dev", "Vikram Shah", "EMP-000002", "HEAD", "TECH", "CORP", [("os-admin", None)], "ananya.rao@click.dev", "System Administrator"),
    ("priya.menon@click.dev", "Priya Menon", "EMP-000003", "HEAD", "FIN", "CORP", [("finance-head", None)], "ananya.rao@click.dev", "Finance Head"),
    ("karthik.reddy@click.dev", "Karthik Reddy", "EMP-000004", "MGR", "FIN", "HYD-BR", [("finance-manager", None)], "priya.menon@click.dev", "Finance Manager - South"),
    ("sneha.iyer@click.dev", "Sneha Iyer", "EMP-000005", "HEAD", "HR", "CORP", [("hr-manager", None)], "ananya.rao@click.dev", "HR Manager"),
    ("rahul.verma@click.dev", "Rahul Verma", "EMP-000006", "HEAD", "OPS", "CORP", [("operations-manager", None)], "ananya.rao@click.dev", "Operations Manager"),
    ("meera.nair@click.dev", "Meera Nair", "EMP-000007", "MGR", "PTN", "CORP", [("partner-manager", None)], "rahul.verma@click.dev", "Partner Manager"),
    ("arjun.kumar@click.dev", "Arjun Kumar", "EMP-000008", "MGR", "OPS", "HYD-BR", [("branch-manager", None)], "rahul.verma@click.dev", "Branch Manager - Hyderabad"),
    ("divya.patel@click.dev", "Divya Patel", "EMP-000009", "EXEC", "OPS", "HYD-BR", [], "arjun.kumar@click.dev", "Employee - Hyderabad"),
    ("rohit.gupta@click.dev", "Rohit Gupta", "EMP-000010", "EXEC", "OPS", "DEL-BR", [], "rahul.verma@click.dev", "Employee - Delhi"),
    ("farah.khan@click.dev", "Farah Khan", "EMP-000011", "MGR", "FIN", "CORP", [("auditor", None)], "priya.menon@click.dev", "Internal Auditor"),
    ("neha.joshi@click.dev", "Neha Joshi", "EMP-000012", "EXEC", "HR", "CORP", [("recruiter", None)], "sneha.iyer@click.dev", "Recruiter"),
    ("imran.sheikh@click.dev", "Imran Sheikh", "EMP-000013", "MGR", "HR", "HYD-BR", [("hr-business-partner", None)], "sneha.iyer@click.dev", "HR Business Partner - South"),
    ("lakshmi.rao@click.dev", "Lakshmi Rao", "EMP-000014", "EXEC", "OPS", "HYD-BR", [], "arjun.kumar@click.dev", "Employee - Hyderabad 2"),
    ("suresh.pillai@click.dev", "Suresh Pillai", "EMP-000015", "EXEC", "FIN", "CORP", [("accountant", None), ("payables-executive", None)],
     "priya.menon@click.dev", "Accountant"),
    ("anita.desai@click.dev", "Anita Desai", "EMP-000016", "MGR", "FIN", "CORP", [("treasury-manager", None), ("financial-controller", None)],
     "priya.menon@click.dev", "Treasury & Controller"),
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
                "joined_on": date(2025, 11, 20) if emp_id in ("EMP-000001", "EMP-000002", "EMP-000005") else
                             timezone.now().date() - timedelta(days=12) if emp_id == "EMP-000010" else
                             timezone.now().date() - timedelta(days=150) if emp_id == "EMP-000014" else date(2026, 1, 5),
                "status": "probation" if emp_id == "EMP-000014" else "active",
                "probation_end_on": timezone.now().date() + timedelta(days=20) if emp_id == "EMP-000014" else None})
            acct, created = OSAccount.objects.get_or_create(user=user, defaults={"organization": org, "kind": AccountKind.EMPLOYEE,
                                                                                 "status": OSAccount.Status.ACTIVE})
            acct.status = OSAccount.Status.ACTIVE
            acct.preferences = {**(acct.preferences or {}), "dev_persona": label}
            if created:
                acct.onboarding_completed_at = timezone.now() if emp_id != "EMP-000009" else None  # Divya shows first-login onboarding
            acct.save()
            for key in ["employee"] + [r for r, _ in role_specs]:
                role = roles.get(key) or Role.objects.get(organization=org, key=key)  # module roles (finance, procurement) come from their installers
                RoleAssignment.objects.get_or_create(user=user, role=role, is_active=True, defaults={"note": "Development seed"})
            people[email] = user

        self._samples(org, people)
        self._hr(org, people, depts, units, desig)
        install(org)  # second pass links module data (e.g. finance cost centers) to the departments created above
        self._finance(org, people, depts)
        return org

    def _finance(self, org, people, depts):
        """DEVELOPMENT finance data: platform payments brought into the ledger, budgets, a bill and an overdue invoice."""
        from apps.access.authz import load_context
        from apps.finance import platform, services
        from apps.finance.ledger import default_entity, fiscal_year_of, next_number
        from apps.finance.models import BankAccount, Budget, BudgetLine, Invoice

        entity = default_entity(org)
        platform.sync(org)
        priya = people["priya.menon@click.dev"]
        req = RequestFactory().post("/")
        req.user = priya
        ctx = load_context(priya)
        bank = BankAccount.objects.filter(entity=entity, account_type="current").first()
        if bank and not bank.last4:
            bank.bank_name = "HDFC Bank (dev)"
            bank.save(update_fields=["bank_name"])
            services.set_bank_number(req, ctx, bank, "50200012345678", "HDFC0001234")
        fy = fiscal_year_of(entity, timezone.localdate())
        for code, name, amount, category in (("TECH", "Technology FY budget", Decimal("1200000"), "technology"),
                                              ("OPS", "Operations FY budget", Decimal("600000"), "operations"),
                                              ("MKT", "Marketing FY budget", Decimal("800000"), "marketing")):
            if depts.get(code) and not Budget.objects.filter(organization=org, department=depts[code], fiscal_year=fy).exists():
                b = Budget.objects.create(organization=org, entity=entity, number=next_number(org, "budget"), name=name, fiscal_year=fy,
                                          department=depts[code], category=category, owner=priya, status="active", notes="Development seed (pre-approved)")
                BudgetLine.objects.create(budget=b, amount=amount)
        if not Invoice.objects.filter(organization=org).exists():
            inv = services.create_invoice(req, ctx, {"party_name": "Acme Foods Pvt Ltd (dev)", "party_type": "customer", "revenue_type": "advertising",
                                                     "issue_date": (timezone.localdate() - timedelta(days=45)).isoformat(),
                                                     "due_date": (timezone.localdate() - timedelta(days=15)).isoformat(),
                                                     "lines": [{"description": "Sponsored placement — Hyderabad, October", "quantity": 1, "unit_price": "100000",
                                                                "account_key": "advertising_revenue",
                                                                "tax_rule_id": str(__import__("apps.finance.models", fromlist=["TaxRule"]).TaxRule.objects.get(organization=org, code="GST18").pk)}]},
                                          kind="customer_invoice")
            services.issue_invoice(req, ctx, inv)
            services.create_invoice(req, ctx, {"party_name": "CloudServe India (dev)", "party_type": "supplier", "supplier_invoice_number": "CS-2026-1101",
                                               "lines": [{"description": "Cloud hosting — November", "quantity": 1, "unit_price": "45000", "account_key": "technology"}]},
                                    kind="vendor_bill")

    def _hr(self, org, people, depts, units, desig):
        """DEVELOPMENT people & HR data: policies a real company would configure, and a little activity to look at."""
        from datetime import time

        from django.test import RequestFactory

        from apps.people import models as pm
        from apps.access.authz import context_for
        from apps.people.services import submit_leave
        from apps.workspace.models import Announcement

        today = timezone.now().date()
        emps = {e.work_email: e for e in Employee.objects.filter(organization=org)}
        for code, name, rank in (("L1", "Associate", 1), ("L2", "Senior Associate", 2), ("L3", "Lead", 3), ("L4", "Manager", 4), ("L5", "Head", 5), ("L6", "Executive", 6)):
            pm.JobLevel.objects.update_or_create(organization=org, code=code, defaults={"name": name, "rank": rank})
        std, _ = pm.WorkSchedule.objects.update_or_create(organization=org, name="Standard (Mon–Fri, 9:30–18:30)", defaults={
            "kind": "standard", "start_time": time(9, 30), "end_time": time(18, 30), "grace_minutes": 15, "working_days": [1, 2, 3, 4, 5], "is_default": True})
        pm.WorkSchedule.objects.update_or_create(organization=org, name="Operations shift (Mon–Sat, 8:00–17:00)", defaults={
            "kind": "shift", "start_time": time(8, 0), "end_time": time(17, 0), "grace_minutes": 10, "working_days": [1, 2, 3, 4, 5, 6]})
        Employee.objects.filter(organization=org, schedule__isnull=True).update(schedule=std)
        for code, name, paid, quota, hr_over, color in (("AL", "Annual leave", True, 18, 6, "#5b3df5"), ("SL", "Sick leave", True, 8, None, "#0b7f62"),
                                                       ("CL", "Casual leave", True, 6, None, "#1d5bd6"), ("UL", "Unpaid leave", False, 0, 5, "#a15c00")):
            pm.LeaveType.objects.update_or_create(organization=org, code=code, defaults={"name": name, "paid": paid, "annual_quota": quota,
                                                                                        "hr_approval_over_days": hr_over, "color": color})
        corp, _ = pm.HolidayCalendar.objects.get_or_create(organization=org, name="Click corporate holidays", org_unit=None)
        tg, _ = pm.HolidayCalendar.objects.get_or_create(organization=org, name="Telangana holidays", org_unit=units["TG"])
        for cal, d, name, opt in ((corp, date(today.year, 1, 26), "Republic Day", False), (corp, date(today.year, 8, 15), "Independence Day", False),
                                  (corp, date(today.year, 10, 2), "Gandhi Jayanti", False), (corp, date(today.year, 12, 25), "Christmas", True),
                                  (tg, date(today.year, 6, 2), "Telangana Formation Day", False)):
            pm.Holiday.objects.get_or_create(calendar=cal, date=d, name=name, defaults={"optional": opt})
        pm.ChecklistTemplate.objects.get_or_create(organization=org, kind="onboarding", name="Standard onboarding", defaults={"is_default": True, "steps": [
            {"title": "Collect signed offer and ID documents", "owner": "hr", "offset_days": -3},
            {"title": "Create Business OS account and email", "owner": "it", "offset_days": -2},
            {"title": "Prepare laptop and access card", "owner": "it", "offset_days": -1},
            {"title": "Welcome meeting and 30-60-90 plan", "owner": "manager", "offset_days": 0},
            {"title": "Complete policy acknowledgements", "owner": "employee", "offset_days": 2},
            {"title": "Payroll and bank setup", "owner": "finance", "offset_days": 3},
            {"title": "Probation goals agreed", "owner": "manager", "offset_days": 14}]})
        pm.ChecklistTemplate.objects.get_or_create(organization=org, kind="offboarding", name="Standard offboarding", defaults={"is_default": True, "steps": [
            {"title": "Knowledge transfer plan", "owner": "manager", "offset_days": 0},
            {"title": "Return laptop, access card and equipment", "owner": "it", "offset_days": 0},
            {"title": "Revoke system access on last day", "owner": "it", "offset_days": 0},
            {"title": "Finance clearance", "owner": "finance", "offset_days": 1},
            {"title": "HR clearance and exit interview", "owner": "hr", "offset_days": 1},
            {"title": "Final settlement", "owner": "finance", "offset_days": 30}]})
        for name, cat in (("Python", "technical"), ("SQL", "technical"), ("Customer communication", "soft"), ("Leadership", "soft"),
                          ("Logistics operations", "domain"), ("Telugu", "language")):
            pm.Skill.objects.get_or_create(organization=org, name=name, defaults={"category": cat})
        pol, _ = pm.Course.objects.get_or_create(organization=org, title="Information security essentials", defaults={"kind": "internal", "mandatory": True, "duration_hours": 1})
        pm.Course.objects.get_or_create(organization=org, title="Managing high-performing teams", defaults={"kind": "workshop", "duration_hours": 6})
        pm.BenefitPlan.objects.get_or_create(organization=org, name="Group health insurance", defaults={"kind": "insurance", "description": "Employee + family cover."})
        if not pm.Enrollment.objects.filter(course=pol).exists():
            for e in Employee.objects.filter(organization=org):
                pm.Enrollment.objects.get_or_create(course=pol, employee=e, defaults={"due_on": today + timedelta(days=10)})
        divya, lakshmi = emps.get("divya.patel@click.dev"), emps.get("lakshmi.rao@click.dev")
        if divya and not pm.Certification.objects.filter(employee=divya).exists():
            pm.Certification.objects.create(employee=divya, name="Forklift safety", provider="SafeWork", issued_on=today - timedelta(days=700),
                                            expires_on=today + timedelta(days=18))
        for e in (divya, lakshmi):
            if e:
                pv, _ = pm.EmployeePrivate.objects.get_or_create(employee=e)
                if e is divya:
                    pv.date_of_birth, pv.share_birthday = date(1997, (today + timedelta(days=3)).month, (today + timedelta(days=3)).day), True
                    pv.save()
        cycle, made = pm.ReviewCycle.objects.get_or_create(organization=org, name=f"H2 {today.year} review", defaults={
            "frequency": "half_yearly", "starts_on": today - timedelta(days=20), "ends_on": today + timedelta(days=40),
            "self_review_due": today + timedelta(days=5), "manager_review_due": today + timedelta(days=20), "status": "active"})
        if made:
            for e in Employee.objects.filter(organization=org, status__in=Employee.WORKING).select_related("manager__user"):
                if e.user_id:
                    pm.Review.objects.get_or_create(cycle=cycle, employee=e, reviewer=e.user, kind="self", defaults={"due_on": cycle.self_review_due})
                if e.manager_id and e.manager.user_id:
                    pm.Review.objects.get_or_create(cycle=cycle, employee=e, reviewer=e.manager.user, kind="manager", defaults={"due_on": cycle.manager_review_due})
            company = pm.Goal.objects.create(organization=org, level="company", title="Grow monthly active customers 30%", kind="okr", metric="MAU growth %",
                                             target=30, current=12, cycle=cycle)
            ops = pm.Goal.objects.create(organization=org, level="department", department=depts["OPS"], parent=company, title="On-time delivery above 95%",
                                         metric="On-time %", target=95, current=91, cycle=cycle)
            if divya:
                pm.Goal.objects.create(organization=org, level="employee", employee=divya, parent=ops, title="Resolve delivery exceptions within 2 hours",
                                       metric="Median hours", target=2, current=3, cycle=cycle, status="at_risk")
        if not pm.Position.objects.filter(organization=org).exists():
            pos = pm.Position.objects.create(organization=org, title="Senior Software Engineer", department=depts["TECH"], org_unit=units["CORP"],
                                             designation=desig["ENG"], headcount=2, salary_min=1800000, salary_max=2600000, status="open",
                                             reporting_manager=emps.get("vikram.shah@click.dev"),
                                             description="Build Click platform services.")
            opening = pm.JobOpening.objects.create(organization=org, position=pos, title=pos.title, openings=2, status="open",
                                                   recruiter=people.get("neha.joshi@click.dev"), hiring_manager=emps.get("vikram.shah@click.dev"),
                                                   opened_on=today - timedelta(days=14))
            for name, title, stage, yrs in (("Aditya Varma", "Backend Engineer", "interview", 5), ("Sana Qureshi", "Software Engineer II", "screening", 4),
                                            ("Ravi Teja", "Senior Developer", "applied", 7), ("Meghana S", "SDE", "shortlisted", 3)):
                c = pm.Candidate.objects.create(organization=org, full_name=name, current_title=title, experience_years=yrs, source="Careers page",
                                                skills=["Python", "Django", "PostgreSQL"], consent_on=today - timedelta(days=10), email=f"{name.split()[0].lower()}@example.dev")
                pm.Application.objects.create(organization=org, candidate=c, opening=opening, stage=stage)
            pm.Position.objects.create(organization=org, title="Operations Associate", department=depts["OPS"], org_unit=units["HYD-BR"], headcount=3,
                                       worker_type="field_worker", status="draft", reporting_manager=emps.get("arjun.kumar@click.dev"))
            pm.HeadcountPlan.objects.get_or_create(department=depts["TECH"], org_unit=None, period=f"FY{today.year + 1}",
                                                   defaults={"organization": org, "approved": 6, "planned": 8})
        if divya and not pm.AttendanceRecord.objects.filter(employee=divya).exists():
            tz = timezone.get_current_timezone()
            from datetime import datetime

            for back in range(1, 8):
                d = today - timedelta(days=back)
                if d.isoweekday() > 5:
                    continue
                late = back == 2
                pm.AttendanceRecord.objects.create(employee=divya, date=d, check_in=datetime.combine(d, time(9, 58 if late else 9, 20), tzinfo=tz),
                                                   check_out=None if back == 1 else datetime.combine(d, time(18, 40), tzinfo=tz), late=late)
        if lakshmi and not pm.LeaveRequest.objects.filter(employee=lakshmi).exists():
            rf = RequestFactory().post("/")
            rf.user = lakshmi.user
            start = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
            submit_leave(rf, context_for(rf), lakshmi,
                         pm.LeaveType.objects.get(organization=org, code="AL"), start, start + timedelta(days=1), "", "Family function")
        if not Announcement.objects.filter(organization=org).exists():
            Announcement.objects.create(organization=org, title="Welcome to Click Business OS", category="feature", priority="important",
                                        body="Home now shows your priorities, approvals, alerts and business pulse in one place. Press Ctrl+K to search anything.",
                                        starts_at=timezone.now() - timedelta(hours=1), created_by=people.get("vikram.shah@click.dev"))
            Announcement.objects.create(organization=org, title="Scheduled maintenance this Sunday", category="maintenance", priority="normal",
                                        body="Business OS will be unavailable on Sunday 02:00–03:00 IST.", requires_ack=True,
                                        starts_at=timezone.now() - timedelta(hours=1), ends_at=timezone.now() + timedelta(days=5),
                                        created_by=people.get("vikram.shah@click.dev"))

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
