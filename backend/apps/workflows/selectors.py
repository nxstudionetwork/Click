from django.db.models import Exists, OuterRef, Q

from apps.access.authz import AuthContext

from .engine import active_delegations_to, can_act
from .models import ApprovalRequest, ApprovalStep


def inbox_for(ctx: AuthContext, limit: int = 200) -> list[ApprovalRequest]:
    """Pending requests the user may decide now (own right or delegation). Candidates are narrowed in SQL, then
    every one is checked by the same rule decide() uses, so the inbox can never show what you can't act on."""
    perms = set(ctx.permission_codes)
    delegating = list(active_delegations_to(ctx.user))
    if not perms and not delegating:
        return []
    if delegating:
        from apps.access.authz import load_context

        for d in delegating:
            perms |= set(load_context(d.delegator).permission_codes)
    current = ApprovalStep.objects.filter(request=OuterRef("pk"), sequence=OuterRef("current_sequence"), approver_permission__in=perms)
    candidates = (ApprovalRequest.objects.filter(organization=ctx.organization, status="pending").exclude(requested_by=ctx.user)
                  .filter(Exists(current)).select_related("policy", "requested_by", "org_unit", "department").order_by("due_at", "created_at")[:limit])
    return [r for r in candidates if can_act(ctx, r)[0]]


def visible_requests(ctx: AuthContext):
    """Requests the user may open: raised by them, decided by them, or within their workflows.request.view scope."""
    scope = ctx.scope("workflows.request.view")
    q = Q(requested_by=ctx.user) | Q(steps__decided_by=ctx.user)
    if not scope.is_empty:
        q |= scope.q(unit="org_unit", department="department", owner="requested_by", organization=None)
    return ApprovalRequest.objects.filter(organization=ctx.organization).filter(q).distinct()
