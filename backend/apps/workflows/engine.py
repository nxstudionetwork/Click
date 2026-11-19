"""
Approval engine. Modules call submit(); people call decide(); a scheduled job calls escalate_overdue().

    req = engine.submit(request, "finance.expense", title="Team offsite travel", amount=Decimal("42000"))
    engine.decide(request, req, "approve", comment="OK within budget")
"""

import secrets
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.access.authz import AuthContext, context_for, holders_of, load_context
from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.workspace.notify import notify, notify_many

from .hooks import fire
from .models import ApprovalComment, ApprovalDelegation, ApprovalPolicy, ApprovalRequest, ApprovalStep


def _money(req: ApprovalRequest) -> str:
    if req.amount is None:
        return ""
    unit = req.policy.amount_unit
    if unit == "days":
        return f" · {req.amount.normalize():f} day{'s' if req.amount != 1 else ''}"
    if unit == "count":
        return f" · {req.amount.normalize():f}"
    return f" · {req.currency} {req.amount:,.2f}"


def _limit_applies(req: ApprovalRequest) -> bool:
    return req.policy.amount_unit == "currency"


def _target(req: ApprovalRequest) -> dict:
    t = {"organization": req.organization_id, "owner": req.requested_by_id}
    if req.org_unit_id:
        t["unit"] = req.org_unit_id
    if req.department_id:
        t["department"] = req.department_id
    return t


def _qualifies(ctx: AuthContext, req: ApprovalRequest, step: ApprovalStep) -> bool:
    if ctx.user.pk == req.requested_by_id:  # segregation of duties: nobody approves their own request
        return False
    # The requester stays in the target so reporting-line scopes ("my reports") match; nobody approves their own
    # request because of the segregation-of-duties check above.
    target = _target(req)
    if not ctx.can(step.approver_permission, **target):
        return False
    return not step.enforce_limit or not _limit_applies(req) or ctx.within_limit(req.policy.approval_type, req.amount)


def active_delegations_to(user, policy=None):
    now = timezone.now()
    qs = ApprovalDelegation.objects.filter(delegate=user, revoked_at__isnull=True, starts_at__lte=now, ends_at__gt=now)
    if policy is not None:
        qs = qs.filter(models_policy_q(policy))
    return qs.select_related("delegator")


def models_policy_q(policy):
    from django.db.models import Q

    return Q(policy__isnull=True) | Q(policy=policy)


def can_act(ctx: AuthContext, req: ApprovalRequest) -> tuple[bool, object | None]:
    """(may decide the current step, the delegator acted for — or None when acting in one's own right)."""
    if req.status != ApprovalRequest.Status.PENDING:
        return False, None
    step = req.steps.filter(sequence=req.current_sequence).first()
    if step is None:
        return False, None
    if _qualifies(ctx, req, step):
        return True, None
    if ctx.user.pk == req.requested_by_id:
        return False, None
    for d in active_delegations_to(ctx.user, req.policy):
        if d.delegator_id != req.requested_by_id and _qualifies(load_context(d.delegator), req, step):
            return True, d.delegator
    return False, None


def eligible_approvers(req: ApprovalRequest, step: ApprovalStep) -> list:
    target = _target(req)
    users = [u for u in holders_of(step.approver_permission, req.organization, **target) if u.pk != req.requested_by_id]
    return [u for u in users if not step.enforce_limit or not _limit_applies(req)
            or load_context(u).within_limit(req.policy.approval_type, req.amount)]


def _activate(req: ApprovalRequest, step: ApprovalStep, request=None) -> None:
    now = timezone.now()
    level = req.policy.levels.filter(sequence=step.sequence).first()
    step.status = ApprovalStep.Status.PENDING
    step.activated_at = now
    step.due_at = now + timedelta(hours=level.escalate_after_hours) if level and level.escalate_after_hours else None
    step.save(update_fields=["status", "activated_at", "due_at", "updated_at"])
    req.current_sequence = step.sequence
    req.due_at = step.due_at
    req.save(update_fields=["current_sequence", "due_at", "updated_at"])
    approvers = eligible_approvers(req, step)
    notify_many(approvers, "approval_request", f"Approval needed: {req.title}{_money(req)}",
                body=f"{req.reference} · {step.name} · from {req.requested_by.full_name or req.requested_by.email}",
                link=f"/approvals/{req.pk}", module=req.policy.module, priority="important")


def submit(request, policy_key: str, *, title: str, amount=None, currency=None, description: str = "", org_unit=None,
           department=None, resource_type: str = "", resource_id: str = "", metadata: dict | None = None,
           priority: str = "normal", blocking: bool = False, due_at=None, skip_permission: bool = False) -> ApprovalRequest:
    """`skip_permission` is for modules that already authorized the action (e.g. a leave request checked against
    people.leave.create for that employee); the requester is still recorded and segregation of duties still applies."""
    ctx = context_for(request)
    policy = ApprovalPolicy.objects.filter(organization=ctx.organization, key=policy_key, is_active=True).prefetch_related("levels").first()
    if policy is None:
        raise DomainError("This approval type isn’t available.", code="policy_not_found", status_code=404)
    emp = ctx.employee
    org_unit = org_unit or (emp.org_unit if emp else None)
    department = department or (emp.department if emp else None)
    target = {"organization": ctx.organization.pk, "owner": ctx.user.pk}
    if org_unit:
        target["unit"] = org_unit
    if department:
        target["department"] = department
    if not skip_permission:
        ctx.require(policy.submit_permission, **target)
    if priority not in ApprovalRequest.Priority.values:
        priority = "normal"
    if policy.requires_amount and amount is None:
        raise DomainError("Enter the amount.", code="amount_required")
    if amount is not None and Decimal(amount) <= 0:
        raise DomainError("The amount must be more than zero.", code="amount_invalid")
    amt = Decimal(amount) if amount is not None else None
    levels = [lv for lv in policy.levels.all() if amt is None or amt >= lv.min_amount]
    if not levels:
        raise DomainError("This approval type has no approval levels configured.", code="policy_incomplete", status_code=409)
    with transaction.atomic():
        req = ApprovalRequest.objects.create(
            organization=ctx.organization, policy=policy, reference=f"APR-{secrets.token_hex(4).upper()}", title=title.strip()[:160],
            description=description, amount=amt, currency=currency or policy.currency, org_unit=org_unit, department=department,
            requested_by=ctx.user, resource_type=resource_type, resource_id=str(resource_id), metadata=metadata or {},
            priority=priority, blocking=blocking,
        )
        steps = [ApprovalStep.objects.create(request=req, sequence=lv.sequence, name=lv.name, approver_permission=lv.approver_permission,
                                             enforce_limit=lv.enforce_limit) for lv in levels]
        ApprovalComment.objects.create(request=req, author=ctx.user, kind="submitted", body=description[:2000])
        _activate(req, steps[0], request)
        if due_at and (req.due_at is None or due_at < req.due_at):
            req.due_at = due_at
            req.save(update_fields=["due_at", "updated_at"])
    record(request, "approval.submitted", category="approval", module=policy.module, resource=req, org_unit=org_unit,
           new={"title": req.title, "amount": req.amount, "policy": policy.key})
    return req


def decide(request, req: ApprovalRequest, decision: str, *, comment: str = "") -> ApprovalRequest:
    ctx = context_for(request)
    if decision not in {"approve", "reject", "request_changes"}:
        raise DomainError("Unknown decision.", code="decision_invalid")
    comment = (comment or "").strip()
    if decision in ("reject", "request_changes") and not comment:
        raise DomainError("Give a reason for rejecting." if decision == "reject" else "Say what needs to change.", code="reason_required")
    if decision == "request_changes":
        return _request_changes(request, ctx, req, comment)
    with transaction.atomic():
        req = ApprovalRequest.objects.select_for_update().select_related("policy", "requested_by", "organization").get(pk=req.pk)
        allowed, on_behalf = can_act(ctx, req)
        if not allowed:
            if req.status != ApprovalRequest.Status.PENDING:
                raise DomainError("This request has already been decided.", code="already_decided", status_code=409)
            raise DomainError("You can’t decide this request (permission, scope or approval limit).", code="permission_denied", status_code=403)
        step = req.steps.get(sequence=req.current_sequence)
        now = timezone.now()
        step.status = ApprovalStep.Status.APPROVED if decision == "approve" else ApprovalStep.Status.REJECTED
        step.decided_by, step.on_behalf_of, step.decided_at, step.comment = ctx.user, on_behalf, now, comment
        step.save()
        kind = "approved" if decision == "approve" else "rejected"
        who = f" on behalf of {on_behalf.full_name}" if on_behalf else ""
        ApprovalComment.objects.create(request=req, author=ctx.user, kind=kind, body=(f"{step.name}{who}. {comment}").strip())
        nxt = req.steps.filter(sequence__gt=step.sequence, status=ApprovalStep.Status.WAITING).order_by("sequence").first()
        if decision == "reject" or nxt is None:
            req.status = ApprovalRequest.Status.APPROVED if decision == "approve" else ApprovalRequest.Status.REJECTED
            req.decided_at, req.current_sequence, req.due_at = now, None, None
            req.save(update_fields=["status", "decided_at", "current_sequence", "due_at", "updated_at"])
            req.steps.filter(status=ApprovalStep.Status.WAITING).update(status=ApprovalStep.Status.SKIPPED)
            fire(req, req.status)
            notify(req.requested_by, "approval_result", f"{req.title} was {req.status}",
                   body=f"{req.reference}{_money(req)}" + (f" · Reason: {comment}" if decision == "reject" else ""),
                   link=f"/approvals/{req.pk}", module=req.policy.module, priority="important")
        else:
            _activate(req, nxt, request)
    record(request, f"approval.{kind}", category="approval", module=req.policy.module, resource=req, org_unit=req.org_unit,
           old={"status": "pending", "level": step.name}, new={"status": req.status, "decision": decision, "comment": comment},
           metadata={"on_behalf_of": str(on_behalf.pk) if on_behalf else None})
    return req


def _request_changes(request, ctx, req: ApprovalRequest, comment: str) -> ApprovalRequest:
    with transaction.atomic():
        req = ApprovalRequest.objects.select_for_update().select_related("policy", "requested_by", "organization").get(pk=req.pk)
        if not req.policy.allow_request_changes:
            raise DomainError("This approval type can only be approved or rejected.", code="decision_invalid")
        allowed, on_behalf = can_act(ctx, req)
        if not allowed:
            raise DomainError("You can’t decide this request.", code="permission_denied", status_code=403)
        req.status = ApprovalRequest.Status.CHANGES_REQUESTED
        req.save(update_fields=["status", "updated_at"])
        who = f" on behalf of {on_behalf.full_name}" if on_behalf else ""
        ApprovalComment.objects.create(request=req, author=ctx.user, kind="changes_requested", body=f"Changes requested{who}: {comment}")
        fire(req, "changes_requested")
    notify(req.requested_by, "approval_result", f"Changes requested: {req.title}", body=comment, link=f"/approvals/{req.pk}",
           module=req.policy.module, priority="important")
    record(request, "approval.changes_requested", category="approval", module=req.policy.module, resource=req, new={"comment": comment})
    return req


def resubmit(request, req: ApprovalRequest, *, title: str | None = None, description: str | None = None, amount=None,
             comment: str = "") -> ApprovalRequest:
    """The requester updates a request that came back with changes requested; it returns to the same level."""
    ctx = context_for(request)
    if req.requested_by_id != ctx.user.pk:
        raise DomainError("Only the person who raised this request can resubmit it.", code="permission_denied", status_code=403)
    if req.status != ApprovalRequest.Status.CHANGES_REQUESTED:
        raise DomainError("Only requests sent back for changes can be resubmitted.", code="invalid_state", status_code=409)
    before = {"title": req.title, "amount": req.amount, "description": req.description}
    with transaction.atomic():
        if title:
            req.title = title.strip()[:160]
        if description is not None:
            req.description = description[:4000]
        if amount not in (None, ""):
            amount = Decimal(str(amount))
            if amount <= 0:
                raise DomainError("The amount must be more than zero.", code="amount_invalid")
            req.amount = amount
        req.status = ApprovalRequest.Status.PENDING
        req.save()
        ApprovalComment.objects.create(request=req, author=ctx.user, kind="resubmitted", body=comment[:2000])
        step = req.steps.filter(sequence=req.current_sequence).first()
        if step:
            _activate(req, step, request)
        fire(req, "resubmitted")
    record(request, "approval.resubmitted", category="approval", module=req.policy.module, resource=req, old=before,
           new={"title": req.title, "amount": req.amount, "description": req.description})
    return req


def cancel(request, req: ApprovalRequest, *, reason: str = "") -> ApprovalRequest:
    ctx = context_for(request)
    if req.requested_by_id != ctx.user.pk:
        raise DomainError("Only the person who raised this request can withdraw it.", code="permission_denied", status_code=403)
    if req.status not in (ApprovalRequest.Status.PENDING, ApprovalRequest.Status.CHANGES_REQUESTED):
        raise DomainError("This request has already been decided.", code="already_decided", status_code=409)
    req.status, req.decided_at, req.current_sequence = ApprovalRequest.Status.CANCELLED, timezone.now(), None
    req.save(update_fields=["status", "decided_at", "current_sequence", "updated_at"])
    req.steps.filter(status__in=[ApprovalStep.Status.WAITING, ApprovalStep.Status.PENDING]).update(status=ApprovalStep.Status.SKIPPED)
    ApprovalComment.objects.create(request=req, author=ctx.user, kind="cancelled", body=reason[:2000])
    fire(req, "cancelled")
    record(request, "approval.cancelled", category="approval", module=req.policy.module, resource=req, new={"reason": reason})
    return req


def escalate_overdue(now=None) -> int:
    """Notify the eligible approvers again (critical) for every step past its due time. Run from a scheduler."""
    now = now or timezone.now()
    n = 0
    for step in ApprovalStep.objects.filter(status=ApprovalStep.Status.PENDING, due_at__lt=now, escalated_at__isnull=True) \
            .select_related("request", "request__policy", "request__organization", "request__requested_by"):
        req = step.request
        notify_many(eligible_approvers(req, step), "deadline", f"Overdue approval: {req.title}",
                    body=f"{req.reference} · {step.name} has been waiting since {step.activated_at:%d %b %H:%M}.",
                    link=f"/approvals/{req.pk}", module=req.policy.module, priority="critical")
        ApprovalComment.objects.create(request=req, kind="escalated", body=f"{step.name} passed its deadline; approvers reminded.")
        step.escalated_at = now
        step.save(update_fields=["escalated_at", "updated_at"])
        record(None, "approval.escalated", category="approval", organization=req.organization, module=req.policy.module, resource=req)
        n += 1
    return n


def urgency(req: ApprovalRequest, now=None) -> list[str]:
    """Flags shown on approval cards: overdue, due_soon, high_value, blocking, waiting_long."""
    from datetime import timedelta as _td
    from django.conf import settings as _s

    now = now or timezone.now()
    flags = []
    if req.due_at and req.due_at < now:
        flags.append("overdue")
    elif req.due_at and req.due_at < now + _td(hours=24):
        flags.append("due_soon")
    threshold = req.policy.high_value_amount
    if threshold is None and req.policy.amount_unit == "currency":
        threshold = Decimal(str(getattr(_s, "CLICK_OS_HIGH_VALUE_AMOUNT", "100000")))
    if req.amount is not None and threshold is not None and req.amount >= threshold:
        flags.append("high_value")
    if req.blocking:
        flags.append("blocking")
    if req.created_at < now - _td(days=3):
        flags.append("waiting_long")
    return flags
