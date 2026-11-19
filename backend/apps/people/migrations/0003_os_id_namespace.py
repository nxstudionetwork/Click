"""
Business OS identifiers get their own namespace, separate from the Click apps (customers CL-CU-…, partners
CLK-PT-…, orders CLK-…). Employee numbers created under the earlier "CLK-E-" format move to "EMP-", and the
lifecycle statuses are mapped to the full HR set. Existing order is preserved; nothing is deleted.
"""

from django.db import migrations

STATUS_MAP = {"pre_joining": "pre_onboarding", "exited": "former"}


def forwards(apps, schema_editor):
    Employee = apps.get_model("people", "Employee")
    IdSequence = apps.get_model("people", "IdSequence")
    for old, new in STATUS_MAP.items():
        Employee.objects.filter(status=old).update(status=new)
    per_org: dict = {}
    for e in Employee.objects.order_by("created_at"):
        per_org.setdefault(e.organization_id, []).append(e)
    for org_id, rows in per_org.items():
        taken = {e.employee_id for e in rows}
        n = 0
        for e in rows:
            if e.employee_id.startswith("CLK-"):
                n += 1
                new = f"EMP-{n:06d}"
                while new in taken:
                    n += 1
                    new = f"EMP-{n:06d}"
                taken.discard(e.employee_id)
                taken.add(new)
                e.employee_id = new
                e.save(update_fields=["employee_id"])
        highest = max([int(x.split("-")[1]) for x in taken if x.startswith("EMP-") and x.split("-")[1].isdigit()] or [0])
        IdSequence.objects.update_or_create(organization_id=org_id, name="EMP", defaults={"value": highest})


def backwards(apps, schema_editor):
    Employee = apps.get_model("people", "Employee")
    for old, new in STATUS_MAP.items():
        Employee.objects.filter(status=new).update(status=old)


class Migration(migrations.Migration):
    dependencies = [("people", "0002_employee_confirmed_on_employee_contract_end_on_and_more")]
    operations = [migrations.RunPython(forwards, backwards)]
