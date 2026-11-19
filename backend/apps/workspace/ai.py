"""
Click Business AI foundation.

The AI never queries the database itself. It may only call *tools*, and every tool declares the permission it needs
and runs with the asking user's AuthContext (same scopes as the rest of the OS). If the user can't see payroll, no
tool will return payroll to them, whatever the question says.

    Provider (CLICK_OS_AI_PROVIDER, dotted path) → chooses tools → tools run as the user → provider phrases the answer
    Default provider "basic": keyword routing, answers only from tool results; never invents figures.

A language-model provider can be plugged in later by implementing BusinessAIProvider.answer(); it receives only the
tools this user is allowed to call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from django.conf import settings
from django.utils.module_loading import import_string

from apps.access.authz import AuthContext


@dataclass(frozen=True)
class Tool:
    key: str
    label: str
    permission: str | None
    keywords: tuple[str, ...]
    run: Callable[[AuthContext, str], dict]
    org_wide: bool = False


def _approvals(ctx, q):
    from apps.workflows.selectors import inbox_for

    inbox = inbox_for(ctx)
    if not inbox:
        return {"answer": "Nothing is waiting for your approval right now."}
    return {"answer": f"{len(inbox)} request{'s' if len(inbox) != 1 else ''} waiting for your decision.",
            "items": [{"title": r.title, "subtitle": f"{r.reference} · {r.requested_by.full_name}", "path": f"/approvals/{r.pk}"} for r in inbox[:5]]}


def _tasks(ctx, q):
    from apps.workspace.widgets import Params, my_work

    d = my_work(ctx, Params())
    c = d["counts"]
    return {"answer": f"You have {c['open']} open task{'s' if c['open'] != 1 else ''}; {c['overdue']} overdue, {c['due_week']} due this week.",
            "items": [{"title": t["title"], "subtitle": t["priority"], "path": t["path"]} for t in d["items"]]}


def _snapshot(ctx, q):
    from apps.workspace.widgets import business_snapshot

    d = business_snapshot(ctx)
    parts = [f"{m['label']}: {m['value']}" + (f" ({'+' if m['delta_pct'] >= 0 else ''}{m['delta_pct']}%)" if m.get("delta_pct") is not None else "")
             for m in d["metrics"] if m.get("value") is not None]
    return {"answer": f"{d['period']} — " + "; ".join(parts) + ".", "note": d["note"]}


def _people(ctx, q):
    from apps.workspace.widgets import people_overview_data

    d = people_overview_data(ctx)
    if not d["metrics"]:
        return {"answer": "There are no employee records within your access."}
    return {"answer": "Within your access: " + "; ".join(f"{m['label']}: {m['value']}" for m in d["metrics"]) + "."}


def _operations(ctx, q):
    from apps.workspace.widgets import NotAtScope, Params, operations_overview

    try:
        d = operations_overview(ctx, Params())
    except NotAtScope as e:
        return {"answer": str(e), "denied": True}
    return {"answer": "Operations right now: " + "; ".join(f"{m['label']}: {m['value']}" for m in d["metrics"]) + "."}


def _partner_issues(ctx, q):
    from apps.workspace import alerts as alerts_mod

    rows = [a for a in alerts_mod.visible(ctx) if a.category in ("partner", "compliance")]
    if not rows:
        return {"answer": "No open partner issues within your access."}
    return {"answer": f"{len(rows)} partner issue{'s' if len(rows) != 1 else ''} need attention.",
            "items": [{"title": a.title, "subtitle": f"{a.get_severity_display()} · {a.recommended_action}", "path": a.link_path or "/home"} for a in rows[:6]]}


def _create_task(ctx, q):
    """Never writes. Proposes the task; the person confirms in the UI, which calls the normal Tasks API."""
    import re as _re

    title = _re.sub(r"^(please\s+)?(create|add|make)\s+(a\s+)?(task|todo|reminder)\s*(for me)?\s*(to|:)?\s*", "", q.strip(), flags=_re.I).strip(" .?")
    if len(title) < 3:
        return {"answer": "What should the task say? For example: “Create a task to review the Q3 vendor list.”"}
    return {"answer": f"I can create this task for you: “{title[:160]}”. Confirm to create it.",
            "proposed_action": {"type": "create_task", "title": title[:160], "assignee": "me"}}


def _payroll(ctx, q):
    return {"answer": "Payroll records aren’t in Click Business OS yet. They’ll be available here once the People & HR payroll module is built."}


def _search(ctx, q):
    from apps.workspace.search import search

    term = re.sub(r"^(find|search( for)?|look up|who is|show me|where is)\s+", "", q.strip(), flags=re.I).strip(" ?.")
    groups = search(ctx, term, limit=4)
    if not groups:
        return {"answer": f"I couldn’t find anything you have access to matching “{term}”."}
    items = [{"title": r["title"], "subtitle": f"{g['label']} · {r['subtitle']}", "path": r["path"]} for g in groups for r in g["results"]]
    return {"answer": f"Here’s what I found for “{term}”.", "items": items[:8]}


TOOLS: tuple[Tool, ...] = (
    Tool("create_task", "Create a task (you confirm)", None, ("create a task", "create task", "add a task", "remind me", "make a task"), _create_task),
    Tool("payroll", "Payroll", "people.payroll.view", ("salary", "salaries", "payroll", "payslip", "ctc", "compensation"), _payroll),
    Tool("approvals", "Your approvals", None, ("approval", "approve", "waiting on me", "pending request"), _approvals),
    Tool("tasks", "Your tasks", None, ("task", "to do", "todo", "overdue", "my work"), _tasks),
    Tool("business", "Business snapshot", "analytics.business.view", ("revenue", "gmv", "orders", "sales", "business", "performance", "collection"), _snapshot, org_wide=True),
    Tool("people", "Headcount", "people.employee.view", ("headcount", "employees", "how many staff", "people count"), _people),
    Tool("operations", "Operations summary", "operations.order.view", ("operations", "today's operations", "orders right now", "stale orders"),
         _operations, org_wide=True),
    Tool("partner_issues", "Partner issues", "partners.partner.view", ("partner issue", "partner problem", "partners requiring", "partner compliance"),
         _partner_issues),
    Tool("search", "Search", None, ("find", "search", "look up", "who is", "where is", "show me"), _search),
)
EXTRA_TOOLS: list = []  # modules (People & HR) add their own permission-checked tools


class BusinessAIProvider:
    name = "base"

    def answer(self, ctx: AuthContext, question: str, tools: list[Tool]) -> dict:  # pragma: no cover - interface
        raise NotImplementedError


class BasicBusinessAI(BusinessAIProvider):
    """Deterministic: matches the question to one tool. Answers come only from tool output."""

    name = "basic"

    def answer(self, ctx, question, tools):
        ql = question.lower()
        for tool in (*EXTRA_TOOLS, *TOOLS):  # match against every tool so we can say "no access" instead of "don't know"
            if any(k in ql for k in tool.keywords):
                if tool not in tools:
                    return {"answer": f"You don’t have access to {tool.label.lower()}, so I can’t look that up for you.",
                            "denied": True, "tool": tool.key}
                return {**tool.run(ctx, question), "tool": tool.key}
        return {"answer": "I can help with: " + ", ".join(t.label.lower() for t in tools) + ". Try “What’s waiting for my approval?”",
                "tool": None}


def allowed_tools(ctx: AuthContext) -> list[Tool]:
    out = []
    for t in (*EXTRA_TOOLS, *TOOLS):
        if t.permission is None:
            out.append(t)
        elif ctx.has(t.permission) and (not t.org_wide or ctx.scope(t.permission).org_wide):
            out.append(t)
    return out


def provider() -> BusinessAIProvider | None:
    path = getattr(settings, "CLICK_OS_AI_PROVIDER", "")
    return import_string(path)() if path else None


def ask(ctx: AuthContext, question: str) -> dict:
    p = provider()
    if p is None:
        return {"answer": "Click Business AI is turned off for this environment.", "available": False}
    if not ctx.has("ai.assistant.view"):
        return {"answer": "Click Business AI isn’t enabled for your role.", "available": False, "denied": True}
    return {**p.answer(ctx, question.strip()[:500], allowed_tools(ctx)), "available": True, "provider": p.name}
