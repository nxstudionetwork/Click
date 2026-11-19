"""
Identity & access administration: accounts, invitations, suspension, role assignment, roles, service accounts.

Anti-escalation rules (server-side, whatever the UI shows):
- Nobody changes their own roles or status.
- You can only grant (in a role you edit, or by assigning a role) permissions you hold yourself; an
  organization-wide grant needs your own organization-wide grant of that permission.
- Assigning needs access.role.assign covering the person (their location / department).
- System roles are read-only templates: duplicate to customise.
"""

from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from rest_framework import status
from rest_framework.response import Response

from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.organization.models import Department, OrgUnit, Team
from apps.people.models import Employee
from apps.users.models import User
from apps.workspace.notify import notify

from . import registry
from .api import OSView
from .auth_views import invite_token
from .authz import AuthContext
from .models import AccountKind, OSAccount, OSSession, Permission, Role, RoleApprovalLimit, RoleAssignment, RolePermission, ServiceAccount
from .serializers import AccountListSerializer, AssignmentSerializer, RoleListSerializer, RoleWriteSerializer
from .sessions import revoke_all


def _target_for_user(user) -> dict:
    emp = getattr(user, "employee", None)
    t = {"owner": user.pk}
    if emp:
        if emp.org_unit_id:
            t["unit"] = emp.org_unit_id
        if emp.department_id:
            t["department"] = emp.department_id
        if emp.team_id:
            t["team"] = emp.team_id
    return t


def _scoped_accounts(ctx: AuthContext, code: str):
    qs = OSAccount.objects.filter(organization=ctx.organization)
    scope = ctx.scope(code)
    if scope.org_wide:
        return qs
    return qs.filter(scope.q(unit="user__employee__org_unit", department="user__employee__department",
                             team="user__employee__team", owner="user", partner="partner", organization=None))


def _account_or_404(ctx, pk, code="identity.user.view") -> OSAccount:
    acct = _scoped_accounts(ctx, code).select_related("user", "organization").filter(pk=pk).first()
    if acct is None:
        raise DomainError("Not found.", code="not_found", status_code=404)
    return acct


def _role_codes_with_scope(role: Role) -> list[tuple[str, str]]:
    lineage = role.lineage()
    return list(RolePermission.objects.filter(role__in=lineage).values_list("permission__code", "scope"))


def assert_can_grant(ctx: AuthContext, grants: list[tuple[str, str]]) -> None:
    missing = []
    for code, scope in grants:
        s = ctx.scope(code)
        if s.is_empty or (scope == "organization" and not s.org_wide):
            missing.append(code)
    if missing:
        raise DomainError("You can only grant permissions you hold yourself (at the same breadth).", code="escalation_denied",
                          status_code=403, details={"permissions": sorted(set(missing))[:20]})


# --- Accounts -----------------------------------------------------------------------
class UsersView(OSView):
    permissions = {"GET": "identity.user.view", "POST": "identity.user.create"}

    def get(self, request):
        qs = _scoped_accounts(self.authz, "identity.user.view").select_related("user", "user__employee__designation",
                                                                              "user__employee__department", "user__employee__org_unit")
        qs = qs.prefetch_related("user__role_assignments__role")
        p = request.query_params
        if q := p.get("q", "").strip():
            qs = qs.filter(Q(user__full_name__icontains=q) | Q(user__email__icontains=q) | Q(user__employee__employee_id__iexact=q))
        if p.get("status") in OSAccount.Status.values:
            qs = qs.filter(status=p["status"])
        if p.get("kind") in AccountKind.values:
            qs = qs.filter(kind=p["kind"])
        if p.get("locked") == "true":
            qs = qs.filter(locked_until__gt=timezone.now())
        resp = self.paginate(qs.order_by("user__full_name"), AccountListSerializer)
        base = _scoped_accounts(self.authz, "identity.user.view")
        resp.data["counts"] = {s: base.filter(status=s).count() for s in OSAccount.Status.values}
        return resp

    def post(self, request):
        ctx, d = self.authz, request.data
        email = str(d.get("email", "")).strip().lower()
        name = " ".join(str(d.get("full_name", "")).split())
        kind = d.get("kind", AccountKind.EMPLOYEE)
        errors = {}
        if "@" not in email:
            errors["email"] = ["Enter a work email."]
        if len(name) < 2:
            errors["fullName"] = ["Enter the person’s name."]
        if kind not in AccountKind.values:
            errors["kind"] = ["Choose an account type."]
        emp = partner = None
        if d.get("employee_id"):
            emp = Employee.objects.filter(pk=d["employee_id"], organization=ctx.organization).select_related("user").first()
            if emp is None:
                errors["employeeId"] = ["Unknown employee record."]
            elif emp.user_id and hasattr(emp.user, "os_account"):
                errors["employeeId"] = ["This employee already has an account."]
        if kind == AccountKind.PARTNER:
            from apps.partners.models import Partner

            partner = Partner.objects.filter(pk=d.get("partner_id")).first()
            if partner is None:
                errors["partnerId"] = ["Choose the partner business this login acts for."]
        if errors:
            raise DomainError("Please check the highlighted fields.", code="validation_error", details=errors)
        if emp is not None:
            ctx.require("identity.user.create", **{k: v for k, v in {"unit": emp.org_unit_id, "department": emp.department_id}.items() if v})
        with transaction.atomic():
            user = User.objects.filter(email__iexact=email).first()
            if user and hasattr(user, "os_account"):
                raise DomainError("This person already has a Business OS account.", code="validation_error", details={"email": ["Already has an account."]})
            if user is None:
                user = User.objects.create_user(email, None, full_name=name)  # unusable until they accept the invitation
                user.set_unusable_password()
                user.save(update_fields=["password"])
            if emp is not None and emp.user_id is None:
                emp.user = user
                emp.save(update_fields=["user", "updated_at"])
            account = OSAccount.objects.create(user=user, organization=ctx.organization, kind=kind, status=OSAccount.Status.INVITED,
                                               partner=partner, external_org_name=str(d.get("external_org_name", ""))[:150],
                                               invited_by=request.user, invited_at=timezone.now())
        record(request, "identity.user.invited", category="security", module="identity", resource=account,
               new={"email": email, "kind": kind, "employee": str(emp.pk) if emp else None})
        return Response({**AccountListSerializer(account).data, "invite_url": f"/invite/{invite_token(account)}",
                         "invite_expires_days": 7}, status=status.HTTP_201_CREATED)


class UserDetailView(OSView):
    permissions = {"GET": "identity.user.view"}

    def get(self, request, pk):
        ctx = self.authz
        acct = _account_or_404(ctx, pk)
        data = AccountListSerializer(acct).data
        data["assignments"] = AssignmentSerializer(
            RoleAssignment.objects.filter(user=acct.user, is_active=True).select_related("role", "org_unit", "department", "team", "granted_by"),
            many=True).data
        data["sessions"] = OSSession.objects.filter(user=acct.user, revoked_at__isnull=True, expires_at__gt=timezone.now()).count()
        data["locked_until"] = acct.locked_until
        data["invited_at"] = acct.invited_at
        data["partner"] = {"id": str(acct.partner_id), "name": acct.partner.business_name} if acct.partner_id else None
        data["is_self"] = acct.user_id == request.user.pk
        data["can_manage"] = ctx.can("identity.user.manage", **_target_for_user(acct.user)) and not data["is_self"]
        data["can_assign"] = ctx.can("access.role.assign", **_target_for_user(acct.user)) and not data["is_self"]
        if ctx.has("audit.event.view"):
            data["recent_activity"] = [{"action": e.action, "outcome": e.outcome, "at": e.created_at, "ip": e.ip}
                                       for e in AuditEvent.objects.filter(actor=acct.user, sensitive=False).order_by("-created_at")[:10]]
        return Response(data)


class UserStatusView(OSView):
    permissions = {"POST": "identity.user.manage"}

    def post(self, request, pk):
        ctx = self.authz
        acct = _account_or_404(ctx, pk, "identity.user.manage")
        if acct.user_id == request.user.pk:
            raise DomainError("You can’t change your own account status.", code="self_change_denied", status_code=403)
        ctx.require("identity.user.manage", **_target_for_user(acct.user))
        action = request.data.get("action")
        before = {"status": acct.status, "locked_until": acct.locked_until}
        extra = {}
        if action == "suspend":
            acct.status = OSAccount.Status.SUSPENDED
            extra["sessions_ended"] = revoke_all(acct.user, "suspended")
        elif action == "reactivate":
            if acct.status not in (OSAccount.Status.SUSPENDED, OSAccount.Status.DEACTIVATED):
                raise DomainError("Only suspended accounts can be reactivated.", code="invalid_state", status_code=409)
            acct.status = OSAccount.Status.ACTIVE if acct.user.has_usable_password() else OSAccount.Status.INVITED
        elif action == "unlock":
            acct.locked_until, acct.failed_attempts = None, 0
        elif action == "sign_out_everywhere":
            extra["sessions_ended"] = revoke_all(acct.user, "admin_sign_out")
        elif action == "resend_invite":
            if acct.status != OSAccount.Status.INVITED:
                raise DomainError("This person already accepted their invitation.", code="invalid_state", status_code=409)
            acct.invited_at = timezone.now()  # invalidates earlier links
            extra["invite_url"] = None
        else:
            raise DomainError("Unknown action.", code="validation_error")
        acct.save()
        acct.bump_access()
        if action == "resend_invite":
            extra["invite_url"] = f"/invite/{invite_token(acct)}"
        record(request, f"identity.user.{action}", category="security", module="identity", resource=acct, old=before,
               new={"status": acct.status, "locked_until": acct.locked_until})
        if action == "suspend":
            notify(acct.user, "security", "Your Click Business OS access was suspended", priority="critical")
        return Response({**AccountListSerializer(acct).data, **extra})


class UserRolesView(OSView):
    permissions = {"POST": "access.role.assign"}

    def post(self, request, pk):
        ctx, d = self.authz, request.data
        acct = _account_or_404(ctx, pk, "access.role.assign")
        if acct.user_id == request.user.pk:
            raise DomainError("You can’t change your own roles. Ask another administrator.", code="self_change_denied", status_code=403)
        ctx.require("access.role.assign", **_target_for_user(acct.user))
        role = Role.objects.filter(pk=d.get("role_id"), organization=ctx.organization, is_active=True).first()
        if role is None:
            raise DomainError("Choose a role.", code="validation_error", details={"roleId": ["Choose a role."]})
        if role.audience not in ("any", acct.kind):
            raise DomainError(f"“{role.name}” is for {role.get_audience_display().lower()}, not this account type.", code="validation_error",
                              details={"roleId": ["Wrong account type for this role."]})
        assert_can_grant(ctx, _role_codes_with_scope(role))
        unit = OrgUnit.objects.filter(pk=d["org_unit_id"], organization=ctx.organization).first() if d.get("org_unit_id") else None
        dept = Department.objects.filter(pk=d["department_id"], organization=ctx.organization).first() if d.get("department_id") else None
        team = Team.objects.filter(pk=d["team_id"], department__organization=ctx.organization).first() if d.get("team_id") else None
        until = parse_datetime(str(d["valid_until"])) if d.get("valid_until") else None
        if until and until <= timezone.now():
            raise DomainError("The end date must be in the future.", code="validation_error", details={"validUntil": ["Must be in the future."]})
        a = RoleAssignment.objects.create(user=acct.user, role=role, org_unit=unit, department=dept, team=team, valid_until=until,
                                          granted_by=request.user, note=str(d.get("note", ""))[:200])
        acct.bump_access()
        record(request, "access.role.assigned", category="access", module="access", resource=acct, resource_label=str(acct.user),
               new={"role": role.key, "unit": unit.code if unit else None, "department": dept.code if dept else None, "valid_until": until})
        notify(acct.user, "security", f"You were given the {role.name} role", body=f"By {request.user.full_name}", link="/profile")
        return Response(AssignmentSerializer(a).data, status=status.HTTP_201_CREATED)


class UserRoleDetailView(OSView):
    permissions = {"DELETE": "access.role.assign"}

    def delete(self, request, pk, assignment_id):
        ctx = self.authz
        acct = _account_or_404(ctx, pk, "access.role.assign")
        if acct.user_id == request.user.pk:
            raise DomainError("You can’t change your own roles.", code="self_change_denied", status_code=403)
        ctx.require("access.role.assign", **_target_for_user(acct.user))
        a = RoleAssignment.objects.filter(pk=assignment_id, user=acct.user, is_active=True).select_related("role").first()
        if a is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        a.is_active = False
        a.save(update_fields=["is_active", "updated_at"])
        acct.bump_access()
        record(request, "access.role.revoked", category="access", module="access", resource=acct, resource_label=str(acct.user),
               old={"role": a.role.key})
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Roles -----------------------------------------------------------------------------
def role_detail(role: Role, ctx: AuthContext) -> dict:
    grants = list(role.grants.select_related("permission").order_by("permission__code"))
    inherited = []
    for parent in role.lineage()[1:]:
        inherited += [{"code": g.permission.code, "scope": g.scope, "from": parent.name} for g in parent.grants.select_related("permission")]
    holders = RoleAssignment.objects.live().filter(role=role).select_related("user", "org_unit", "department")
    return {
        **RoleListSerializer(Role.objects.annotate(permission_count=Count("grants", distinct=True),
                                                    holder_count=Count("assignments", filter=Q(assignments__is_active=True), distinct=True)).get(pk=role.pk)).data,
        "home_widgets": role.home_widgets,
        "grants": [{"code": g.permission.code, "scope": g.scope, "sensitive": g.permission.sensitive} for g in grants],
        "inherited": inherited,
        "approval_limits": [{"approval_type": lim.approval_type, "max_amount": str(lim.max_amount) if lim.max_amount is not None else None,
                             "currency": lim.currency} for lim in role.approval_limits.all()],
        "holders": [{"user_id": str(a.user_id), "full_name": a.user.full_name, "org_unit": a.org_unit.name if a.org_unit_id else None,
                     "department": a.department.name if a.department_id else None} for a in holders[:100]],
        "can_edit": not role.is_system and ctx.has("access.role.edit"),
        "can_delete": not role.is_system and ctx.has("access.role.delete") and not holders.exists(),
    }


def _apply_role(ctx: AuthContext, role: Role, data: dict, *, creating: bool) -> None:
    if "grants" in data:
        grants = [(g["code"], g["scope"]) for g in data["grants"]]
        unknown = [c for c, _ in grants if not registry.is_known(c)]
        if unknown:
            raise DomainError("Unknown permissions.", code="validation_error", details={"grants": unknown[:20]})
        assert_can_grant(ctx, grants)
    if "approval_limits" in data:
        bad = [lim["approval_type"] for lim in data["approval_limits"] if lim["approval_type"] not in registry.APPROVAL_TYPES]
        if bad:
            raise DomainError("Unknown approval types.", code="validation_error", details={"approvalLimits": bad})
    if data.get("home_widgets") is not None:
        from apps.workspace.widgets import WIDGETS

        data["home_widgets"] = [w for w in data["home_widgets"] if w in WIDGETS]
    parent = None
    if data.get("parent_id"):
        parent = Role.objects.filter(pk=data["parent_id"], organization=ctx.organization).first()
        if parent is None or (role.pk and role.pk in {r.pk for r in parent.lineage()}):
            raise DomainError("Choose a valid parent role.", code="validation_error", details={"parentId": ["Invalid parent."]})
        assert_can_grant(ctx, _role_codes_with_scope(parent))
    for f in ("name", "description", "audience", "requires_mfa", "priority", "home_widgets"):
        if f in data:
            setattr(role, f, data[f])
    if "parent_id" in data:
        role.parent = parent
    role.save()
    if "grants" in data:
        role.grants.all().delete()
        perms = {p.code: p for p in Permission.objects.filter(code__in=[g["code"] for g in data["grants"]])}
        RolePermission.objects.bulk_create([RolePermission(role=role, permission=perms[g["code"]], scope=g["scope"]) for g in data["grants"]])
    if "approval_limits" in data:
        role.approval_limits.all().delete()
        RoleApprovalLimit.objects.bulk_create([RoleApprovalLimit(role=role, approval_type=lim["approval_type"], max_amount=lim.get("max_amount"),
                                                                 currency=lim.get("currency") or "INR") for lim in data["approval_limits"]])
    if not creating:
        OSAccount.objects.filter(user__role_assignments__role=role).update(access_version=F("access_version") + 1)


class RolesView(OSView):
    permissions = {"GET": "access.role.view", "POST": "access.role.create"}

    def get(self, request):
        qs = Role.objects.filter(organization=self.authz.organization).select_related("parent").annotate(
            permission_count=Count("grants", distinct=True),
            holder_count=Count("assignments", filter=Q(assignments__is_active=True), distinct=True))
        return Response({"results": RoleListSerializer(qs, many=True).data})

    def post(self, request):
        ctx = self.authz
        s = RoleWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        key = data.pop("key", None) or slugify(data["name"])[:60]
        if Role.objects.filter(organization=ctx.organization, key=key).exists():
            raise DomainError("A role with this key already exists.", code="validation_error", details={"key": ["Must be unique."]})
        with transaction.atomic():
            role = Role(organization=ctx.organization, key=key, name=data["name"])
            _apply_role(ctx, role, data, creating=True)
        record(request, "access.role.create", category="access", module="access", resource=role,
               new={"grants": data.get("grants", []), "approval_limits": data.get("approval_limits", [])})
        return Response(role_detail(role, ctx), status=status.HTTP_201_CREATED)


class RoleDetailView(OSView):
    permissions = {"GET": "access.role.view", "PATCH": "access.role.edit", "DELETE": "access.role.delete"}

    def _role(self, pk) -> Role:
        role = Role.objects.filter(pk=pk, organization=self.authz.organization).select_related("parent").first()
        if role is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return role

    def get(self, request, pk):
        return Response(role_detail(self._role(pk), self.authz))

    def patch(self, request, pk):
        ctx, role = self.authz, self._role(pk)
        if role.is_system:
            raise DomainError("System roles are read-only. Duplicate it to make your own version.", code="system_role", status_code=403)
        if RoleAssignment.objects.live().filter(role=role, user=request.user).exists() and "grants" in request.data:
            raise DomainError("You can’t change the permissions of a role you hold.", code="self_change_denied", status_code=403)
        before = role_detail(role, ctx)
        s = RoleWriteSerializer(data={"name": role.name, **request.data}, partial=True)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            _apply_role(ctx, role, dict(s.validated_data), creating=False)
        after = role_detail(role, ctx)
        record(request, "access.role.update", category="access", module="access", resource=role,
               old={k: before[k] for k in ("name", "grants", "approval_limits", "requires_mfa")},
               new={k: after[k] for k in ("name", "grants", "approval_limits", "requires_mfa")})
        return Response(after)

    def delete(self, request, pk):
        role = self._role(pk)
        if role.is_system:
            raise DomainError("System roles can’t be deleted.", code="system_role", status_code=403)
        if RoleAssignment.objects.filter(role=role, is_active=True).exists():
            raise DomainError("Remove this role from everyone who holds it first.", code="role_in_use", status_code=409)
        record(request, "access.role.delete", category="access", module="access", resource=role, old={"key": role.key})
        role.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoleDuplicateView(OSView):
    permissions = {"POST": "access.role.create"}

    def post(self, request, pk):
        ctx = self.authz
        src = Role.objects.filter(pk=pk, organization=ctx.organization).first()
        if src is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        grants = [(g.permission.code, g.scope) for g in src.grants.select_related("permission")]
        assert_can_grant(ctx, grants + (_role_codes_with_scope(src.parent) if src.parent_id else []))
        base, n = f"{src.key}-copy", 1
        key = base
        while Role.objects.filter(organization=ctx.organization, key=key).exists():
            n += 1
            key = f"{base}-{n}"
        with transaction.atomic():
            role = Role.objects.create(organization=ctx.organization, key=key, name=f"{src.name} (copy)", description=src.description,
                                       parent=src.parent, audience=src.audience, requires_mfa=src.requires_mfa, home_widgets=src.home_widgets,
                                       priority=src.priority)
            RolePermission.objects.bulk_create([RolePermission(role=role, permission=g.permission, scope=g.scope) for g in src.grants.all()])
            RoleApprovalLimit.objects.bulk_create([RoleApprovalLimit(role=role, approval_type=lim.approval_type, max_amount=lim.max_amount,
                                                                     currency=lim.currency) for lim in src.approval_limits.all()])
        record(request, "access.role.duplicate", category="access", module="access", resource=role, metadata={"from": src.key})
        return Response(role_detail(role, ctx), status=status.HTTP_201_CREATED)


class PermissionCatalogView(OSView):
    permissions = {"GET": "access.role.view"}

    def get(self, request):
        from apps.workspace.widgets import WIDGETS

        ctx = self.authz
        return Response({
            "groups": [{"key": k, "label": v} for k, v in registry.GROUPS],
            "modules": [{"key": m.key, "label": m.label, "group": m.group, "status": m.status,
                         "resources": [{"key": r.key, "label": r.label, "sensitive": r.sensitive,
                                        "actions": [{"action": a, "code": f"{m.key}.{r.key}.{a}", "you_hold": ctx.scope(f"{m.key}.{r.key}.{a}").level}
                                                    for a in r.actions]} for r in m.resources]}
                        for m in registry.MODULES if m.resources],
            "scopes": [{"key": s, "label": registry.SCOPE_LABELS[s]} for s in registry.SCOPES],
            "approval_types": [{"key": k, "label": v} for k, v in registry.APPROVAL_TYPES.items()],
            "audiences": [{"key": k, "label": v} for k, v in Role.Audience.choices],
            "widgets": [{"key": w.key, "title": w.title, "permission": w.permission} for w in WIDGETS.values()],
        })


# --- Service accounts -------------------------------------------------------------------
class ServiceAccountsView(OSView):
    permissions = {"GET": "identity.service_account.view", "POST": "identity.service_account.manage"}

    def get(self, request):
        qs = ServiceAccount.objects.filter(organization=self.authz.organization)
        return Response({"results": [{"id": str(s.pk), "name": s.name, "description": s.description, "key_prefix": s.key_prefix,
                                      "usable": s.is_usable, "last_used_at": s.last_used_at, "expires_at": s.expires_at,
                                      "revoked_at": s.revoked_at, "created_at": s.created_at} for s in qs]})

    def post(self, request):
        name = str(request.data.get("name", "")).strip()
        if len(name) < 3:
            raise DomainError("Name the integration this key is for.", code="validation_error", details={"name": ["Too short."]})
        expires = parse_datetime(str(request.data.get("expires_at") or "")) if request.data.get("expires_at") else None
        acct, key = ServiceAccount.issue(organization=self.authz.organization, name=name[:120], created_by=request.user,
                                         description=str(request.data.get("description", ""))[:300], expires_at=expires)
        record(request, "identity.service_account.create", category="security", module="identity", resource=acct, sensitive=True)
        return Response({"id": str(acct.pk), "name": acct.name, "key": key,
                         "note": "Copy this key now. It is shown once and can’t be recovered. Give it roles from the Users area."},
                        status=status.HTTP_201_CREATED)


class ServiceAccountDetailView(OSView):
    permissions = {"DELETE": "identity.service_account.manage"}

    def delete(self, request, pk):
        s = ServiceAccount.objects.filter(pk=pk, organization=self.authz.organization, revoked_at__isnull=True).first()
        if s is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        s.revoked_at = timezone.now()
        s.save(update_fields=["revoked_at", "updated_at"])
        record(request, "identity.service_account.revoke", category="security", module="identity", resource=s, sensitive=True)
        return Response(status=status.HTTP_204_NO_CONTENT)

