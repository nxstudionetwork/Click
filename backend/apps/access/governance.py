"""
Identity & Access governance (Module 3) on top of the one authorization engine in authz.py.

Everything that grants access goes through `provision()`:
    admin assignment · access package · approved access request · emergency (break-glass) access
so anti-escalation, segregation of duties, audit and notifications are applied the same way every time.

Read-only analysis answers the questions administrators actually ask:
    effective_access(user)   "what can this person actually do, and why?"
    who_has(code)            "who can approve refunds?"
    simulate(user, code, …)  "would this be allowed — and why not?"
    compare_roles(roles)     "how do these roles differ?"
    risk(account)            an internal review indicator (not a recognised security score)
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from fnmatch import fnmatch

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.workspace.notify import notify, notify_many

from . import registry
from .authz import AuthContext, holders_of, load_context
from .models import (AccessPackage, AccessRequest, AccessReview, AccessReviewItem, EmergencyAccess, OSAccount, Role, RoleApprovalLimit,
                     RoleAssignment, RolePermission, RoleVersion, ServiceAccount, SoDException, SoDRule)
from .sessions import revoke_all

EMERGENCY_MAX_HOURS = 8
DORMANT_DAYS = 90


# --------------------------------------------------------------------------------------------------------------------
# Role helpers
# --------------------------------------------------------------------------------------------------------------------
def role_codes(role: Role) -> list[tuple[str, str]]:
    """(code, scope) for the role and everything it inherits."""
    return list(RolePermission.objects.filter(role__in=role.lineage(), permission__is_active=True).values_list("permission__code", "scope"))


def snapshot_role(role: Role, user=None, reason: str = "") -> RoleVersion:
    role.refresh_from_db()
    last = role.versions.order_by("-version").first()
    n = (last.version + 1) if last else 1
    snap = {
        "name": role.name, "parent": role.parent.key if role.parent_id else None, "audience": role.audience, "requires_mfa": role.requires_mfa,
        "grants": sorted([[g.permission.code, g.scope] for g in role.grants.select_related("permission")]),
        "limits": sorted([[lim.approval_type, str(lim.max_amount) if lim.max_amount is not None else None] for lim in role.approval_limits.all()]),
    }
    if last and last.snapshot == snap:
        return last
    v = RoleVersion.objects.create(role=role, version=n, snapshot=snap, changed_by=user, reason=reason[:300],
                                   affected_users=RoleAssignment.objects.live().filter(role=role).values("user").distinct().count())
    Role.objects.filter(pk=role.pk).update(version=n)
    return v


def diff_versions(a: dict, b: dict) -> dict:
    ga, gb = {tuple(x) for x in a.get("grants", [])}, {tuple(x) for x in b.get("grants", [])}
    la, lb = {tuple(x) for x in a.get("limits", [])}, {tuple(x) for x in b.get("limits", [])}
    return {"added": sorted(gb - ga), "removed": sorted(ga - gb), "limits_added": sorted(lb - la), "limits_removed": sorted(la - lb),
            "fields": {k: [a.get(k), b.get(k)] for k in ("name", "parent", "audience", "requires_mfa") if a.get(k) != b.get(k)}}


# --------------------------------------------------------------------------------------------------------------------
# Segregation of duties
# --------------------------------------------------------------------------------------------------------------------
def _match(codes, patterns) -> list[str]:
    return sorted({c for c in codes for p in patterns if fnmatch(c, p)})


def sod_conflicts(org, codes, user=None) -> list[dict]:
    codes = set(codes)
    out = []
    exceptions = {}
    if user is not None:
        for e in SoDException.objects.filter(user=user, organization=org, revoked_at__isnull=True):
            if e.is_live:
                exceptions[e.rule_id] = e
    for rule in SoDRule.objects.filter(organization=org, is_active=True):
        a, b = _match(codes, rule.first), _match(codes, rule.second)
        if a and b:
            exc = exceptions.get(rule.pk)
            out.append({"rule": rule.key, "rule_id": str(rule.pk), "name": rule.name, "severity": rule.severity, "first": a[:5], "second": b[:5],
                        "exception": {"reason": exc.reason, "valid_until": exc.valid_until} if exc else None})
    return out


def user_codes(user, org) -> set[str]:
    acct = OSAccount.objects.filter(user=user).first()
    if acct is None:
        return set()
    return set(AuthContext(user, acct).grants.keys())


def check_sod(org, user, adding: list[str], *, exception_reason: str = "", actor_ctx: AuthContext | None = None) -> list[dict]:
    """Raise if adding these codes creates a blocking conflict; return warnings otherwise. An `exception` rule may be
    overridden by someone holding access.sod.approve (not the person themselves), which records an SoD exception."""
    before = {c["rule"] for c in sod_conflicts(org, user_codes(user, org), user)}
    after = sod_conflicts(org, user_codes(user, org) | set(adding), user)
    new = [c for c in after if c["rule"] not in before and not c["exception"]]
    blocking = [c for c in new if c["severity"] == SoDRule.Severity.BLOCK]
    if blocking:
        raise DomainError(f"Segregation of duties: {blocking[0]['name']}. This combination isn’t allowed.", code="sod_blocked", status_code=409,
                          details={"conflicts": blocking})
    needs = [c for c in new if c["severity"] == SoDRule.Severity.EXCEPTION]
    if needs:
        if not exception_reason.strip():
            raise DomainError(f"Segregation of duties: {needs[0]['name']}. Give a reason to request an exception.", code="sod_exception_required",
                              status_code=409, details={"conflicts": needs})
        if actor_ctx is None or not actor_ctx.has("access.sod.approve") or actor_ctx.user.pk == user.pk:
            raise DomainError("An exception to segregation of duties needs someone with SoD exception authority (not the person themselves).",
                              code="sod_exception_required", status_code=403, details={"conflicts": needs})
        for c in needs:
            SoDException.objects.create(organization=org, rule_id=c["rule_id"], user=user, reason=exception_reason[:500], approved_by=actor_ctx.user,
                                        valid_until=timezone.now() + timedelta(days=365))
    return [c for c in new if c["severity"] == SoDRule.Severity.WARNING]


# --------------------------------------------------------------------------------------------------------------------
# Provisioning — the only way access is granted
# --------------------------------------------------------------------------------------------------------------------
def provision(request, *, org, user, role: Role, granted_by, org_unit=None, department=None, team=None, valid_until=None, note: str = "",
              actor_ctx: AuthContext | None = None, enforce_escalation: bool = True, sod_reason: str = "", source: str = "admin") -> tuple[RoleAssignment, list]:
    from .admin_views import assert_can_grant

    acct = OSAccount.objects.filter(user=user, organization=org).first()
    if acct is None:
        raise DomainError("This person has no Business OS account.", code="validation_error")
    if role.audience not in ("any", acct.kind):
        raise DomainError(f"“{role.name}” is for {role.get_audience_display().lower()}, not this account type.", code="validation_error",
                          details={"roleId": ["Wrong account type for this role."]})
    granter_ctx = actor_ctx or (load_context(granted_by) if granted_by else None)
    if enforce_escalation:
        if granter_ctx is None:
            raise DomainError("Nobody authorised this grant.", code="escalation_denied", status_code=403)
        assert_can_grant(granter_ctx, role_codes(role))
    warnings = check_sod(org, user, [c for c, _ in role_codes(role)], exception_reason=sod_reason, actor_ctx=granter_ctx)
    with transaction.atomic():
        a = RoleAssignment.objects.create(user=user, role=role, org_unit=org_unit, department=department, team=team, valid_until=valid_until,
                                          granted_by=granted_by, note=f"{source}: {note}"[:200])
        acct.bump_access()
    record(request, "access.role.assigned", category="access", module="access", resource=acct, resource_label=str(user), actor=granted_by,
           organization=org, new={"role": role.key, "source": source, "unit": getattr(org_unit, "code", None),
                                  "department": getattr(department, "code", None), "valid_until": valid_until, "sod_warnings": [w["rule"] for w in warnings]})
    notify(user, "security", f"You were given the {role.name} role" + (f" until {valid_until:%d %b %Y}" if valid_until else ""),
           body=f"Source: {source}", link="/access/me")
    return a, warnings


def revoke_assignment(request, a: RoleAssignment, *, actor=None, reason: str = "") -> None:
    if not a.is_active:
        return
    a.is_active = False
    a.save(update_fields=["is_active", "updated_at"])
    acct = OSAccount.objects.filter(user=a.user).first()
    if acct:
        acct.bump_access()
    record(request, "access.role.revoked", category="access", module="access", resource=acct, resource_label=str(a.user), actor=actor,
           organization=a.role.organization, old={"role": a.role.key}, new={"reason": reason})


# --------------------------------------------------------------------------------------------------------------------
# Access requests (approval engine policy "access.request")
# --------------------------------------------------------------------------------------------------------------------
def submit_access_request(request, ctx: AuthContext, *, role=None, package=None, reason: str, valid_until=None, org_unit=None, department=None):
    from apps.workflows import engine

    if not (role or package):
        raise DomainError("Choose a role or an access package.", code="validation_error")
    if len(reason.strip()) < 10:
        raise DomainError("Explain why you need this access (at least a sentence).", code="validation_error", details={"reason": ["Too short."]})
    if package is not None and not package.requestable:
        raise DomainError("This package can’t be requested.", code="validation_error")
    if role is not None and role.audience not in ("any", ctx.kind):
        raise DomainError("This role isn’t available for your account type.", code="validation_error")
    if role is not None and RoleAssignment.objects.live().filter(user=ctx.user, role=role).exists():
        raise DomainError("You already have this role.", code="validation_error")
    if AccessRequest.objects.filter(requester=ctx.user, status=AccessRequest.Status.PENDING, role=role, package=package).exists():
        raise DomainError("You already have a pending request for this.", code="duplicate_request", status_code=409)
    if package is not None and package.max_days:
        cap = timezone.now() + timedelta(days=package.max_days)
        valid_until = min(valid_until, cap) if valid_until else cap
    name = role.name if role else package.name
    roles = [role] if role else list(package.roles.filter(is_active=True))
    conflicts = sod_conflicts(ctx.organization, set(ctx.grants) | {c for r in roles for c, _ in role_codes(r)}, ctx.user)
    with transaction.atomic():
        ar = AccessRequest.objects.create(organization=ctx.organization, code=f"ACR-{secrets.token_hex(3).upper()}", requester=ctx.user, role=role,
                                          package=package, reason=reason.strip()[:4000], valid_until=valid_until, org_unit=org_unit, department=department)
        req = engine.submit(request, "access.request", title=f"Access: {name}", description=reason.strip()[:2000], resource_type="access.request",
                            resource_id=str(ar.pk), metadata={"role": getattr(role, "key", None), "package": getattr(package, "key", None),
                                                              "valid_until": valid_until.isoformat() if valid_until else None,
                                                              "sod_conflicts": [c["name"] for c in conflicts]})
        ar.approval = req
        ar.save(update_fields=["approval", "updated_at"])
    record(request, "access.request.submitted", category="access", module="access", resource=ar, new={"for": name, "reason": reason[:200]})
    return ar


def _on_access_request(req, outcome: str) -> None:
    ar = AccessRequest.objects.filter(pk=req.resource_id).select_related("role", "package", "requester", "organization").first()
    if ar is None or ar.status != AccessRequest.Status.PENDING:
        return
    if outcome in ("rejected", "cancelled"):
        ar.status = AccessRequest.Status.REJECTED if outcome == "rejected" else AccessRequest.Status.CANCELLED
        ar.decided_at = timezone.now()
        ar.save(update_fields=["status", "decided_at", "updated_at"])
        return
    if outcome != "approved":
        return
    from .admin_views import assert_can_grant

    steps = list(req.steps.filter(status="approved").select_related("decided_by").order_by("-sequence"))
    final = steps[0] if steps else None
    approver = final.decided_by if final else None
    roles = [ar.role] if ar.role_id else list(ar.package.roles.filter(is_active=True))
    ids, note = [], ""
    try:
        # Anti-escalation across the chain: someone who approved must hold what is granted (usually the business owner
        # at level 1); the access administrator at the last level records the grant.
        wanted = [c for r in roles for c in role_codes(r)]
        granter_ctx = None
        for st in steps:
            if st.decided_by_id is None:
                continue
            c = load_context(st.decided_by)
            try:
                assert_can_grant(c, wanted)
                granter_ctx = c
                break
            except DomainError:
                continue
        if granter_ctx is None:
            raise DomainError("None of the approvers holds the permissions in this role, so it can’t be granted from this request.",
                              code="escalation_denied", status_code=403)
        with transaction.atomic():
            for role in roles:
                a, _w = provision(None, org=ar.organization, user=ar.requester, role=role, granted_by=approver, org_unit=ar.org_unit,
                                  department=ar.department, valid_until=ar.valid_until, note=ar.code, source="access request",
                                  actor_ctx=granter_ctx)
                ids.append(str(a.pk))
        ar.status = AccessRequest.Status.PROVISIONED
    except DomainError as e:
        # The approval stands; the grant didn't happen (approver can't grant it, or SoD blocks it). Say so plainly.
        ar.status, note = AccessRequest.Status.BLOCKED, str(e.detail)[:300]
        notify(ar.requester, "approval_result", f"Approved but not granted: {ar.code}", body=note, link="/access/requests")
        if approver:
            notify(approver, "security", f"{ar.code} could not be provisioned", body=note, link="/access/requests")
    ar.assignment_ids, ar.outcome_note, ar.decided_at = ids, note, timezone.now()
    ar.save(update_fields=["status", "assignment_ids", "outcome_note", "decided_at", "updated_at"])


def _register_hooks():
    from apps.workflows.hooks import on_decision

    on_decision("access.request")(_on_access_request)


# --------------------------------------------------------------------------------------------------------------------
# Emergency (break-glass) access
# --------------------------------------------------------------------------------------------------------------------
def activate_emergency(request, ctx: AuthContext, *, role: Role, reason: str, hours: int) -> EmergencyAccess:
    ctx.require("access.emergency.create")
    if not role.emergency_eligible or role.organization_id != ctx.organization.pk:
        raise DomainError("This role isn’t available for emergency access.", code="validation_error")
    if len(reason.strip()) < 20:
        raise DomainError("Describe the emergency (at least 20 characters).", code="validation_error", details={"reason": ["Too short."]})
    if settings.CLICK_OS_SENSITIVE_REQUIRES_MFA and not (ctx.account and ctx.account.mfa_enabled):
        raise DomainError("Emergency access needs two-step verification.", code="mfa_required", status_code=403)
    if EmergencyAccess.objects.filter(user=ctx.user, status=EmergencyAccess.Status.ACTIVE).exists():
        raise DomainError("You already have emergency access active.", code="validation_error")
    hours = max(1, min(int(hours or 1), EMERGENCY_MAX_HOURS))
    ends = timezone.now() + timedelta(hours=hours)
    with transaction.atomic():
        a = RoleAssignment.objects.create(user=ctx.user, role=role, valid_until=ends, granted_by=ctx.user, note="emergency (break-glass)")
        ea = EmergencyAccess.objects.create(organization=ctx.organization, user=ctx.user, role=role, assignment=a, reason=reason.strip(), ends_at=ends)
        ctx.account.bump_access()
    record(request, "access.emergency.activated", category="security", module="access", resource=ea, sensitive=True,
           new={"role": role.key, "hours": hours, "reason": reason[:300]})
    watchers = [u for u in holders_of("access.emergency.manage", ctx.organization) if u.pk != ctx.user.pk]
    notify_many(watchers, "security", f"Emergency access activated by {ctx.user.full_name}",
                body=f"{role.name} for {hours}h · {reason[:150]}", link="/access/emergency", priority="critical")
    return ea


def end_emergency(request, ea: EmergencyAccess, *, actor=None, reason="ended") -> None:
    if ea.status != EmergencyAccess.Status.ACTIVE:
        return
    if ea.assignment_id:
        RoleAssignment.objects.filter(pk=ea.assignment_id).update(is_active=False)
    ea.status, ea.ended_at = EmergencyAccess.Status.ENDED, timezone.now()
    ea.save(update_fields=["status", "ended_at", "updated_at"])
    acct = OSAccount.objects.filter(user=ea.user).first()
    if acct:
        acct.bump_access()
    record(request, "access.emergency.ended", category="security", module="access", resource=ea, actor=actor, organization=ea.organization,
           sensitive=True, new={"reason": reason})


# --------------------------------------------------------------------------------------------------------------------
# Access reviews
# --------------------------------------------------------------------------------------------------------------------
def _reviewer_for(user, fallback):
    emp = getattr(user, "employee", None)
    mgr = getattr(emp, "manager", None) if emp else None
    if mgr is not None and mgr.user_id and mgr.user_id != user.pk:
        return mgr.user
    return fallback


def launch_review(request, ctx: AuthContext, *, name: str, kind: str, due_on=None, role_ids=None, privileged_only=False) -> AccessReview:
    qs = RoleAssignment.objects.live().filter(role__organization=ctx.organization).select_related("user__employee__manager__user", "role")
    if role_ids:
        qs = qs.filter(role_id__in=role_ids)
    sensitive_roles = set(RolePermission.objects.filter(permission__sensitive=True).values_list("role_id", flat=True))
    rows = []
    for a in qs:
        if privileged_only and a.role_id not in sensitive_roles and not a.role.requires_mfa:
            continue
        reviewer = _reviewer_for(a.user, ctx.user)
        if reviewer.pk == a.user_id:  # nobody certifies their own access
            reviewer = ctx.user if ctx.user.pk != a.user_id else None
        rows.append((a, reviewer, "Privileged role" if a.role_id in sensitive_roles else ""))
    if not rows:
        raise DomainError("No access matches this review.", code="validation_error")
    with transaction.atomic():
        rv = AccessReview.objects.create(organization=ctx.organization, name=name[:160], kind=kind if kind in AccessReview.Kind.values else "periodic",
                                         due_on=due_on, created_by=ctx.user)
        AccessReviewItem.objects.bulk_create([AccessReviewItem(review=rv, assignment=a, reviewer=r, reason=why) for a, r, why in rows])
    reviewers = {r.pk: r for _, r, _ in rows if r is not None}
    notify_many(list(reviewers.values()), "deadline", f"Access review: {rv.name}", body=f"Due {due_on:%d %b}" if due_on else "",
                link="/access/reviews", module="access")
    record(request, "access.review.launched", category="access", module="access", resource=rv, metadata={"items": len(rows)})
    return rv


def event_review(user, why: str) -> AccessReview | None:
    """Joiner/mover/leaver: put the person's current access in front of their manager (or access admins)."""
    acct = OSAccount.objects.filter(user=user).select_related("organization").first()
    if acct is None:
        return None
    assignments = list(RoleAssignment.objects.live().filter(user=user).select_related("role"))
    if not assignments:
        return None
    admins = holders_of("access.review.manage", acct.organization)
    fallback = next((u for u in admins if u.pk != user.pk), None)
    reviewer = _reviewer_for(user, fallback)
    if reviewer is None or reviewer.pk == user.pk:
        reviewer = fallback
    rv = AccessReview.objects.create(organization=acct.organization, name=f"{user.full_name}: {why}"[:160], kind="event",
                                     due_on=timezone.localdate() + timedelta(days=7))
    AccessReviewItem.objects.bulk_create([AccessReviewItem(review=rv, assignment=a, reviewer=reviewer, reason=why[:200]) for a in assignments])
    if reviewer:
        notify(reviewer, "deadline", f"Review {user.full_name}'s access", body=why, link="/access/reviews", module="access")
    return rv


def decide_review_item(request, ctx: AuthContext, item: AccessReviewItem, decision: str, comment: str = "") -> AccessReviewItem:
    if item.reviewer_id != ctx.user.pk and not ctx.has("access.review.manage"):
        raise DomainError("This item isn’t assigned to you.", code="permission_denied", status_code=403)
    if item.assignment.user_id == ctx.user.pk:
        raise DomainError("You can’t certify your own access.", code="self_change_denied", status_code=403)
    if decision not in AccessReviewItem.Decision.values or decision == "pending":
        raise DomainError("Choose keep, remove, suspend or escalate.", code="validation_error")
    if decision in ("remove", "suspend", "escalate") and not comment.strip():
        raise DomainError("Give a reason.", code="reason_required")
    if item.review.status != AccessReview.Status.OPEN:
        raise DomainError("This review is closed.", code="invalid_state", status_code=409)
    with transaction.atomic():
        item.decision, item.comment, item.decided_by, item.decided_at = decision, comment[:500], ctx.user, timezone.now()
        item.save()
        if decision == "remove":
            revoke_assignment(request, item.assignment, reason=f"Access review: {comment}")
        elif decision == "suspend":
            acct = OSAccount.objects.filter(user=item.assignment.user).first()
            if acct and acct.status == OSAccount.Status.ACTIVE:
                if not ctx.can("identity.user.manage"):
                    raise DomainError("Suspending an account needs user administration rights; choose escalate instead.", code="permission_denied",
                                      status_code=403)
                acct.status = OSAccount.Status.SUSPENDED
                acct.save(update_fields=["status", "updated_at"])
                revoke_all(acct.user, "access_review")
        elif decision == "escalate":
            notify_many(holders_of("access.review.manage", ctx.organization), "security", f"Access review escalated: {item.assignment.user.full_name}",
                        body=f"{item.assignment.role.name}: {comment}", link="/access/reviews", priority="important")
    record(request, f"access.review.{decision}", category="access", module="access", resource=item.review,
           resource_label=f"{item.assignment.user} · {item.assignment.role.key}", new={"comment": comment})
    if not item.review.items.filter(decision="pending").exists():
        item.review.status, item.review.closed_at = AccessReview.Status.CLOSED, timezone.now()
        item.review.save(update_fields=["status", "closed_at", "updated_at"])
    return item


# --------------------------------------------------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------------------------------------------------
def effective_access(user, org) -> dict:
    from apps.workflows.models import ApprovalDelegation

    acct = OSAccount.objects.filter(user=user, organization=org).first()
    if acct is None:
        raise DomainError("Not found.", code="not_found", status_code=404)
    ctx = AuthContext(user, acct)
    assignments = list(RoleAssignment.objects.filter(user=user, role__organization=org, is_active=True)
                       .select_related("role", "role__parent", "org_unit", "department", "team", "granted_by"))
    now = timezone.now()
    live_ids = {a.pk for a in RoleAssignment.objects.live().filter(user=user)}
    rows = []
    for a in assignments:
        rows.append({"id": str(a.pk), "role": {"id": str(a.role_id), "key": a.role.key, "name": a.role.name}, "live": a.pk in live_ids,
                     "inherits": [r.name for r in a.role.lineage()[1:]], "anchor": a.org_unit.name if a.org_unit_id else (a.department.name if a.department_id else "Own location"),
                     "valid_from": a.valid_from, "valid_until": a.valid_until, "temporary": bool(a.valid_until), "granted_by": getattr(a.granted_by, "full_name", None),
                     "note": a.note, "emergency": EmergencyAccess.objects.filter(assignment=a).exists()})
    implicit = [{"role": {"key": r.key, "name": r.name}, "why": "Has direct reports (from People & HR)"} for r in ctx.roles
                if r.pk not in {a.role_id for a in assignments}]
    perms = []
    for code in sorted(ctx.grants):
        s = ctx.scope(code)
        if s.is_empty:
            continue
        entry = registry.PERMISSIONS.get(code)
        perms.append({"code": code, "label": f"{entry[2].capitalize()} · {entry[1].label}" if entry else code, "module": code.split(".")[0],
                      "scope": s.level, "sensitive": registry.is_sensitive(code),
                      "sources": sorted({g.role_key for g in ctx.grants[code]})})
    delegations = [{"from": d.delegator.full_name, "policy": d.policy.name if d.policy_id else "All approvals", "until": d.ends_at}
                   for d in ApprovalDelegation.objects.filter(delegate=user, revoked_at__isnull=True, starts_at__lte=now, ends_at__gt=now)
                   .select_related("delegator", "policy")]
    return {
        "account": {"id": str(acct.pk), "name": user.full_name, "email": user.email, "status": acct.status, "kind": acct.kind,
                    "identity_type": acct.identity_type, "mfa": acct.mfa_enabled, "last_login_at": acct.last_login_at, "expires_at": acct.expires_at},
        "assignments": rows, "implicit_roles": implicit, "permissions": perms,
        "mfa_blocked": sorted(ctx.mfa_blocked),
        "approval_authority": [{"type": t, "label": registry.APPROVAL_TYPES.get(t, t), "limit": str(v) if v is not None else None}
                               for t, v in sorted(ctx.limits.items())],
        "delegations": delegations,
        "conflicts": sod_conflicts(org, {p["code"] for p in perms}, user),
        "risk": risk(acct, ctx),
    }


def who_has(org, code: str, target: dict | None = None) -> list[dict]:
    if not registry.is_known(code):
        raise DomainError("Unknown permission.", code="validation_error")
    roles = {r.pk: r for r in Role.objects.filter(organization=org, is_active=True).select_related("parent")}
    grant_roles = {}
    for rp in RolePermission.objects.filter(permission__code=code, role__organization=org):
        grant_roles[rp.role_id] = rp.scope
    via = {}
    for r in roles.values():
        for anc in r.lineage():
            if anc.pk in grant_roles:
                via[r.pk] = (anc, grant_roles[anc.pk])
                break
    out = []
    for a in RoleAssignment.objects.live().filter(role_id__in=via.keys()).select_related("user", "role", "org_unit", "department"):
        acct = OSAccount.objects.filter(user=a.user).first()
        if acct is None or acct.status != OSAccount.Status.ACTIVE:
            continue
        ctx = AuthContext(a.user, acct)
        if target and not ctx.can(code, **target):
            continue
        src_role, scope = via[a.role_id]
        out.append({"user_id": str(a.user_id), "account_id": str(acct.pk), "name": a.user.full_name, "role": a.role.name,
                    "via": src_role.name if src_role.pk != a.role_id else None, "scope": scope, "effective_scope": ctx.scope(code).level,
                    "anchor": a.org_unit.name if a.org_unit_id else (a.department.name if a.department_id else "Own location"),
                    "valid_until": a.valid_until, "granted_by": a.granted_by.full_name if a.granted_by_id else None,
                    "mfa_blocked": code in ctx.mfa_blocked})
    return sorted(out, key=lambda r: r["name"] or "")


def simulate(org, user, code: str, *, unit=None, department=None, owner=None, approval_type: str = "", amount=None) -> dict:
    acct = OSAccount.objects.filter(user=user, organization=org).first()
    if acct is None:
        return {"allowed": False, "reasons": ["The person has no Business OS account."]}
    if not registry.is_known(code):
        return {"allowed": False, "reasons": [f"{code} is not a permission in the catalogue."]}
    ctx = AuthContext(user, acct)
    reasons = []
    if acct.status != OSAccount.Status.ACTIVE:
        return {"allowed": False, "reasons": [f"Account is {acct.get_status_display().lower()}."]}
    if code in ctx.mfa_blocked and not ctx.has(code):
        return {"allowed": False, "reasons": ["Granted, but blocked until the person turns on two-step verification."]}
    s = ctx.scope(code)
    if s.is_empty:
        return {"allowed": False, "reasons": ["No role grants this permission."]}
    reasons.append(f"Granted by {', '.join(sorted({g.role_key for g in ctx.grants[code]}))} at {s.level} scope.")
    target = {k: v for k, v in {"unit": unit, "department": department, "owner": owner}.items() if v}
    if target:
        if not s.covers(**target):
            return {"allowed": False, "reasons": reasons + ["The record is outside the person’s scope."]}
        reasons.append("The record is inside the person’s scope.")
    if approval_type:
        try:
            amt = Decimal(str(amount)) if amount not in (None, "") else None
        except InvalidOperation:
            amt = None
        has, cap = ctx.approval_authority(approval_type)
        if amt is not None:
            if not ctx.within_limit(approval_type, amt):
                return {"allowed": False, "reasons": reasons + [f"Approval limit exceeded ({'none' if not has else cap})."]}
            reasons.append(f"Within approval limit ({'no upper limit' if cap is None else cap}).")
    return {"allowed": True, "reasons": reasons}


def compare_roles(org, role_ids) -> dict:
    order = {str(x): i for i, x in enumerate(role_ids)}
    roles = sorted(Role.objects.filter(organization=org, pk__in=role_ids).select_related("parent"), key=lambda r: order.get(str(r.pk), 99))
    if len(roles) < 2:
        raise DomainError("Choose at least two roles.", code="validation_error")
    per = {r.pk: dict(role_codes(r)) for r in roles}
    codes = sorted(set().union(*[set(v) for v in per.values()]))
    lims = {r.pk: {lim.approval_type: (str(lim.max_amount) if lim.max_amount is not None else "No limit")
                   for anc in r.lineage() for lim in anc.approval_limits.all()} for r in roles}
    return {"roles": [{"id": str(r.pk), "name": r.name, "version": r.version} for r in roles],
            "rows": [{"code": c, "module": c.split(".")[0], "values": [per[r.pk].get(c) for r in roles],
                      "differs": len({per[r.pk].get(c) for r in roles}) > 1} for c in codes],
            "limits": [{"type": t, "values": [lims[r.pk].get(t) for r in roles]} for t in sorted(set().union(*[set(v) for v in lims.values()]))]}


def risk(acct: OSAccount, ctx: AuthContext | None = None) -> dict:
    """Internal review indicator (0–100). Not a recognised security score."""
    ctx = ctx or AuthContext(acct.user, acct)
    factors = []
    codes = [c for c in ctx.grants if ctx.has(c)]
    admin = [c for c in codes if registry.is_admin_code(c)]
    sens = [c for c in codes if registry.is_sensitive(c)]
    if admin:
        factors.append(("Administrative permissions", 25))
    if sens:
        factors.append((f"{len(sens)} sensitive permissions", min(20, 5 + len(sens))))
    if len(ctx.roles) >= 4:
        factors.append((f"{len(ctx.roles)} roles", 10))
    if not acct.mfa_enabled and (admin or sens):
        factors.append(("Privileged without two-step verification", 25))
    if RoleAssignment.objects.live().filter(user=acct.user, valid_until__isnull=False).exists():
        factors.append(("Temporary access", 5))
    if acct.last_login_at and acct.last_login_at < timezone.now() - timedelta(days=DORMANT_DAYS):
        factors.append((f"No sign-in for {DORMANT_DAYS}+ days", 15))
    conf = sod_conflicts(acct.organization, codes, acct.user)
    if conf:
        factors.append((f"{len(conf)} segregation-of-duties conflicts", 15))
    score = min(100, sum(w for _, w in factors))
    return {"score": score, "level": "high" if score >= 60 else "medium" if score >= 30 else "low",
            "factors": [f for f, _ in factors], "note": "Internal indicator for access reviews, not a security certification."}


def orphaned(org) -> list[dict]:
    from apps.people.models import Employee

    out = []
    exited = set(Employee.EXITED) if hasattr(Employee, "EXITED") else {"resigned", "terminated", "retired"}
    for acct in OSAccount.objects.filter(organization=org).exclude(status__in=["deactivated", "archived", "expired"]).select_related("user"):
        emp = getattr(acct.user, "employee", None)
        issues = []
        if acct.kind == "employee" and emp is None:
            issues.append("Employee account without an HR record")
        if emp is not None and emp.status in exited:
            issues.append(f"Employee has left ({emp.status})")
        if emp is not None and emp.status not in exited and not emp.manager_id and acct.kind == "employee":
            issues.append("No manager")
        if emp is not None and not emp.department_id:
            issues.append("No department")
        live = RoleAssignment.objects.live().filter(user=acct.user).exists()
        if acct.status == "active" and not live:
            issues.append("Active account with no roles")
        if acct.expires_at and acct.expires_at < timezone.now():
            issues.append("Contract / access end date passed")
        if acct.status == "active" and (acct.last_login_at is None or acct.last_login_at < timezone.now() - timedelta(days=DORMANT_DAYS)) \
                and acct.created_at < timezone.now() - timedelta(days=DORMANT_DAYS):
            issues.append(f"No sign-in for {DORMANT_DAYS}+ days")
        if issues:
            out.append({"account_id": str(acct.pk), "name": acct.user.full_name, "email": acct.user.email, "status": acct.status, "issues": issues})
    return out


def unused_roles(org) -> list[dict]:
    rows = []
    for r in Role.objects.filter(organization=org, is_active=True):
        if r.key == "people-manager":
            continue
        if not RoleAssignment.objects.filter(role=r, is_active=True).exists() and not r.children.exists():
            rows.append({"id": str(r.pk), "name": r.name, "key": r.key, "system": r.is_system})
    return rows


def privileged(org) -> list[dict]:
    out = []
    for acct in OSAccount.objects.filter(organization=org, status=OSAccount.Status.ACTIVE).select_related("user"):
        ctx = AuthContext(acct.user, acct)
        codes = [c for c in ctx.grants if ctx.has(c) or c in ctx.mfa_blocked]
        admin = sorted({c.split(".")[0] for c in codes if registry.is_admin_code(c)})
        sens = [c for c in codes if registry.is_sensitive(c)]
        if not (admin or sens):
            continue
        last_review = AccessReviewItem.objects.filter(assignment__user=acct.user).exclude(decision="pending").order_by("-decided_at").first()
        out.append({"account_id": str(acct.pk), "name": acct.user.full_name, "roles": [r.name for r in ctx.roles], "admin_areas": admin,
                    "sensitive": len(sens), "mfa": acct.mfa_enabled, "last_login_at": acct.last_login_at,
                    "last_reviewed": last_review.decided_at if last_review else None})
    return sorted(out, key=lambda r: (-len(r["admin_areas"]), r["name"] or ""))


# --------------------------------------------------------------------------------------------------------------------
# Scheduled jobs (python manage.py os_access_jobs)
# --------------------------------------------------------------------------------------------------------------------
def run_jobs(now=None) -> dict:
    now = now or timezone.now()
    out = {"temporary_expired": 0, "expiring_notified": 0, "emergency_ended": 0, "accounts_expired": 0, "sod_exceptions_lapsed": 0}
    for a in RoleAssignment.objects.filter(is_active=True, valid_until__lte=now).select_related("user", "role", "role__organization"):
        ea = EmergencyAccess.objects.filter(assignment=a, status="active").first()
        if ea:
            end_emergency(None, ea, reason="time limit reached")
            out["emergency_ended"] += 1
            continue
        revoke_assignment(None, a, reason="Temporary access ended")
        notify(a.user, "security", f"Your temporary {a.role.name} access ended", link="/access/me")
        out["temporary_expired"] += 1
    soon = now + timedelta(days=3)
    for a in RoleAssignment.objects.filter(is_active=True, valid_until__gt=now, valid_until__lte=soon).select_related("user", "role"):
        if notify(a.user, "deadline", f"Your {a.role.name} access ends {a.valid_until:%d %b}", link="/access/me",
                  dedupe_key=f"temp-expiring:{a.pk}"):
            out["expiring_notified"] += 1
    for acct in OSAccount.objects.filter(expires_at__lte=now, status__in=["active", "invited", "suspended"]).select_related("user"):
        acct.status = OSAccount.Status.EXPIRED
        acct.save(update_fields=["status", "updated_at"])
        revoke_all(acct.user, "expired")
        acct.bump_access()
        record(None, "identity.user.expired", category="security", module="identity", resource=acct, organization=acct.organization)
        out["accounts_expired"] += 1
    out["sod_exceptions_lapsed"] = SoDException.objects.filter(revoked_at__isnull=True, valid_until__lte=now).update(revoked_at=now)
    for ea in EmergencyAccess.objects.filter(status="active", ends_at__lte=now):
        end_emergency(None, ea, reason="time limit reached")
        out["emergency_ended"] += 1
    return out


def home(ctx: AuthContext) -> dict:
    org = ctx.organization
    accts = OSAccount.objects.filter(organization=org)
    active = accts.filter(status="active")
    now = timezone.now()
    from apps.audit.models import AuditEvent

    day = now - timedelta(days=1)
    failed = AuditEvent.objects.filter(organization=org, category="auth", outcome="failure", created_at__gte=day).count() \
        if ctx.has("identity.security.view") else None
    priv = privileged(org) if ctx.has("access.analysis.view") else []
    mfa_cov = round(active.exclude(mfa_enabled_at__isnull=True).count() / max(1, active.count()) * 100)
    sod_violations = 0
    if ctx.has("access.sod.view"):
        for acct in active.select_related("user"):
            c = AuthContext(acct.user, acct)
            sod_violations += sum(1 for x in sod_conflicts(org, [k for k in c.grants if c.has(k)], acct.user) if not x["exception"])
    return {
        "identity": {"total": accts.count(), "active": active.count(), "invited": accts.filter(status="invited").count(),
                     "suspended": accts.filter(status="suspended").count(), "expired": accts.filter(status__in=["expired", "deactivated"]).count(),
                     "external": accts.exclude(kind="employee").count(),
                     "service_accounts": ServiceAccount.objects.filter(organization=org, revoked_at__isnull=True).count(),
                     "by_type": {t: accts.filter(identity_type=t).count() for t, _ in OSAccount._meta.get_field("identity_type").choices}},
        "access": {"roles": Role.objects.filter(organization=org, is_active=True).count(),
                   "custom_roles": Role.objects.filter(organization=org, is_active=True, is_system=False).count(),
                   "privileged_users": len(priv), "temporary": RoleAssignment.objects.live().filter(role__organization=org, valid_until__isnull=False).count(),
                   "expiring_7d": RoleAssignment.objects.live().filter(role__organization=org, valid_until__lte=now + timedelta(days=7)).count(),
                   "pending_requests": AccessRequest.objects.filter(organization=org, status="pending").count(),
                   "packages": AccessPackage.objects.filter(organization=org, is_active=True).count()},
        "security": {"failed_logins_24h": failed, "locked": accts.filter(locked_until__gt=now).count(), "mfa_coverage_pct": mfa_cov,
                     "admins": sum(1 for p in priv if p["admin_areas"]), "privileged_without_mfa": sum(1 for p in priv if not p["mfa"]),
                     "emergency_active": EmergencyAccess.objects.filter(organization=org, status="active").count(),
                     "emergency_unreviewed": EmergencyAccess.objects.filter(organization=org, status="ended").count()},
        "governance": {"reviews_open": AccessReview.objects.filter(organization=org, status="open").count(),
                       "review_items_mine": AccessReviewItem.objects.filter(reviewer=ctx.user, decision="pending").count(),
                       "sod_violations": sod_violations if ctx.has("access.sod.view") else None,
                       "orphaned": len(orphaned(org)) if ctx.has("access.analysis.view") else None,
                       "unused_roles": len(unused_roles(org)) if ctx.has("access.analysis.view") else None},
        "my_requests": AccessRequest.objects.filter(requester=ctx.user, status="pending").count(),
    }
