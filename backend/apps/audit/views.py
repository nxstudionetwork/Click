"""Audit trail API (os/audit). Scoped like everything else; sensitive events need audit.sensitive.view."""

import csv

from django.http import HttpResponse
from django.utils.dateparse import parse_date

from apps.access.api import OSView
from apps.audit.services import record

from .models import AuditEvent


def _payload(e: AuditEvent) -> dict:
    return {"id": str(e.pk), "at": e.created_at, "actor": e.actor_label or "System", "actor_kind": e.actor_kind, "action": e.action,
            "category": e.category, "module": e.module, "resource_type": e.resource_type, "resource_id": e.resource_id,
            "resource_label": e.resource_label, "old_value": e.old_value, "new_value": e.new_value, "outcome": e.outcome,
            "ip": e.ip, "sensitive": e.sensitive, "metadata": e.metadata}


class AuditView(OSView):
    permissions = {"GET": "audit.event.view"}

    def _qs(self, request):
        ctx = self.authz
        scope = ctx.scope("audit.event.view")
        qs = AuditEvent.objects.filter(organization=ctx.organization)
        if not scope.org_wide:
            qs = qs.filter(scope.q(unit="org_unit", owner="actor", organization=None))
        if not ctx.has("audit.sensitive.view"):
            qs = qs.filter(sensitive=False)
        p = request.query_params
        if p.get("category"):
            qs = qs.filter(category=p["category"])
        if p.get("module"):
            qs = qs.filter(module=p["module"])
        if p.get("outcome"):
            qs = qs.filter(outcome=p["outcome"])
        if p.get("action"):
            qs = qs.filter(action__icontains=p["action"])
        if p.get("actor"):
            qs = qs.filter(actor_label__icontains=p["actor"])
        if p.get("resource_id"):
            qs = qs.filter(resource_id=p["resource_id"])
        if d := parse_date(p.get("from", "") or ""):
            qs = qs.filter(created_at__date__gte=d)
        if d := parse_date(p.get("to", "") or ""):
            qs = qs.filter(created_at__date__lte=d)
        return qs.order_by("-created_at")

    def get(self, request):
        qs = self._qs(request)
        if request.query_params.get("export") == "csv":
            self.authz.require("audit.event.export")
            record(request, "audit.export", category="export", module="audit", metadata={"filters": dict(request.query_params)})
            resp = HttpResponse(content_type="text/csv")
            resp["Content-Disposition"] = 'attachment; filename="click-audit.csv"'
            w = csv.writer(resp)
            w.writerow(["time", "actor", "action", "category", "module", "resource", "outcome", "ip"])
            for e in qs[:10000]:
                w.writerow([e.created_at.isoformat(), e.actor_label, e.action, e.category, e.module, e.resource_label, e.outcome, e.ip or ""])
            return resp
        from apps.core.api.pagination import DefaultPagination

        p = DefaultPagination()
        page = p.paginate_queryset(qs, request, view=self)
        resp = p.get_paginated_response([_payload(e) for e in page])
        resp.data["categories"] = [{"key": k, "label": v} for k, v in AuditEvent.Category.choices]
        resp.data["can_export"] = self.authz.has("audit.event.export")
        return resp
