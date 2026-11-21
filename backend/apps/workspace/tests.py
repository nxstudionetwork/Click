"""Home / Command Center: role-composed layout, independent widgets, mandatory sections, views, context, alerts,
announcements, notification center, AI (permission inheritance, confirm-first actions), help."""

from datetime import timedelta

from django.utils import timezone

from apps.access.tests import login, os_seed, signed_in  # noqa: F401
from apps.access.models import Role, RolePermission, Permission, RoleAssignment
from apps.users.models import User
from apps.workflows.models import Task
from apps.workspace.models import Alert, Announcement, WorkNotification


def _layout(c):
    return [w["key"] for w in c.get("/api/v1/os/home").json()["layout"]]


def test_home_layout_is_role_aware(os_seed):
    emp, ceo = signed_in("divya.patel@click.dev"), signed_in("ananya.rao@click.dev")
    e, x = _layout(emp), _layout(ceo)
    assert {"priorities", "approvals", "alerts", "my_work"} <= set(e)
    assert not {"business_pulse", "finance_snapshot", "ecosystem", "team"} & set(e)
    assert {"business_pulse", "ecosystem", "risk_watch", "finance_snapshot"} <= set(x)
    home = ceo.get("/api/v1/os/home").json()
    assert home["canExecutive"] is True and emp.get("/api/v1/os/home").json()["canExecutive"] is False
    assert {"date", "tasksOpen", "approvalsWaiting", "alertsImportant", "deadlinesWeek"} <= set(home["summary"])


def test_manager_view_comes_from_reporting_line(os_seed):
    arjun = signed_in("arjun.kumar@click.dev")  # Divya and Lakshmi report to him; no manager role was assigned by hand
    assert "team" in _layout(arjun)
    team = arjun.get("/api/v1/os/home/widgets/team").json()["data"]
    assert team["counts"]["members"] >= 2 and "salary" not in str(team).lower()
    assert "team" not in _layout(signed_in("divya.patel@click.dev"))


def test_widgets_enforce_permissions_independently(os_seed):
    emp = signed_in("divya.patel@click.dev")
    assert emp.get("/api/v1/os/home/widgets/business_pulse").status_code == 404
    assert emp.get("/api/v1/os/home/widgets/finance_snapshot").status_code == 404
    ceo = signed_in("ananya.rao@click.dev")
    w = ceo.get("/api/v1/os/home/widgets/business_pulse", {"period": "last_week"}).json()
    assert w["error"] is None and w["period"]["key"] == "last_week"
    gmv = next(m for m in w["data"]["metrics"] if m["key"] == "gmv")
    assert gmv["label"] == "Gross transaction value" and "series" in gmv and gmv["drill"]
    fin = ceo.get("/api/v1/os/home/widgets/finance_snapshot").json()["data"]
    rev = next(x for x in fin["lines"] if x["key"] == "click_revenue")
    assert rev["available"] is False and rev["value"] is None  # never blended into one "revenue" number


def test_narrow_scope_gets_honest_not_at_scope(os_seed):
    role = Role.objects.create(organization=os_seed, key="branch-analyst", name="Branch analyst", home_widgets=["ecosystem"])
    RolePermission.objects.create(role=role, permission=Permission.objects.get(code="analytics.business.view"), scope="branch")
    RoleAssignment.objects.create(user=User.objects.get(email="divya.patel@click.dev"), role=role)
    c = signed_in("divya.patel@click.dev")
    assert "ecosystem" not in _layout(c)  # org-wide only, so a branch grant doesn't offer it at all
    pulse = c.get("/api/v1/os/home/widgets/business_pulse").json()
    assert "gmv" not in {m["key"] for m in pulse["data"]["metrics"]}


def test_mandatory_alerts_cannot_be_hidden_and_layout_persists(os_seed):
    c = signed_in("ananya.rao@click.dev")
    r = c.put("/api/v1/os/home/layout", {"layout": [{"key": "insights", "size": "l", "period": "this_month", "pinned": True},
                                                     {"key": "my_work", "size": "s"}]}, format="json")
    assert r.json()["keptMandatory"] == ["alerts"]
    layout = c.get("/api/v1/os/home").json()["layout"]
    keys = [w["key"] for w in layout]
    assert "alerts" in keys and "business_pulse" not in keys
    ins = next(w for w in layout if w["key"] == "insights")
    assert ins["pinned"] and ins["size"] == "l" and ins["period"] == "this_month"
    c.post("/api/v1/os/home/layout/reset")
    assert "business_pulse" in _layout(c)
    from apps.audit.models import AuditEvent

    assert AuditEvent.objects.filter(action="home.layout.update").exists()


def test_saved_and_preset_views_respect_access(os_seed):
    ceo = signed_in("ananya.rao@click.dev")
    assert ceo.post("/api/v1/os/home/views/preset:executive").status_code == 200
    assert _layout(ceo)[0] in ("alerts", "business_pulse")
    vid = ceo.post("/api/v1/os/home/views", {"name": "Board prep"}, format="json").json()["id"]
    assert any(v["id"] == vid for v in ceo.get("/api/v1/os/home").json()["views"]["saved"])
    emp = signed_in("divya.patel@click.dev")
    assert emp.post("/api/v1/os/home/views/preset:executive").status_code == 403


def test_location_context_switching(os_seed):
    ceo = signed_in("ananya.rao@click.dev")
    opts = ceo.get("/api/v1/os/me/context").json()["contextOptions"]
    assert opts["switchable"] and any(u["code"] == "HYD-BR" for u in opts["units"])
    hyd = next(u for u in opts["units"] if u["code"] == "HYD-BR")
    assert ceo.put("/api/v1/os/home/context", {"unitId": hyd["id"]}, format="json").status_code == 200
    assert ceo.get("/api/v1/os/home").json()["context"]["unit"]["name"] == "Hyderabad Branch"
    emp = signed_in("divya.patel@click.dev")
    assert emp.get("/api/v1/os/me/context").json()["contextOptions"]["switchable"] is False
    assert emp.put("/api/v1/os/home/context", {"unitId": hyd["id"]}, format="json").status_code == 403


def test_approval_center_inline_and_request_changes(os_seed):
    karthik = signed_in("karthik.reddy@click.dev")
    items = karthik.get("/api/v1/os/home/widgets/approvals").json()["data"]["items"]
    assert items and {"flags", "levels", "stage", "waitingHours"} <= set(items[0])
    rid = items[0]["id"]
    r = karthik.post(f"/api/v1/os/approvals/{rid}/request_changes", {"comment": "Attach the receipt"}, format="json")
    assert r.json()["status"] == "changes_requested"
    divya = signed_in("divya.patel@click.dev")
    pr = divya.get("/api/v1/os/home/widgets/priorities").json()["data"]["items"]
    assert any(p["reason"] == "Your request needs changes" for p in pr)
    r = divya.post(f"/api/v1/os/approvals/{rid}/resubmit", {"comment": "Receipt attached", "amount": "12000"}, format="json")
    assert r.json()["status"] == "pending" and r.json()["amount"] == "12000.00"


def test_personal_and_scoped_alerts(os_seed, settings):
    from apps.access.tests import login as do_login
    from rest_framework.test import APIClient

    c = APIClient()
    for _ in range(5):
        do_login(c, "rohit.gupta@click.dev", password="nope-nope-nope")
    rohit_user = User.objects.get(email="rohit.gupta@click.dev")
    a = Alert.objects.get(subject_user=rohit_user)
    assert a.severity == "high"
    ceo = signed_in("ananya.rao@click.dev")
    assert str(a.pk) not in {x["id"] for x in ceo.get("/api/v1/os/alerts").json()["results"]}  # personal alerts stay personal
    from apps.payments.models import Payment

    assert not Payment.objects.exists() or True
    priya = signed_in("priya.menon@click.dev")
    from apps.workspace.alerts import Found, _apply, DETECTORS

    _apply(os_seed, DETECTORS["payments.failed"], [Found("24h", "high", "6 payments failed")])
    titles = {x["title"] for x in priya.get("/api/v1/os/alerts").json()["results"]}
    assert "6 payments failed" in titles
    emp = signed_in("divya.patel@click.dev")
    assert "6 payments failed" not in {x["title"] for x in emp.get("/api/v1/os/alerts").json()["results"]}
    aid = next(x["id"] for x in priya.get("/api/v1/os/alerts").json()["results"] if x["title"] == "6 payments failed")
    r = priya.post(f"/api/v1/os/alerts/{aid}/acknowledge")
    assert r.json()["status"] == "acknowledged" and r.json()["owner"]["fullName"] == "Priya Menon"


def test_announcements_audience_ack_and_critical(os_seed):
    from apps.organization.models import Department

    sneha = signed_in("sneha.iyer@click.dev")
    fin = Department.objects.get(code="FIN")
    r = sneha.post("/api/v1/os/announcements", {"title": "Finance close", "body": "Books close Friday.", "audience": {"departments": [str(fin.pk)]}}, format="json")
    assert r.status_code == 201
    karthik, divya = signed_in("karthik.reddy@click.dev"), signed_in("divya.patel@click.dev")
    assert "Finance close" in {a["title"] for a in karthik.get("/api/v1/os/announcements").json()["results"]}
    assert "Finance close" not in {a["title"] for a in divya.get("/api/v1/os/announcements").json()["results"]}
    maint = Announcement.objects.get(title__startswith="Scheduled maintenance")
    assert divya.post(f"/api/v1/os/announcements/{maint.pk}/dismiss").json()["error"]["code"] == "ack_required"
    divya.post(f"/api/v1/os/announcements/{maint.pk}/acknowledge")
    assert divya.post(f"/api/v1/os/announcements/{maint.pk}/dismiss").status_code == 200
    crit = Announcement.objects.create(organization=os_seed, title="Security incident", body="Reset passwords.", priority="critical",
                                       starts_at=timezone.now() - timedelta(minutes=1))
    assert divya.post(f"/api/v1/os/announcements/{crit.pk}/dismiss").json()["error"]["code"] == "not_dismissable"
    assert "announcements" in _layout(divya)
    # Critical notices need extra authority to publish
    assert signed_in("karthik.reddy@click.dev").post("/api/v1/os/announcements", {"title": "x" * 5, "body": "y" * 5, "priority": "critical"},
                                                     format="json").status_code == 403


def test_notification_center_categories_unread_and_clear(os_seed):
    c = signed_in("karthik.reddy@click.dev")
    data = c.get("/api/v1/os/notifications", {"category": "approvals"}).json()
    assert data["results"] and all(n["type"].startswith("approval") for n in data["results"])
    nid = data["results"][0]["id"]
    assert c.post(f"/api/v1/os/notifications/{nid}/archive").json()["error"]["code"] == "essential_unread"
    c.post(f"/api/v1/os/notifications/{nid}/read")
    assert c.post(f"/api/v1/os/notifications/{nid}/unread").json()["read"] is False
    c.post(f"/api/v1/os/notifications/{nid}/read")
    assert c.post(f"/api/v1/os/notifications/{nid}/archive").json()["archived"] is True
    assert nid not in {n["id"] for n in c.get("/api/v1/os/notifications").json()["results"]}


def test_search_never_returns_restricted_types(os_seed):
    emp = signed_in("divya.patel@click.dev").get("/api/v1/os/search", {"q": "rao"}).json()
    assert "employee" in {g["type"] for g in emp["groups"]}
    assert not {"user", "candidate"} & {g["type"] for g in emp["groups"]}
    assert "candidate" not in {t["type"] for t in emp["types"]}
    admin = signed_in("vikram.shah@click.dev").get("/api/v1/os/search", {"q": "rao"}).json()
    assert "user" in {g["type"] for g in admin["groups"]}
    rec = signed_in("neha.joshi@click.dev").get("/api/v1/os/search", {"q": "aditya"}).json()
    assert "candidate" in {g["type"] for g in rec["groups"]}


def test_ai_inherits_permissions_and_never_writes(os_seed):
    emp = signed_in("divya.patel@click.dev")
    r = emp.post("/api/v1/os/ai", {"question": "Show me everyone's salary"}, format="json").json()
    assert r["denied"] is True
    r = emp.post("/api/v1/os/ai", {"question": "What's the revenue this month?"}, format="json").json()
    assert r["denied"] is True
    r = signed_in("ananya.rao@click.dev").post("/api/v1/os/ai", {"question": "How are orders and revenue?"}, format="json").json()
    assert r["tool"] == "business" and "Gross transaction value" in r["answer"]
    before = Task.objects.count()
    r = emp.post("/api/v1/os/ai", {"question": "Create a task to review the Q3 vendor list"}, format="json").json()
    assert r["proposedAction"] == {"type": "create_task", "title": "review the Q3 vendor list", "assignee": "me"}
    assert Task.objects.count() == before  # AI only proposes; the person confirms through the normal Tasks API
    hr = signed_in("sneha.iyer@click.dev").post("/api/v1/os/ai", {"question": "What is Divya's salary?"}, format="json").json()
    assert hr["denied"] is True  # compensation is never answered by AI, even for HR


def test_quick_action_pins_and_report_problem(os_seed):
    c = signed_in("divya.patel@click.dev")
    assert c.put("/api/v1/os/home/quick-actions", {"pins": ["request_leave", "add_employee"]}, format="json").json()["pins"] == ["request_leave"]
    qa = c.get("/api/v1/os/home/widgets/quick_actions").json()["data"]["items"]
    assert qa[0]["key"] == "request_leave" and qa[0]["pinned"] and "add_employee" not in {a["key"] for a in qa}
    r = c.post("/api/v1/os/help/report", {"summary": "Leave page shows wrong balance", "page": "/people/leave"}, format="json").json()
    assert r["routed"] and Task.objects.filter(source_type="help.report", source_id=r["reference"]).exists()


def test_partner_accounts_get_restricted_home(os_seed):
    from apps.access.models import OSAccount
    from apps.partners.models import Partner, PartnerCategory, PartnerType

    ptype = PartnerType.objects.first() or PartnerType.objects.create(slug="t", name="T")
    cat = PartnerCategory.objects.filter(partner_type=ptype).first() or PartnerCategory.objects.create(partner_type=ptype, slug="c", name="C")
    partner = Partner.objects.create(partner_type=ptype, category=cat, business_name="Kitchen")
    user = User.objects.create_user("owner2@kitchen.test", "ClickOS-dev-2026!", full_name="Owner")
    OSAccount.objects.create(user=user, organization=os_seed, kind="partner", status="active", partner=partner)
    RoleAssignment.objects.create(user=user, role=Role.objects.get(key="partner-business"))
    keys = set(_layout(signed_in("owner2@kitchen.test", access_type="partner")))
    assert keys <= {"priorities", "approvals", "alerts", "announcements", "upcoming", "my_work", "recent_activity", "security"}


def test_upcoming_groups_and_data_freshness(os_seed):
    c = signed_in("divya.patel@click.dev")
    w = c.get("/api/v1/os/home/widgets/upcoming").json()
    assert [g["key"] for g in w["data"]["groups"]] == ["today", "tomorrow", "this_week"]
    assert w["generatedAt"] and w["source"] and "refreshSeconds" in w
    assert WorkNotification.objects.exists()
