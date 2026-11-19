"""Approvals, delegations, policies and tasks API (os/approvals/*, os/tasks/*, os/admin/workflows/*)."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.response import Response

from apps.access import registry
from apps.access.api import OSView
from apps.audit.services import record
from apps.core.api.exceptions import DomainError
from apps.organization.models import OrgUnit
from apps.users.models import User
from apps.workspace.notify import notify

from . import engine
from .models import ApprovalComment, ApprovalDelegation, ApprovalLevel, ApprovalPolicy, ApprovalRequest, Task
from .selectors import inbox_for, visible_requests


def _person(u):
    return {"id": str(u.pk), "full_name": u.full_name or u.email} if u else None


def request_brief(r: ApprovalRequest) -> dict:
    return {"id": str(r.pk), "reference": r.reference, "title": r.title, "status": r.status, "amount": str(r.amount) if r.amount is not None else None,
            "currency": r.currency, "policy": {"key": r.policy.key, "name": r.policy.name, "module": r.policy.module},
            "requested_by": _person(r.requested_by), "org_unit": r.org_unit.name if r.org_unit_id else None,
            "current_sequence": r.current_sequence, "due_at": r.due_at, "created_at": r.created_at, "decided_at": r.decided_at,
            "priority": r.priority, "flags": engine.urgency(r), "amount_unit": r.policy.amount_unit}


class ApprovalsView(OSView):
    def get(self, request):
        ctx = self.authz
        box = request.query_params.get("box", "inbox")
        if box == "inbox":
            items = inbox_for(ctx)
        elif box == "mine":
            items = ApprovalRequest.objects.filter(requested_by=ctx.user).select_related("policy", "requested_by", "org_unit")[:200]
        elif box == "decided":
            items = ApprovalRequest.objects.filter(steps__decided_by=ctx.user).distinct().select_related("policy", "requested_by", "org_unit")[:200]
        elif box == "all":
            ctx.require("workflows.request.view")
            items = visible_requests(ctx).select_related("policy", "requested_by", "org_unit")[:200]
        else:
            raise DomainError("Unknown list.", code="validation_error")
        if s := request.query_params.get("status"):
            items = [r for r in items if r.status == s]
        return Response({"results": [request_brief(r) for r in items], "box": box,
                         "counts": {"inbox": len(inbox_for(ctx)) if box != "inbox" else len(items),
                                    "mine_pending": ApprovalRequest.objects.filter(requested_by=ctx.user, status="pending").count()}})

    def post(self, request):
        d = request.data
        amount = d.get("amount")
        if amount not in (None, ""):
            try:
                amount = Decimal(str(amount))
            except InvalidOperation:
                raise DomainError("Enter a valid amount.", code="validation_error", details={"amount": ["Enter a valid amount."]})
        else:
            amount = None
        title = str(d.get("title", "")).strip()
        if len(title) < 3:
            raise DomainError("Give the request a title.", code="validation_error", details={"title": ["Give the request a title."]})
        unit = None
        if d.get("org_unit_id"):
            unit = OrgUnit.objects.filter(pk=d["org_unit_id"], organization=self.authz.organization).first()
            if unit is None:
                raise DomainError("Unknown location.", code="validation_error", details={"orgUnitId": ["Unknown location."]})
        req = engine.submit(request, str(d.get("policy_key", "")), title=title, amount=amount, description=str(d.get("description", ""))[:4000],
                            org_unit=unit)
        return Response(request_brief(req), status=status.HTTP_201_CREATED)


def load_visible(ctx, pk):
    """A request the caller may see (or decide). Anything else is a plain 404, never a 403 that confirms it exists."""
    req = (ApprovalRequest.objects.select_related("policy", "requested_by", "org_unit", "department")
           .filter(pk=pk, organization=ctx.organization).first())
    if req is None:
        raise DomainError("Not found.", code="not_found", status_code=404)
    allowed, on_behalf = engine.can_act(ctx, req)
    if not (allowed or visible_requests(ctx).filter(pk=req.pk).exists()):
        raise DomainError("Not found.", code="not_found", status_code=404)
    return req, allowed, on_behalf


def detail_payload(request, ctx, pk) -> dict:
    req, allowed, on_behalf = load_visible(ctx, pk)
    data = request_brief(req)
    data.update({
        "description": req.description, "department": req.department.name if req.department_id else None,
        "steps": [{"sequence": s.sequence, "name": s.name, "status": s.status, "decided_by": _person(s.decided_by),
                   "on_behalf_of": _person(s.on_behalf_of), "decided_at": s.decided_at, "comment": s.comment, "due_at": s.due_at}
                  for s in req.steps.select_related("decided_by", "on_behalf_of")],
        "history": [{"kind": h.kind, "author": _person(h.author), "body": h.body, "at": h.created_at}
                    for h in req.history.select_related("author")],
        "can_decide": allowed, "deciding_on_behalf_of": _person(on_behalf),
        "can_cancel": req.requested_by_id == request.user.pk and req.status in ("pending", "changes_requested"),
        "can_resubmit": req.requested_by_id == request.user.pk and req.status == "changes_requested",
        "can_request_changes": allowed and req.policy.allow_request_changes,
    })
    return data


class ApprovalDetailView(OSView):
    def get(self, request, pk):
        return Response(detail_payload(request, self.authz, pk))


class ApprovalActionView(OSView):
    def post(self, request, pk, action):
        req = load_visible(self.authz, pk)[0]
        comment = str(request.data.get("comment", ""))[:2000]
        if action in {"approve", "reject", "request_changes"}:
            req = engine.decide(request, req, action, comment=comment)
        elif action == "resubmit":
            req = engine.resubmit(request, req, title=request.data.get("title"), description=request.data.get("description"),
                                  amount=request.data.get("amount"), comment=comment)
        elif action == "cancel":
            req = engine.cancel(request, req, reason=comment)
        elif action == "comment":
            if not comment.strip():
                raise DomainError("Write a comment.", code="validation_error")
            ApprovalComment.objects.create(request=req, author=request.user, kind="comment", body=comment)
        else:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return Response(detail_payload(request, self.authz, req.pk))


class SubmittablePoliciesView(OSView):
    """Approval types this person can raise (each policy's submit permission is checked)."""

    def get(self, request):
        ctx = self.authz
        out = []
        for p in ApprovalPolicy.objects.filter(organization=ctx.organization, is_active=True).prefetch_related("levels"):
            if ctx.has(p.submit_permission):
                out.append({"key": p.key, "name": p.name, "description": p.description, "module": p.module, "currency": p.currency,
                            "requires_amount": p.requires_amount, "levels": [{"name": lv.name, "min_amount": str(lv.min_amount)} for lv in p.levels.all()]})
        return Response({"results": out})


class DelegationsView(OSView):
    def get(self, request):
        now = timezone.now()
        given = ApprovalDelegation.objects.filter(delegator=request.user, revoked_at__isnull=True, ends_at__gt=now).select_related("delegate", "policy")
        received = ApprovalDelegation.objects.filter(delegate=request.user, revoked_at__isnull=True, ends_at__gt=now).select_related("delegator", "policy")
        fmt = lambda d, who: {"id": str(d.pk), "person": _person(who), "policy": d.policy.name if d.policy_id else "All approvals",  # noqa: E731
                              "starts_at": d.starts_at, "ends_at": d.ends_at, "reason": d.reason}
        return Response({"given": [fmt(d, d.delegate) for d in given], "received": [fmt(d, d.delegator) for d in received]})

    def post(self, request):
        ctx = self.authz
        delegate = User.objects.filter(pk=request.data.get("delegate_id"), os_account__organization=ctx.organization,
                                       os_account__status="active", os_account__kind="employee").first()
        if delegate is None or delegate.pk == request.user.pk:
            raise DomainError("Choose a colleague to delegate to.", code="validation_error", details={"delegateId": ["Choose a colleague."]})
        starts = parse_datetime(str(request.data.get("starts_at") or "")) or timezone.now()
        ends = parse_datetime(str(request.data.get("ends_at") or ""))
        if ends is None or ends <= starts or ends - starts > timedelta(days=90):
            raise DomainError("Choose an end date after the start (at most 90 days).", code="validation_error", details={"endsAt": ["Invalid period."]})
        policy = None
        if request.data.get("policy_key"):
            policy = ApprovalPolicy.objects.filter(organization=ctx.organization, key=request.data["policy_key"]).first()
        d = ApprovalDelegation.objects.create(delegator=request.user, delegate=delegate, policy=policy, starts_at=starts, ends_at=ends,
                                              reason=str(request.data.get("reason", ""))[:200])
        record(request, "approval.delegation.created", category="approval", resource=d, resource_label=f"to {delegate.full_name}",
               new={"delegate": str(delegate.pk), "ends_at": ends, "policy": policy.key if policy else None})
        notify(delegate, "workflow", f"{request.user.full_name} delegated approvals to you",
               body=f"Until {ends:%d %b %Y}. {d.reason}".strip(), link="/approvals")
        return Response({"id": str(d.pk)}, status=status.HTTP_201_CREATED)


class DelegationDetailView(OSView):
    def delete(self, request, pk):
        d = ApprovalDelegation.objects.filter(pk=pk, delegator=request.user, revoked_at__isnull=True).first()
        if d is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        d.revoked_at = timezone.now()
        d.save(update_fields=["revoked_at", "updated_at"])
        record(request, "approval.delegation.revoked", category="approval", resource=d)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Approval policies (administration) ------------------------------------------------
def policy_payload(p: ApprovalPolicy) -> dict:
    return {"id": str(p.pk), "key": p.key, "name": p.name, "description": p.description, "module": p.module,
            "approval_type": p.approval_type, "submit_permission": p.submit_permission, "currency": p.currency,
            "requires_amount": p.requires_amount, "is_active": p.is_active,
            "levels": [{"sequence": lv.sequence, "name": lv.name, "approver_permission": lv.approver_permission,
                        "min_amount": str(lv.min_amount), "enforce_limit": lv.enforce_limit, "escalate_after_hours": lv.escalate_after_hours}
                       for lv in p.levels.all()],
            "open_requests": p.requests.filter(status="pending").count()}


class PoliciesAdminView(OSView):
    permissions = {"GET": "workflows.policy.view", "POST": "workflows.policy.configure"}

    def get(self, request):
        qs = ApprovalPolicy.objects.filter(organization=self.authz.organization).prefetch_related("levels")
        return Response({"results": [policy_payload(p) for p in qs], "approval_types": registry.APPROVAL_TYPES})

    def post(self, request):
        return _save_policy(request, self.authz, None)


class PolicyAdminDetailView(OSView):
    permissions = {"GET": "workflows.policy.view", "PATCH": "workflows.policy.configure"}

    def _get(self, pk):
        p = ApprovalPolicy.objects.filter(pk=pk, organization=self.authz.organization).prefetch_related("levels").first()
        if p is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return p

    def get(self, request, pk):
        return Response(policy_payload(self._get(pk)))

    def patch(self, request, pk):
        return _save_policy(request, self.authz, self._get(pk))


def _save_policy(request, ctx, policy):
    d = request.data
    errors = {}
    submit_perm = d.get("submit_permission", policy.submit_permission if policy else "")
    if not registry.is_known(submit_perm):
        errors["submitPermission"] = ["Unknown permission."]
    if d.get("approval_type", policy.approval_type if policy else "general") not in registry.APPROVAL_TYPES:
        errors["approvalType"] = ["Unknown approval type."]
    levels = d.get("levels")
    if levels is not None:
        if not levels:
            errors["levels"] = ["Add at least one level."]
        for lv in levels:
            if not registry.is_known(lv.get("approver_permission", "")):
                errors["levels"] = [f"Unknown approver permission: {lv.get('approver_permission')}"]
    if errors:
        raise DomainError("Please check the highlighted fields.", code="validation_error", details=errors)
    before = policy_payload(policy) if policy else None
    with transaction.atomic():
        if policy is None:
            key = str(d.get("key", "")).strip()
            if not key or ApprovalPolicy.objects.filter(organization=ctx.organization, key=key).exists():
                raise DomainError("Choose a unique key, e.g. finance.expense.", code="validation_error", details={"key": ["Must be unique."]})
            policy = ApprovalPolicy(organization=ctx.organization, key=key)
        for f in ("name", "description", "module", "approval_type", "submit_permission", "currency", "requires_amount", "is_active"):
            if f in d:
                setattr(policy, f, d[f])
        policy.module = policy.module or policy.key.split(".")[0]
        policy.save()
        if levels is not None:
            policy.levels.all().delete()
            for i, lv in enumerate(sorted(levels, key=lambda x: int(x.get("sequence", 0) or 0)), start=1):
                ApprovalLevel.objects.create(policy=policy, sequence=i, name=str(lv.get("name") or f"Level {i}")[:80],
                                             approver_permission=lv["approver_permission"], min_amount=Decimal(str(lv.get("min_amount") or 0)),
                                             enforce_limit=bool(lv.get("enforce_limit", True)),
                                             escalate_after_hours=int(lv["escalate_after_hours"]) if lv.get("escalate_after_hours") else None)
    policy = ApprovalPolicy.objects.prefetch_related("levels").get(pk=policy.pk)
    after = policy_payload(policy)
    record(request, "workflows.policy.update" if before else "workflows.policy.create", category="config", module="workflows",
           resource=policy, old=before, new=after)
    return Response(after, status=status.HTTP_200_OK if before else status.HTTP_201_CREATED)


# --- Tasks ------------------------------------------------------------------------------
def task_payload(t: Task, user) -> dict:
    return {"id": str(t.pk), "title": t.title, "description": t.description, "status": t.status, "priority": t.priority,
            "due_at": t.due_at, "completed_at": t.completed_at, "assignee": _person(t.assignee), "created_by": _person(t.created_by),
            "module": t.module, "link_path": t.link_path, "created_at": t.created_at,
            "overdue": bool(t.due_at and t.due_at < timezone.now() and t.status in ("open", "in_progress")),
            "can_edit": user.pk in (t.assignee_id, t.created_by_id), "snoozed_until": t.snoozed_until,
            "comments": [{"author": c.author.full_name if c.author_id else None, "body": c.body, "at": c.created_at} for c in t.comments.select_related("author")[:20]]}


class TasksView(OSView):
    def get(self, request):
        user, now = request.user, timezone.now()
        view = request.query_params.get("view", "assigned")
        qs = Task.objects.select_related("assignee", "created_by")
        active = ["open", "in_progress"]
        qs = {
            "assigned": qs.filter(assignee=user, status__in=active),
            "created": qs.filter(created_by=user).exclude(assignee=user),
            "overdue": qs.filter(assignee=user, status__in=active, due_at__lt=now),
            "upcoming": qs.filter(assignee=user, status__in=active, due_at__gte=now, due_at__lt=now + timedelta(days=7)),
            "done": qs.filter(Q(assignee=user) | Q(created_by=user), status__in=["done", "cancelled"]).order_by("-completed_at", "-updated_at"),
        }.get(view)
        if qs is None:
            raise DomainError("Unknown view.", code="validation_error")
        return self.paginate_tasks(qs)

    def paginate_tasks(self, qs):
        from apps.core.api.pagination import DefaultPagination

        p = DefaultPagination()
        page = p.paginate_queryset(qs, self.request, view=self)
        return p.get_paginated_response([task_payload(t, self.request.user) for t in page])

    def post(self, request):
        ctx = self.authz
        d = request.data
        title = str(d.get("title", "")).strip()
        if len(title) < 2:
            raise DomainError("Give the task a title.", code="validation_error", details={"title": ["Give the task a title."]})
        assignee = request.user
        if d.get("assignee_id") and str(d["assignee_id"]) != str(request.user.pk):
            assignee = User.objects.filter(pk=d["assignee_id"], os_account__organization=ctx.organization, os_account__status="active").first()
            if assignee is None:
                raise DomainError("Choose someone in your organization.", code="validation_error", details={"assigneeId": ["Unknown person."]})
            emp = getattr(assignee, "employee", None)
            target = {"owner": assignee.pk}
            if emp and emp.org_unit_id:
                target["unit"] = emp.org_unit_id
            if emp and emp.department_id:
                target["department"] = emp.department_id
            if emp and emp.team_id:
                target["team"] = emp.team_id
            ctx.require("workflows.task.assign", **target)
        due = parse_datetime(str(d.get("due_at") or "")) if d.get("due_at") else None
        priority = d.get("priority") if d.get("priority") in Task.Priority.values else "normal"
        t = Task.objects.create(organization=ctx.organization, title=title[:160], description=str(d.get("description", ""))[:4000], assignee=assignee,
                                created_by=request.user, priority=priority, due_at=due)
        if assignee.pk != request.user.pk:
            notify(assignee, "task_assigned", f"New task: {t.title}", body=f"From {request.user.full_name}", link=f"/tasks?open={t.pk}",
                   priority="important" if priority in ("high", "urgent") else "normal")
        record(request, "workflows.task.create", category="data", module="workflows", resource=t, new={"assignee": str(assignee.pk), "due_at": due})
        return Response(task_payload(t, request.user), status=status.HTTP_201_CREATED)


class TaskDetailView(OSView):
    def patch(self, request, pk):
        t = Task.objects.select_related("assignee", "created_by").filter(pk=pk).filter(Q(assignee=request.user) | Q(created_by=request.user)).first()
        if t is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        d = request.data
        if "status" in d:
            if d["status"] not in Task.Status.values:
                raise DomainError("Unknown status.", code="validation_error")
            t.status = d["status"]
            t.completed_at = timezone.now() if t.status == "done" else None
            if t.status == "done" and t.created_by_id != request.user.pk:
                notify(t.created_by, "workflow", f"Task completed: {t.title}", body=f"By {request.user.full_name}", link=f"/tasks?open={t.pk}")
        if "title" in d and str(d["title"]).strip():
            t.title = str(d["title"]).strip()[:160]
        if "description" in d:
            t.description = str(d["description"])[:4000]
        if "priority" in d and d["priority"] in Task.Priority.values:
            t.priority = d["priority"]
        if "due_at" in d:
            t.due_at = parse_datetime(str(d["due_at"])) if d["due_at"] else None
        if "snooze_hours" in d:
            hrs = int(d["snooze_hours"] or 0)
            t.snoozed_until = timezone.now() + timedelta(hours=min(max(hrs, 0), 24 * 14)) if hrs else None
        if "assignee_id" in d and str(d["assignee_id"]) != str(t.assignee_id):
            if t.created_by_id != request.user.pk and not self.authz.has("workflows.task.assign"):
                raise DomainError("Only the creator or someone who can assign tasks can reassign this.", code="permission_denied", status_code=403)
            new = User.objects.filter(pk=d["assignee_id"], os_account__organization=self.authz.organization, os_account__status="active").first()
            if new is None:
                raise DomainError("Choose someone in your organization.", code="validation_error")
            if new.pk != request.user.pk:
                emp = getattr(new, "employee", None)
                self.authz.require("workflows.task.assign", owner=new.pk, **({"unit": emp.org_unit_id} if emp and emp.org_unit_id else {}))
                notify(new, "task_assigned", f"Task reassigned to you: {t.title}", body=f"From {request.user.full_name}", link=f"/tasks?open={t.pk}")
            t.assignee = new
        if d.get("comment"):
            from .models import TaskComment

            TaskComment.objects.create(task=t, author=request.user, body=str(d["comment"])[:2000])
        t.save()
        return Response(task_payload(t, request.user))


class PeoplePickerView(OSView):
    """Colleagues for assignee/delegate pickers: active employee accounts in the organization (name + designation only)."""

    def get(self, request):
        from apps.access.models import OSAccount

        q = str(request.query_params.get("q", "")).strip()
        qs = OSAccount.objects.filter(organization=self.authz.organization, status="active", kind="employee").select_related("user", "user__employee__designation")
        if q:
            qs = qs.filter(Q(user__full_name__icontains=q) | Q(user__email__icontains=q) | Q(user__employee__employee_id__iexact=q))
        out = []
        for a in qs.order_by("user__full_name")[:20]:
            emp = getattr(a.user, "employee", None)
            out.append({"id": str(a.user_id), "full_name": a.user.full_name or a.user.email,
                        "designation": emp.designation.name if emp and emp.designation else None})
        return Response({"results": out})

