"""
Authorization engine: MODULE → RESOURCE → ACTION → SCOPE.

`load_context(user)` resolves everything a request needs once:

    account / employee / organization  →  live role assignments  →  role lineage (inheritance)
      →  grants {permission code: [(scope level, anchor)]}  →  ScopeSet per permission (lazy, cached)

A ScopeSet answers both questions every module asks:
    covers(...)  "may I act on THIS record?"          (detail views, approvals)
    q(...)       "which records may I see at all?"    (querysets: enforced in the database, not the UI)

Rules
- Fail closed: an unresolvable scope (no unit to anchor "region" on) grants nothing.
- Partner accounts are clamped to their own partner business, whatever a role says.
- Sensitive permissions (and roles marked requires_mfa) need MFA when CLICK_OS_SENSITIVE_REQUIRES_MFA is on.
- Every request recomputes from the database, so revoking a role or suspending an account is immediate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from typing import Any

from django.conf import settings
from django.db.models import Q

from apps.core.api.exceptions import DomainError
from apps.organization.models import Department, OrgUnit

from . import registry
from .models import AccountKind, OSAccount, RoleApprovalLimit, RoleAssignment, RolePermission

UNIT_LEVELS = {"business_unit", "region", "state", "city"}


def _id(v):
    return getattr(v, "pk", v)


@dataclass
class ScopeSet:
    organization_id: Any = None
    org_wide: bool = False
    unit_paths: set[str] = field(default_factory=set)
    department_ids: set = field(default_factory=set)
    team_ids: set = field(default_factory=set)
    own: bool = False
    partner_ids: set = field(default_factory=set)
    user_id: Any = None

    @property
    def is_empty(self) -> bool:
        return not (self.org_wide or self.unit_paths or self.department_ids or self.team_ids or self.own or self.partner_ids)

    @property
    def level(self) -> str:
        """Broadest description, for display."""
        if self.org_wide:
            return "organization"
        if self.unit_paths:
            return "units"
        if self.department_ids:
            return "department"
        if self.team_ids:
            return "team"
        if self.partner_ids:
            return "partner"
        return "own" if self.own else "none"

    def covers(self, *, unit=None, department=None, team=None, owner=None, partner=None, organization=None) -> bool:
        """May the holder act on a record with these attributes? Unknown attributes simply don't match."""
        if self.is_empty:
            return False
        if organization is not None and self.organization_id and _id(organization) != self.organization_id:
            return False
        if self.org_wide:
            return True
        if unit is not None and self.unit_paths:
            path = unit.path if isinstance(unit, OrgUnit) else OrgUnit.objects.filter(pk=unit).values_list("path", flat=True).first()
            if path and any(path.startswith(p) for p in self.unit_paths):
                return True
        if department is not None and _id(department) in self.department_ids:
            return True
        if team is not None and _id(team) in self.team_ids:
            return True
        if partner is not None and _id(partner) in self.partner_ids:
            return True
        return bool(self.own and owner is not None and _id(owner) == self.user_id)

    def q(self, *, unit: str | None = "org_unit", department: str | None = None, team: str | None = None,
          owner: str | None = None, partner: str | None = None, organization: str | None = "organization") -> Q:
        """A filter for querysets. Pass the field names the model has; fields set to None are not applicable."""
        if self.is_empty:
            return Q(pk__in=[])
        base = Q(**{organization: self.organization_id}) if organization and self.organization_id else Q()
        if self.org_wide:
            return base
        parts = Q(pk__in=[])
        if unit:
            for p in self.unit_paths:
                parts |= Q(**{f"{unit}__path__startswith": p})
        if department and self.department_ids:
            parts |= Q(**{f"{department}__in": self.department_ids})
        if team and self.team_ids:
            parts |= Q(**{f"{team}__in": self.team_ids})
        if partner and self.partner_ids:
            parts |= Q(**{f"{partner}__in": self.partner_ids})
        if owner and self.own:
            parts |= Q(**{owner: self.user_id})
        return base & parts

    def filter(self, qs, **fields):
        return qs.filter(self.q(**fields))


@dataclass
class Grant:
    level: str
    unit: OrgUnit | None
    department: Department | None
    team_id: Any
    role_key: str


class AuthContext:
    def __init__(self, user, account: OSAccount | None, *, service=None):
        self.user = user
        self.account = account
        self.service = service
        self.employee = getattr(user, "employee", None) if account or service else None
        self.organization = account.organization if account else (service.organization if service else None)
        self.kind = "service" if service else (account.kind if account else None)
        self.roles: list = []
        self.grants: dict[str, list[Grant]] = {}
        self.mfa_blocked: set[str] = set()
        self.limits: dict[str, Decimal | None] = {}
        self._scopes: dict[str, ScopeSet] = {}
        self._unit_cache: dict[str, OrgUnit] = {}
        if account is not None or service is not None:
            self._load()

    # ---- loading ------------------------------------------------------
    @property
    def mfa_ok(self) -> bool:
        if not settings.CLICK_OS_SENSITIVE_REQUIRES_MFA or self.service is not None:
            return True
        return bool(self.account and self.account.mfa_enabled)

    def _load(self) -> None:
        assignments = list(
            RoleAssignment.objects.live().filter(user=self.user, role__organization=self.organization)
            .select_related("role", "role__parent", "org_unit", "department", "team")
        )
        emp = self.employee
        role_ids: dict = {}
        for a in assignments:
            if not self._audience_ok(a.role):
                continue
            self.roles.append(a.role)
            for r in a.role.lineage():
                role_ids.setdefault(r.pk, []).append((a, r))
        grants = RolePermission.objects.filter(role_id__in=role_ids.keys(), permission__is_active=True).select_related("permission")
        for g in grants:
            for a, lineage_role in role_ids[g.role_id]:
                assigned_role = a.role
                code = g.permission.code
                if (g.permission.sensitive or assigned_role.requires_mfa or lineage_role.requires_mfa) and not self.mfa_ok:
                    self.mfa_blocked.add(code)
                    continue
                self.grants.setdefault(code, []).append(Grant(
                    level=g.scope,
                    unit=a.org_unit or (emp.org_unit if emp else None),
                    department=a.department or (emp.department if emp else None),
                    team_id=(a.team_id or (emp.team_id if emp else None)),
                    role_key=assigned_role.key,
                ))
        live_role_ids = {r.pk for r in self.roles} | set(role_ids.keys())
        for lim in RoleApprovalLimit.objects.filter(role_id__in=live_role_ids):
            current = self.limits.get(lim.approval_type, Decimal("0"))
            if lim.max_amount is None or current is None:
                self.limits[lim.approval_type] = None  # unlimited wins
            else:
                self.limits[lim.approval_type] = max(current, lim.max_amount)

    def _audience_ok(self, role) -> bool:
        aud = role.audience
        return aud == "any" or aud == self.kind

    # ---- scope resolution ---------------------------------------------
    def _ancestor(self, unit: OrgUnit, types) -> OrgUnit | None:
        ids = list(reversed(unit.ancestor_ids))  # self first, then upwards
        missing = [i for i in ids if i not in self._unit_cache]
        if missing:
            for u in OrgUnit.objects.filter(pk__in=missing):
                self._unit_cache[str(u.pk)] = u
        for i in ids:
            u = self._unit_cache.get(i)
            if u and u.unit_type in types:
                return u
        return None

    def scope(self, code: str) -> ScopeSet:
        if code in self._scopes:
            return self._scopes[code]
        s = ScopeSet(organization_id=self.organization.pk if self.organization else None, user_id=self.user.pk)
        for g in self.grants.get(code, ()):
            if g.level == "organization":
                s.org_wide = True
            elif g.level in UNIT_LEVELS and g.unit:
                anc = self._ancestor(g.unit, {g.level})
                if anc:
                    s.unit_paths.add(anc.path)
            elif g.level == "branch" and g.unit:
                anc = self._ancestor(g.unit, OrgUnit.SITE_TYPES)
                if anc:
                    s.unit_paths.add(anc.path)
            elif g.level == "department" and g.department:
                s.department_ids |= g.department.descendant_ids()
            elif g.level == "team" and g.team_id:
                s.team_ids.add(g.team_id)
            elif g.level == "own":
                s.own = True
        if self.kind == AccountKind.PARTNER:  # partners never see beyond their own business
            broad = s.org_wide or s.unit_paths or s.department_ids or s.team_ids
            s = ScopeSet(organization_id=s.organization_id, user_id=s.user_id, own=s.own,
                         partner_ids={self.account.partner_id} if broad and self.account.partner_id else set())
        self._scopes[code] = s
        return s

    # ---- questions ----------------------------------------------------
    def has(self, code: str) -> bool:
        return not self.scope(code).is_empty

    def can(self, code: str, **target) -> bool:
        return self.scope(code).covers(**target) if target else self.has(code)

    def require(self, code: str, **target) -> ScopeSet:
        s = self.scope(code)
        if s.is_empty or (target and not s.covers(**target)):
            if code in self.mfa_blocked:
                raise DomainError("Turn on two-step verification to use this. Go to Settings → Security.", code="mfa_required", status_code=403)
            raise DomainError("You don’t have permission to do this.", code="permission_denied", status_code=403)
        return s

    def has_module(self, module_key: str) -> bool:
        prefix = f"{module_key}."
        return any(code.startswith(prefix) and self.has(code) for code in self.grants)

    def sees_in_navigation(self, module: "registry.Module") -> bool:
        if module.nav_requires:
            return any(self.has(c) for c in module.nav_requires)
        return self.has_module(module.key)

    def approval_authority(self, approval_type: str) -> tuple[bool, Decimal | None]:
        """(has authority, max amount or None for unlimited)."""
        if approval_type not in self.limits:
            return False, Decimal("0")
        return True, self.limits[approval_type]

    def within_limit(self, approval_type: str, amount) -> bool:
        if amount is None:
            return True
        ok, cap = self.approval_authority(approval_type)
        if approval_type == "general" and not ok:
            return True  # policies without a monetary authority rely on the approver permission alone
        return ok and (cap is None or Decimal(amount) <= cap)

    @cached_property
    def permission_codes(self) -> list[str]:
        return sorted(c for c in self.grants if self.has(c))

    def scope_summary(self) -> dict[str, str]:
        return {c: self.scope(c).level for c in self.permission_codes}

    @property
    def is_admin(self) -> bool:
        return any(registry.is_admin_code(c) and self.has(c) for c in self.grants)


def load_context(user) -> AuthContext:
    account = OSAccount.objects.select_related("organization").filter(user=user).first()
    return AuthContext(user, account)


def context_for(request) -> AuthContext:
    """Cached per request. Views always go through this, never through the user object directly."""
    ctx = getattr(request, "_os_authz", None)
    if ctx is None:
        service = getattr(request, "os_service_account", None)
        if service is not None:
            ctx = AuthContext(request.user, None, service=service)
        else:
            ctx = load_context(request.user)
        request._os_authz = ctx
    return ctx


def holders_of(code: str, org, **target) -> list:
    """Users whose effective permissions cover `target` for `code` (e.g. who can approve this request)."""
    from apps.users.models import User

    perm_roles = set(RolePermission.objects.filter(permission__code=code).values_list("role_id", flat=True))
    if not perm_roles:
        return []
    from .models import Role

    # roles granting the permission directly or through a parent
    all_roles = list(Role.objects.filter(organization=org, is_active=True).select_related("parent"))
    role_ids = {r.pk for r in all_roles if any(x.pk in perm_roles for x in r.lineage())}
    user_ids = set(RoleAssignment.objects.live().filter(role_id__in=role_ids).values_list("user_id", flat=True))
    out = []
    for user in User.objects.filter(pk__in=user_ids, is_active=True, os_account__status=OSAccount.Status.ACTIVE):
        ctx = load_context(user)
        if ctx.can(code, **target) if target else ctx.has(code):
            out.append(user)
    return out
