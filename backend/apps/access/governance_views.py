"""/api/v1/os/access/* — Identity & Access workspace (Module 3). Every endpoint asks the central engine; nothing here
decides access on its own."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import slugify
from rest_framework import status
from rest_framework.response import Response

from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.organization.models import Department, OrgUnit

from . import governance as gov
from . import registry
from .admin_views import _account_or_404, _target_for_user
from .api import OSView
from .models import (AccessPackage, AccessRequest, AccessReview, AccessReviewItem, EmergencyAccess, IdentityType, OSAccount, Role,
                     RoleAssignment, RolePermission, RoleVersion, SoDException, SoDRule)

NAV = [
    ("overview", "Overview", [("home", "Identity & Access home", "/access", None), ("me", "My access", "/access/me", None)]),
    ("identity", "Identity", [("users", "Identity directory", "/settings/users", "identity.user.view"),
                              ("service", "Service accounts & API keys", "/settings/system", "identity.service_account.view")]),
    ("roles", "Roles", [("roles", "Role directory & builder", "/settings/roles", "access.role.view"),
                        ("compare", "Role comparison & matrix", "/access/compare", "access.analysis.view"),
                        ("packages", "Access packages", "/access/packages", "access.package.view")]),
    ("permissions", "Permissions", [("effective", "Effective access", "/access/effective", "access.analysis.view"),
                                    ("simulator", "Permission simulator", "/access/simulator", "access.analysis.view"),
                                    ("who", "Who has access?", "/access/who", "access.analysis.view")]),
    ("management", "Access management", [("requests", "Access requests", "/access/requests", None),
                                         ("reviews", "Access reviews", "/access/reviews", None),
                                         ("delegations", "Delegations", "/approvals?tab=delegations", None)]),
    ("security", "Security", [("emergency", "Emergency access", "/access/emergency", "access.emergency.view|access.emergency.create"),
                              ("events", "Security events", "/access/security", "identity.security.view")]),
    ("governance", "Governance", [("sod", "Segregation of duties", "/access/sod", "access.sod.view"),
                                  ("privileged", "Privileged access", "/access/privileged", "access.analysis.view"),
                                  ("hygiene", "Orphaned & unused access", "/access/hygiene", "access.analysis.view"),
                                  ("audit", "Access audit", "/settings/audit?category=access", "audit.event.view")]),
]


def _allowed(ctx, perm):
    return perm is None or any(ctx.has(p) for p in perm.split("|"))


def _dt(v, field):
    if not v:
        return None
    d = parse_datetime(str(v))
    if d is None:
        dd = parse_date(str(v))
        if dd is None:
            raise DomainError("Enter a valid date.", code="validation_error", details={field: ["Invalid date."]})
        from datetime import datetime, time

        d = datetime.combine(dd, time(23, 59), tzinfo=timezone.get_current_timezone())
    if d <= timezone.now():
        raise DomainError("The end date must be in the future.", code="validation_error", details={field: ["Must be in the future."]})
    return d


def _user_from_account(ctx, pk, code="identity.user.view"):
    return _account_or_404(ctx, pk, code).user


class NavView(OSView):
    def get(self, request):
        ctx = self.authz
        out = []
        for key, label, items in NAV:
            vis = [{"key": k, "label": lbl, "path": p} for k, lbl, p, perm in items if _allowed(ctx, perm)]
            if vis:
                out.append({"key": key, "label": label, "items": vis})
        return Response({"sections": out})


class HomeView(OSView):
    def get(self, request):
        ctx = self.authz
        if not (ctx.has("access.analysis.view") or ctx.has("identity.user.view") or ctx.has("access.role.view")):
            return Response({"mode": "self"})
        return Response({"mode": "admin", **gov.home(ctx)})


class MyAccessView(OSView):
    def get(self, request):
        data = gov.effective_access(request.user, self.authz.organization)
        data["requests"] = [_req_row(r) for r in AccessRequest.objects.filter(requester=request.user).select_related("role", "package")[:20]]
        return Response(data)


class EffectiveAccessView(OSView):
    permissions = {"GET": "access.analysis.view"}

    def get(self, request, pk):
        user = _user_from_account(self.authz, pk)
        record(request, "access.effective.viewed", category="access", module="access", resource_type="os_account", resource_id=str(pk))
        return Response(gov.effective_access(user, self.authz.organization))


class IdentityView(OSView):
    """Lifecycle attributes the Users page doesn't set: identity type and access end date."""

    permissions = {"PATCH": "identity.user.edit"}

    def patch(self, request, pk):
        ctx = self.authz
        acct = _account_or_404(ctx, pk, "identity.user.edit")
        if acct.user_id == request.user.pk:
            raise DomainError("You can’t change your own identity record.", code="self_change_denied", status_code=403)
        ctx.require("identity.user.edit", **_target_for_user(acct.user))
        before = {"identity_type": acct.identity_type, "expires_at": acct.expires_at}
        if "identity_type" in request.data:
            if request.data["identity_type"] not in IdentityType.values:
                raise DomainError("Choose an identity type.", code="validation_error")
            acct.identity_type = request.data["identity_type"]
        if "expires_at" in request.data:
            acct.expires_at = _dt(request.data["expires_at"], "expiresAt") if request.data["expires_at"] else None
        acct.save(update_fields=["identity_type", "expires_at", "updated_at"])
        record(request, "identity.user.lifecycle", category="security", module="identity", resource=acct, old=before,
               new={"identity_type": acct.identity_type, "expires_at": acct.expires_at})
        return Response({"identityType": acct.identity_type, "expiresAt": acct.expires_at})


class WhoHasView(OSView):
    permissions = {"GET": "access.analysis.view"}

    def get(self, request):
        p = request.query_params
        code = p.get("code", "")
        target = {k: v for k, v in {"unit": p.get("unit"), "department": p.get("department")}.items() if v}
        rows = gov.who_has(self.authz.organization, code, target or None)
        record(request, "access.who_has.viewed", category="access", module="access", metadata={"code": code, "rows": len(rows)})
        return Response({"code": code, "results": rows})


class SimulateView(OSView):
    permissions = {"POST": "access.analysis.view"}

    def post(self, request):
        d = request.data
        user = _user_from_account(self.authz, d.get("account_id"))
        res = gov.simulate(self.authz.organization, user, str(d.get("code", "")), unit=d.get("unit_id") or None,
                           department=d.get("department_id") or None, approval_type=str(d.get("approval_type") or ""), amount=d.get("amount"))
        record(request, "access.simulated", category="access", module="access", metadata={"code": d.get("code"), "allowed": res["allowed"]})
        return Response(res)


class CompareView(OSView):
    permissions = {"GET": "access.analysis.view"}

    def get(self, request):
        ids = [x for x in request.query_params.get("roles", "").split(",") if x]
        return Response(gov.compare_roles(self.authz.organization, ids))


class MatrixView(OSView):
    """Role × permission grid for one module (filterable), so admins see breadth at a glance."""

    permissions = {"GET": "access.analysis.view"}

    def get(self, request):
        module = request.query_params.get("module", "")
        roles = list(Role.objects.filter(organization=self.authz.organization, is_active=True).order_by("priority", "name"))
        grants = {}
        for rp in RolePermission.objects.filter(role__in=roles, permission__module=module).select_related("permission"):
            grants.setdefault(rp.permission.code, {})[str(rp.role_id)] = rp.scope
        mod = registry.MODULE_BY_KEY.get(module)
        rows = []
        if mod:
            for res in mod.resources:
                rows.append({"resource": res.label, "sensitive": res.sensitive,
                             "actions": {a: grants.get(f"{module}.{res.key}.{a}", {}) for a in res.actions}})
        return Response({"modules": [{"key": m.key, "label": m.label} for m in registry.MODULES if m.resources],
                         "roles": [{"id": str(r.pk), "name": r.name} for r in roles], "rows": rows})


class RoleVersionsView(OSView):
    permissions = {"GET": "access.role.view"}

    def get(self, request, pk):
        role = Role.objects.filter(pk=pk, organization=self.authz.organization).first()
        if role is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        versions = list(role.versions.select_related("changed_by").order_by("-version"))
        out = []
        for i, v in enumerate(versions):
            prev = versions[i + 1].snapshot if i + 1 < len(versions) else {}
            out.append({"version": v.version, "at": v.created_at, "by": v.changed_by.full_name if v.changed_by_id else None, "reason": v.reason,
                        "affected_users": v.affected_users, "changes": gov.diff_versions(prev, v.snapshot)})
        return Response({"role": role.name, "current": role.version, "results": out})


# --- Packages -----------------------------------------------------------------------------------------------------
def _pkg(p: AccessPackage):
    return {"id": str(p.pk), "key": p.key, "name": p.name, "description": p.description, "requestable": p.requestable, "max_days": p.max_days,
            "is_active": p.is_active, "roles": [{"id": str(r.pk), "name": r.name} for r in p.roles.all()]}


class PackagesView(OSView):
    permissions = {"GET": "access.package.view", "POST": "access.package.manage"}

    def get(self, request):
        return Response({"results": [_pkg(p) for p in AccessPackage.objects.filter(organization=self.authz.organization).prefetch_related("roles")]})

    def post(self, request):
        ctx, d = self.authz, request.data
        name = str(d.get("name", "")).strip()
        roles = list(Role.objects.filter(organization=ctx.organization, pk__in=d.get("role_ids") or [], is_active=True))
        if len(name) < 3 or not roles:
            raise DomainError("Name the package and choose at least one role.", code="validation_error")
        key = slugify(name)[:60]
        if AccessPackage.objects.filter(organization=ctx.organization, key=key).exists():
            raise DomainError("A package with this name exists.", code="validation_error", details={"name": ["Must be unique."]})
        p = AccessPackage.objects.create(organization=ctx.organization, key=key, name=name[:120], description=str(d.get("description", ""))[:300],
                                         requestable=bool(d.get("requestable", True)), max_days=int(d["max_days"]) if d.get("max_days") else None,
                                         created_by=request.user)
        p.roles.set(roles)
        record(request, "access.package.create", category="access", module="access", resource=p, new={"roles": [r.key for r in roles]})
        return Response(_pkg(p), status=status.HTTP_201_CREATED)


class PackageDetailView(OSView):
    permissions = {"PATCH": "access.package.manage"}

    def patch(self, request, pk):
        ctx, d = self.authz, request.data
        p = AccessPackage.objects.filter(pk=pk, organization=ctx.organization).first()
        if p is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        for f in ("name", "description"):
            if f in d:
                setattr(p, f, str(d[f])[:300])
        for f in ("requestable", "is_active"):
            if f in d:
                setattr(p, f, bool(d[f]))
        if "max_days" in d:
            p.max_days = int(d["max_days"]) if d["max_days"] else None
        p.save()
        if "role_ids" in d:
            p.roles.set(Role.objects.filter(organization=ctx.organization, pk__in=d["role_ids"] or []))
        record(request, "access.package.update", category="access", module="access", resource=p)
        return Response(_pkg(p))


class PackageAssignView(OSView):
    permissions = {"POST": "access.role.assign"}

    def post(self, request, pk):
        ctx, d = self.authz, request.data
        p = AccessPackage.objects.filter(pk=pk, organization=ctx.organization, is_active=True).first()
        if p is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        acct = _account_or_404(ctx, d.get("account_id"), "access.role.assign")
        if acct.user_id == request.user.pk:
            raise DomainError("You can’t change your own roles.", code="self_change_denied", status_code=403)
        ctx.require("access.role.assign", **_target_for_user(acct.user))
        until = _dt(d.get("valid_until"), "validUntil")
        if p.max_days:
            cap = timezone.now() + timedelta(days=p.max_days)
            until = min(until, cap) if until else cap
        unit = OrgUnit.objects.filter(pk=d.get("org_unit_id"), organization=ctx.organization).first() if d.get("org_unit_id") else None
        out, warnings = [], []
        from django.db import transaction

        with transaction.atomic():
            for role in p.roles.filter(is_active=True):
                if RoleAssignment.objects.live().filter(user=acct.user, role=role).exists():
                    continue
                a, w = gov.provision(request, org=ctx.organization, user=acct.user, role=role, granted_by=request.user, org_unit=unit,
                                     valid_until=until, note=p.name, actor_ctx=ctx, sod_reason=str(d.get("sod_exception_reason", "")),
                                     source=f"package {p.key}")
                out.append(str(a.pk))
                warnings += w
        return Response({"assigned": len(out), "sodWarnings": warnings}, status=status.HTTP_201_CREATED)


# --- Requests -----------------------------------------------------------------------------------------------------
def _req_row(r: AccessRequest):
    return {"id": str(r.pk), "code": r.code, "requester": r.requester.full_name, "for": r.role.name if r.role_id else (r.package.name if r.package_id else ""),
            "kind": "role" if r.role_id else "package", "reason": r.reason, "status": r.status, "status_label": r.get_status_display(),
            "valid_until": r.valid_until, "approval_id": str(r.approval_id) if r.approval_id else None, "outcome_note": r.outcome_note,
            "created_at": r.created_at, "decided_at": r.decided_at}


class RequestsView(OSView):
    def get(self, request):
        ctx = self.authz
        qs = AccessRequest.objects.filter(organization=ctx.organization).select_related("requester", "role", "package")
        if request.query_params.get("view") == "all":
            ctx.require("access.request.view")
            scope = ctx.scope("access.request.view")
            if not scope.org_wide:
                qs = qs.filter(Q(requester__in=scope.report_user_ids) | Q(requester=request.user))
        else:
            qs = qs.filter(requester=request.user)
        if st := request.query_params.get("status"):
            qs = qs.filter(status=st)
        return Response({"results": [_req_row(r) for r in qs[:200]]})

    def post(self, request):
        ctx, d = self.authz, request.data
        ctx.require("access.request.create")
        role = Role.objects.filter(pk=d.get("role_id"), organization=ctx.organization, is_active=True).first() if d.get("role_id") else None
        package = AccessPackage.objects.filter(pk=d.get("package_id"), organization=ctx.organization, is_active=True).first() if d.get("package_id") else None
        unit = OrgUnit.objects.filter(pk=d.get("org_unit_id"), organization=ctx.organization).first() if d.get("org_unit_id") else None
        dept = Department.objects.filter(pk=d.get("department_id"), organization=ctx.organization).first() if d.get("department_id") else None
        ar = gov.submit_access_request(request, ctx, role=role, package=package, reason=str(d.get("reason", "")),
                                       valid_until=_dt(d.get("valid_until"), "validUntil"), org_unit=unit, department=dept)
        return Response(_req_row(ar), status=status.HTTP_201_CREATED)


class RequestableView(OSView):
    def get(self, request):
        ctx = self.authz
        held = set(RoleAssignment.objects.live().filter(user=request.user).values_list("role_id", flat=True))
        roles = Role.objects.filter(organization=ctx.organization, is_active=True, audience__in=["any", ctx.kind]) \
            .exclude(key__in=["people-manager"]).exclude(pk__in=held)
        return Response({"roles": [{"id": str(r.pk), "name": r.name, "description": r.description, "sensitive": r.requires_mfa} for r in roles],
                         "packages": [_pkg(p) for p in AccessPackage.objects.filter(organization=ctx.organization, is_active=True, requestable=True)
                                      .prefetch_related("roles")]})


# --- Reviews ------------------------------------------------------------------------------------------------------
class ReviewsView(OSView):
    def get(self, request):
        ctx = self.authz
        mine = AccessReviewItem.objects.filter(reviewer=request.user, decision="pending").select_related(
            "review", "assignment__user", "assignment__role", "assignment__org_unit")
        reviews = []
        if ctx.has("access.review.view"):
            for rv in AccessReview.objects.filter(organization=ctx.organization)[:50]:
                items = rv.items
                reviews.append({"id": str(rv.pk), "name": rv.name, "kind": rv.kind, "status": rv.status, "due_on": rv.due_on, "total": items.count(),
                                "pending": items.filter(decision="pending").count(), "removed": items.filter(decision="remove").count(),
                                "created_at": rv.created_at})
        return Response({"mine": [_item(i) for i in mine[:200]], "reviews": reviews, "can_launch": ctx.has("access.review.manage")})

    def post(self, request):
        ctx, d = self.authz, request.data
        ctx.require("access.review.manage")
        rv = gov.launch_review(request, ctx, name=str(d.get("name") or "Access certification"), kind=str(d.get("kind") or "periodic"),
                               due_on=parse_date(str(d.get("due_on") or "")) or None, role_ids=d.get("role_ids") or None,
                               privileged_only=bool(d.get("privileged_only")))
        return Response({"id": str(rv.pk), "items": rv.items.count()}, status=status.HTTP_201_CREATED)


def _item(i: AccessReviewItem):
    a = i.assignment
    acct = OSAccount.objects.filter(user=a.user).first()
    return {"id": str(i.pk), "review": i.review.name, "user": a.user.full_name, "account_id": str(acct.pk) if acct else None, "role": a.role.name,
            "anchor": a.org_unit.name if a.org_unit_id else "Own location", "granted_at": a.created_at, "valid_until": a.valid_until,
            "last_login_at": acct.last_login_at if acct else None, "reason": i.reason, "decision": i.decision, "comment": i.comment,
            "due_on": i.review.due_on}


class ReviewDetailView(OSView):
    permissions = {"GET": "access.review.view"}

    def get(self, request, pk):
        rv = AccessReview.objects.filter(pk=pk, organization=self.authz.organization).first()
        if rv is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response({"id": str(rv.pk), "name": rv.name, "status": rv.status,
                         "items": [_item(i) | {"reviewer": i.reviewer.full_name if i.reviewer_id else None,
                                               "decided_by": i.decided_by.full_name if i.decided_by_id else None}
                                   for i in rv.items.select_related("assignment__user", "assignment__role", "assignment__org_unit", "reviewer", "decided_by")]})


class ReviewItemDecideView(OSView):
    def post(self, request, pk):
        item = AccessReviewItem.objects.filter(pk=pk, review__organization=self.authz.organization).select_related(
            "review", "assignment__user", "assignment__role").first()
        if item is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        gov.decide_review_item(request, self.authz, item, str(request.data.get("decision", "")), str(request.data.get("comment", "")))
        return Response(_item(item))


# --- Segregation of duties ----------------------------------------------------------------------------------------
def _rule(r: SoDRule):
    return {"id": str(r.pk), "key": r.key, "name": r.name, "description": r.description, "first": r.first, "second": r.second,
            "severity": r.severity, "is_active": r.is_active}


class SoDView(OSView):
    permissions = {"GET": "access.sod.view", "POST": "access.sod.configure"}

    def get(self, request):
        ctx = self.authz
        violations = []
        for acct in OSAccount.objects.filter(organization=ctx.organization, status="active").select_related("user"):
            from .authz import AuthContext

            c = AuthContext(acct.user, acct)
            for v in gov.sod_conflicts(ctx.organization, [k for k in c.grants if c.has(k)], acct.user):
                violations.append({"account_id": str(acct.pk), "user": acct.user.full_name, **v})
        exc = SoDException.objects.filter(organization=ctx.organization).select_related("rule", "user", "approved_by")[:100]
        return Response({"rules": [_rule(r) for r in SoDRule.objects.filter(organization=ctx.organization)], "violations": violations,
                         "exceptions": [{"id": str(e.pk), "rule": e.rule.name, "user": e.user.full_name, "reason": e.reason,
                                         "approved_by": e.approved_by.full_name if e.approved_by_id else None, "valid_until": e.valid_until,
                                         "live": e.is_live} for e in exc]})

    def post(self, request):
        ctx, d = self.authz, request.data
        name = str(d.get("name", "")).strip()
        first, second = [str(x) for x in d.get("first") or []], [str(x) for x in d.get("second") or []]
        if len(name) < 3 or not first or not second or d.get("severity") not in SoDRule.Severity.values:
            raise DomainError("Name the rule, list both sides and choose a severity.", code="validation_error")
        r = SoDRule.objects.create(organization=ctx.organization, key=slugify(name)[:60], name=name[:160], description=str(d.get("description", ""))[:300],
                                   first=first, second=second, severity=d["severity"])
        record(request, "access.sod.rule_create", category="config", module="access", resource=r, new=_rule(r))
        return Response(_rule(r), status=status.HTTP_201_CREATED)


class SoDRuleDetailView(OSView):
    permissions = {"PATCH": "access.sod.configure"}

    def patch(self, request, pk):
        r = SoDRule.objects.filter(pk=pk, organization=self.authz.organization).first()
        if r is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        before = _rule(r)
        if request.data.get("severity") in SoDRule.Severity.values:
            r.severity = request.data["severity"]
        if "is_active" in request.data:
            r.is_active = bool(request.data["is_active"])
        r.save()
        record(request, "access.sod.rule_update", category="config", module="access", resource=r, old=before, new=_rule(r))
        return Response(_rule(r))


class SoDExceptionRevokeView(OSView):
    permissions = {"POST": "access.sod.approve"}

    def post(self, request, pk):
        e = SoDException.objects.filter(pk=pk, organization=self.authz.organization, revoked_at__isnull=True).first()
        if e is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        e.revoked_at = timezone.now()
        e.save(update_fields=["revoked_at", "updated_at"])
        record(request, "access.sod.exception_revoke", category="access", module="access", resource=e)
        return Response({"revoked": True})


# --- Emergency access ---------------------------------------------------------------------------------------------
def _ea(e: EmergencyAccess):
    return {"id": str(e.pk), "user": e.user.full_name, "role": e.role.name, "reason": e.reason, "starts_at": e.starts_at, "ends_at": e.ends_at,
            "ended_at": e.ended_at, "status": e.status, "reviewed_by": e.reviewed_by.full_name if e.reviewed_by_id else None, "review_note": e.review_note,
            "actions": AuditEvent.objects.filter(actor=e.user, created_at__gte=e.starts_at, created_at__lte=e.ended_at or timezone.now()).count()}


class EmergencyView(OSView):
    def get(self, request):
        ctx = self.authz
        qs = EmergencyAccess.objects.filter(organization=ctx.organization).select_related("user", "role", "reviewed_by")
        if not ctx.has("access.emergency.view"):
            qs = qs.filter(user=request.user)
        eligible = Role.objects.filter(organization=ctx.organization, is_active=True, emergency_eligible=True) if ctx.has("access.emergency.create") else []
        return Response({"results": [_ea(e) for e in qs[:100]], "eligible_roles": [{"id": str(r.pk), "name": r.name} for r in eligible],
                         "max_hours": gov.EMERGENCY_MAX_HOURS, "can_activate": ctx.has("access.emergency.create"),
                         "can_review": ctx.has("access.emergency.manage")})

    def post(self, request):
        ctx, d = self.authz, request.data
        role = Role.objects.filter(pk=d.get("role_id"), organization=ctx.organization).first()
        if role is None:
            raise DomainError("Choose a role.", code="validation_error")
        e = gov.activate_emergency(request, ctx, role=role, reason=str(d.get("reason", "")), hours=int(d.get("hours") or 1))
        return Response(_ea(e), status=status.HTTP_201_CREATED)


class EmergencyActionView(OSView):
    def post(self, request, pk, action):
        ctx = self.authz
        e = EmergencyAccess.objects.filter(pk=pk, organization=ctx.organization).select_related("user", "role").first()
        if e is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if action == "end":
            if e.user_id != request.user.pk:
                ctx.require("access.emergency.manage")
            gov.end_emergency(request, e, actor=request.user, reason=str(request.data.get("reason") or "ended early"))
        elif action == "review":
            ctx.require("access.emergency.manage")
            if e.user_id == request.user.pk:
                raise DomainError("Someone else must review your emergency access.", code="self_change_denied", status_code=403)
            if e.status == EmergencyAccess.Status.ACTIVE:
                raise DomainError("End the emergency access before reviewing it.", code="invalid_state", status_code=409)
            note = str(request.data.get("note", "")).strip()
            if len(note) < 10:
                raise DomainError("Record what you checked.", code="validation_error")
            e.status, e.reviewed_by, e.review_note = EmergencyAccess.Status.REVIEWED, request.user, note[:2000]
            e.save(update_fields=["status", "reviewed_by", "review_note", "updated_at"])
            record(request, "access.emergency.reviewed", category="security", module="access", resource=e, sensitive=True, new={"note": note[:300]})
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response(_ea(e))


# --- Governance lists ---------------------------------------------------------------------------------------------
class PrivilegedView(OSView):
    permissions = {"GET": "access.analysis.view"}

    def get(self, request):
        return Response({"results": gov.privileged(self.authz.organization)})


class HygieneView(OSView):
    permissions = {"GET": "access.analysis.view"}

    def get(self, request):
        org = self.authz.organization
        now = timezone.now()
        from .models import ServiceAccount

        return Response({"orphaned": gov.orphaned(org), "unused_roles": gov.unused_roles(org),
                         "expired_temporary": [{"user": a.user.full_name, "role": a.role.name, "ended": a.valid_until}
                                               for a in RoleAssignment.objects.filter(role__organization=org, is_active=True, valid_until__lte=now)
                                               .select_related("user", "role")[:100]],
                         "unused_service_accounts": [{"id": str(s.pk), "name": s.name, "last_used_at": s.last_used_at}
                                                     for s in ServiceAccount.objects.filter(organization=org, revoked_at__isnull=True)
                                                     .filter(Q(last_used_at__isnull=True) | Q(last_used_at__lt=now - timedelta(days=90)))]})


class SecurityEventsView(OSView):
    permissions = {"GET": "identity.security.view"}

    def get(self, request):
        ctx = self.authz
        since = timezone.now() - timedelta(days=int(request.query_params.get("days") or 7))
        qs = AuditEvent.objects.filter(organization=ctx.organization, category__in=["auth", "security"], created_at__gte=since)
        if request.query_params.get("failures") == "true":
            qs = qs.filter(outcome="failure")
        rows = [{"id": str(e.pk), "action": e.action, "outcome": e.outcome, "actor": e.actor.full_name if e.actor_id else None, "ip": e.ip,
                 "label": e.resource_label, "at": e.created_at} for e in qs.select_related("actor").order_by("-created_at")[:300]]
        failures = qs.filter(outcome="failure")
        by_ip = {}
        for ip in failures.exclude(ip__isnull=True).values_list("ip", flat=True):
            by_ip[ip] = by_ip.get(ip, 0) + 1
        return Response({"results": rows, "failures": failures.count(),
                         "suspicious_ips": [{"ip": k, "failures": v} for k, v in sorted(by_ip.items(), key=lambda x: -x[1]) if v >= 5][:20],
                         "locked": [{"account_id": str(a.pk), "name": a.user.full_name, "until": a.locked_until}
                                    for a in OSAccount.objects.filter(organization=ctx.organization, locked_until__gt=timezone.now()).select_related("user")]})
