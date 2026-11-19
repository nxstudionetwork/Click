"""Identity & Access plugs into Business AI and global search through the shared registries — no separate copies.
Every tool declares the permission it needs and answers only from data the asker may see."""

import re

from apps.workspace import ai as ai_mod

from . import governance as gov
from . import registry
from .authz import AuthContext
from .models import OSAccount

PHRASES = {
    "approve refund": "payments.refund.approve", "refund": "payments.refund.approve", "salary": "people.payroll.view",
    "payroll": "people.payroll.view", "export customer": "sales.customer.export", "customer data": "sales.customer.export",
    "manage partner": "partners.partner.edit", "approve expense": "finance.expense.approve", "approve payment": "finance.payment.approve",
    "purchase order": "procurement.order.approve", "assign role": "access.role.assign", "delete invoice": "finance.invoice.delete",
    "journal": "finance.ledger.approve", "settlement": "finance.settlement.approve",
}


def _who(ctx: AuthContext, q: str) -> dict:
    ql = q.lower()
    code = next((m for m in re.findall(r"[a-z_]+\.[a-z_]+\.[a-z_]+", ql) if registry.is_known(m)), None)
    if code is None:
        code = next((c for p, c in PHRASES.items() if p in ql and registry.is_known(c)), None)
    if code is None or "admin" in ql:
        rows = [r for r in gov.privileged(ctx.organization) if r["admin_areas"]]
        names = ", ".join(f"{r['name']} ({'/'.join(r['admin_areas'])}{'' if r['mfa'] else ', no 2-step'})" for r in rows[:15])
        return {"answer": f"{len(rows)} people hold administrative access: {names or 'none'}.", "link": "/access/privileged"}
    rows = gov.who_has(ctx.organization, code)
    if not rows:
        return {"answer": f"Nobody currently holds {code}.", "link": f"/access/who?code={code}"}
    names = "; ".join(f"{r['name']} — {r['role']} at {r['effective_scope']} scope" + (" (blocked until 2-step is on)" if r["mfa_blocked"] else "")
                      for r in rows[:15])
    return {"answer": f"{len(rows)} people can use {code}: {names}.", "link": f"/access/who?code={code}"}


def _conflicts(ctx: AuthContext, q: str) -> dict:
    out = []
    for acct in OSAccount.objects.filter(organization=ctx.organization, status="active").select_related("user"):
        c = AuthContext(acct.user, acct)
        for v in gov.sod_conflicts(ctx.organization, [k for k in c.grants if c.has(k)], acct.user):
            if not v["exception"]:
                out.append(f"{acct.user.full_name}: {v['name']} ({v['severity']})")
    if not out:
        return {"answer": "No segregation-of-duties conflicts without an approved exception.", "link": "/access/sod"}
    return {"answer": f"{len(out)} conflicts: " + "; ".join(out[:12]) + ".", "link": "/access/sod"}


def _expired(ctx: AuthContext, q: str) -> dict:
    hy = gov.orphaned(ctx.organization)
    from django.utils import timezone

    from .models import RoleAssignment

    temp = RoleAssignment.objects.filter(role__organization=ctx.organization, is_active=True, valid_until__isnull=False).select_related("user", "role")
    now = timezone.now()
    ended = [f"{a.user.full_name} ({a.role.name})" for a in temp if a.valid_until <= now]
    soon = [f"{a.user.full_name} ({a.role.name}, ends {a.valid_until:%d %b})" for a in temp if a.valid_until > now]
    parts = [f"Temporary access past its end date: {', '.join(ended) or 'none'}", f"active temporary access: {', '.join(soon[:10]) or 'none'}",
             f"{len(hy)} accounts need hygiene review"]
    return {"answer": ". ".join(parts) + ".", "link": "/access/hygiene"}


def _excessive(ctx: AuthContext, q: str) -> dict:
    rows = []
    for acct in OSAccount.objects.filter(organization=ctx.organization, status="active").select_related("user"):
        r = gov.risk(acct)
        if r["score"] >= 30:
            rows.append((r["score"], acct.user.full_name, r["factors"]))
    rows.sort(reverse=True)
    if not rows:
        return {"answer": "No accounts stand out for excessive access right now.", "link": "/access/privileged"}
    return {"answer": "Accounts to review first (internal indicator, not a verdict): " +
                      "; ".join(f"{n} {s}/100 — {', '.join(f[:3])}" for s, n, f in rows[:8]) + ".", "link": "/access/privileged"}


ai_mod.EXTRA_TOOLS += [
    ai_mod.Tool("access_who", "Who has access", "access.analysis.view",
                ("who has", "who can", "has access to", "administrator access", "admin access", "who holds"), _who),
    ai_mod.Tool("access_conflicts", "Segregation-of-duties conflicts", "access.sod.view",
                ("conflicting permission", "segregation of duties", "sod conflict", "permission conflict"), _conflicts),
    ai_mod.Tool("access_expired", "Temporary & orphaned access", "access.analysis.view",
                ("expired temporary", "temporary access", "orphaned account", "expiring access"), _expired),
    ai_mod.Tool("access_excessive", "Potentially excessive access", "access.analysis.view",
                ("excessive access", "risky access", "too much access", "over-privileged"), _excessive),
]
