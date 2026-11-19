"""
Generic scoped resources for Business OS modules: one pattern for every list / detail endpoint.

    class PositionList(ScopedList):
        model = Position
        serializer_class = PositionSerializer
        perms = {"view": "people.position.view", "create": "people.position.create"}
        scope_fields = {"unit": "org_unit", "department": "department"}
        search_fields = ("title", "code")
        filters = {"department": "department_id", "status": "status"}

Reads are filtered by the caller's scope *in the database*. Creates and updates are checked against the scope of the
resulting record (you can't create something outside your scope). Field-level restrictions live on the serializer
(`restricted_fields`), so sensitive columns never leave the server for people without the permission.
"""

from __future__ import annotations

import csv

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from rest_framework import serializers, status
from rest_framework.response import Response

from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.core.api.pagination import DefaultPagination

from .api import OSView


class OSSerializer(serializers.ModelSerializer):
    """`restricted_fields = {"salary_min": "people.payroll.view"}` — dropped unless the caller holds the permission for
    this record (scope-aware through the view's `target_for`)."""

    restricted_fields: dict[str, str] = {}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        view = self.context.get("view")
        ctx = getattr(view, "authz", None) if view else self.context.get("authz")
        if ctx is None:
            for f in self.restricted_fields:
                data.pop(f, None)
            return data
        target = view.target_for(instance) if view is not None and hasattr(view, "target_for") else {}
        for f, code in self.restricted_fields.items():
            if not ctx.can(code, **target):
                data.pop(f, None)
        return data


class ScopedBase(OSView):
    model = None
    serializer_class = None
    perms: dict[str, str] = {}
    scope_fields: dict[str, str] = {"unit": "org_unit"}
    organization_field: str | None = "organization"
    search_fields: tuple[str, ...] = ()
    filters: dict[str, str] = {}
    ordering: tuple[str, ...] = ()
    select_related: tuple[str, ...] = ()
    audit_prefix: str = ""
    audit_category: str = "data"
    export_fields: tuple[str, ...] = ()
    sensitive_audit: bool = False

    # The method → permission map used by MethodPermission.
    @property
    def permissions(self):  # type: ignore[override]
        p = self.perms
        return {"GET": p.get("view"), "POST": p.get("create"), "PATCH": p.get("edit"), "PUT": p.get("edit"),
                "DELETE": p.get("delete")}

    def base_queryset(self):
        qs = self.model.objects.all()
        if self.organization_field:
            qs = qs.filter(**{self.organization_field: self.authz.organization})
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        return qs

    def scope_q(self, code: str):
        return self.authz.scope(code).q(**self.scope_fields, organization=None)

    def get_queryset(self):
        return self.base_queryset().filter(self.scope_q(self.perms["view"]))

    def target_for(self, obj) -> dict:
        """Attributes of a record (or of the data about to be saved) that scopes are checked against."""
        t = {}
        for key, field in self.scope_fields.items():
            value = obj
            for part in field.split("__"):
                value = getattr(value, part, None) if value is not None else None
            value = getattr(value, "pk", value)
            if value is not None:
                t[key] = value
        return t

    def require_on(self, code: str, obj) -> None:
        self.authz.require(code, **self.target_for(obj))

    def serializer(self, *args, **kw):
        kw.setdefault("context", {"request": self.request, "view": self, "authz": self.authz})
        return self.serializer_class(*args, **kw)

    def audit(self, action: str, obj, old=None, new=None):
        record(self.request, f"{self.audit_prefix}.{action}", category=self.audit_category, module=self.audit_prefix.split(".")[0],
               resource=obj, old=old, new=new, sensitive=self.sensitive_audit,
               org_unit=getattr(obj, "org_unit", None) if hasattr(obj, "org_unit_id") else None)


class ScopedList(ScopedBase):
    def filter_queryset(self, qs):
        p = self.request.query_params
        if (term := p.get("q", "").strip()) and self.search_fields:
            cond = Q()
            for f in self.search_fields:
                cond |= Q(**{f"{f}__icontains": term})
            qs = qs.filter(cond)
        for param, lookup in self.filters.items():
            v = p.get(param)
            if v not in (None, ""):
                if "," in v:
                    qs = qs.filter(**{f"{lookup}__in": v.split(",")})
                else:
                    qs = qs.filter(**{lookup: None if v == "none" else v})
        if self.ordering:
            qs = qs.order_by(*self.ordering)
        return qs

    def get(self, request):
        qs = self.filter_queryset(self.get_queryset())
        if request.query_params.get("export") == "csv":
            return self.export(qs)
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(self.serializer(page, many=True).data)

    def export(self, qs):
        code = self.perms.get("export")
        if not code or not self.export_fields:
            raise DomainError("Export isn’t available here.", code="not_found", status_code=404)
        self.authz.require(code)
        record(self.request, f"{self.audit_prefix}.export", category="export", module=self.audit_prefix.split(".")[0],
               metadata={"rows": qs.count(), "filters": dict(self.request.query_params)})
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="{self.audit_prefix.replace(".", "-")}.csv"'
        w = csv.writer(resp)
        w.writerow(self.export_fields)
        for row in self.serializer(qs[:20000], many=True).data:
            w.writerow([row.get(f, "") if not isinstance(row.get(f), dict) else row[f].get("name", "") for f in self.export_fields])
        return resp

    def perform_create(self, serializer):
        return serializer.save(**({self.organization_field: self.authz.organization} if self.organization_field else {}))

    def post(self, request):
        s = self.serializer(data=request.data)
        s.is_valid(raise_exception=True)
        probe = self.model(**{k: v for k, v in s.validated_data.items() if not isinstance(v, list)})
        self.require_on(self.perms["create"], probe)
        with transaction.atomic():
            obj = self.perform_create(s)
        self.audit("create", obj, new=dict(self.serializer(obj).data))
        return Response(self.serializer(obj).data, status=status.HTTP_201_CREATED)


class ScopedDetail(ScopedBase):
    def get_object(self, pk):
        obj = self.get_queryset().filter(pk=pk).first()
        if obj is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return obj

    def get(self, request, pk):
        return Response(self.serializer(self.get_object(pk)).data)

    def patch(self, request, pk):
        obj = self.get_object(pk)
        self.require_on(self.perms["edit"], obj)
        before = dict(self.serializer(obj).data)
        s = self.serializer(obj, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            obj = s.save()
            self.require_on(self.perms["edit"], obj)  # can't move a record outside your own scope
        after = dict(self.serializer(obj).data)
        self.audit("update", obj, old=before, new=after)
        return Response(after)

    def delete(self, request, pk):
        obj = self.get_object(pk)
        self.require_on(self.perms["delete"], obj)
        self.audit("delete", obj, old=dict(self.serializer(obj).data))
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
