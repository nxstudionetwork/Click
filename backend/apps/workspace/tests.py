"""Home widgets, search, AI permission inheritance, notifications, modules, onboarding."""

from apps.access.tests import os_seed, signed_in  # noqa: F401
from apps.workspace.models import WorkNotification


def _widget_keys(c):
    return [w["key"] for w in c.get("/api/v1/os/home").json()["widgets"]]


def test_home_is_composed_from_roles_and_permissions(os_seed):
    emp = _widget_keys(signed_in("divya.patel@click.dev"))
    ceo = _widget_keys(signed_in("ananya.rao@click.dev"))
    assert "business_snapshot" not in emp and "finance_overview" not in emp
    assert ceo[0] == "business_snapshot" and "partner_pipeline" in ceo
    w = next(w for w in signed_in("ananya.rao@click.dev").get("/api/v1/os/home").json()["widgets"] if w["key"] == "business_snapshot")
    assert w["error"] is None and {m["key"] for m in w["data"]["metrics"]} >= {"gmv", "orders", "partners"}


def test_narrow_scope_gets_honest_not_at_scope(os_seed):
    from apps.access.models import Role, RolePermission, Permission, RoleAssignment
    from apps.users.models import User

    role = Role.objects.create(organization=os_seed, key="branch-analyst", name="Branch analyst", home_widgets=["business_snapshot"])
    RolePermission.objects.create(role=role, permission=Permission.objects.get(code="analytics.business.view"), scope="branch")
    RoleAssignment.objects.create(user=User.objects.get(email="divya.patel@click.dev"), role=role)
    widgets = signed_in("divya.patel@click.dev").get("/api/v1/os/home").json()["widgets"]
    snap = next(w for w in widgets if w["key"] == "business_snapshot")
    assert snap["data"] is None and snap["error"]["code"] == "not_at_scope"


def test_home_layout_preferences(os_seed):
    c = signed_in("ananya.rao@click.dev")
    c.patch("/api/v1/os/me/preferences", {"home": {"hidden": ["business_snapshot"], "order": ["calendar"]}}, format="json")
    keys = _widget_keys(c)
    assert keys[0] == "calendar" and "business_snapshot" not in keys


def test_search_never_returns_restricted_types(os_seed):
    emp = signed_in("divya.patel@click.dev").get("/api/v1/os/search", {"q": "rao"}).json()
    assert {g["type"] for g in emp["groups"]} == {"employee"}
    assert "user" not in {t["type"] for t in emp["types"]}
    admin = signed_in("vikram.shah@click.dev").get("/api/v1/os/search", {"q": "rao"}).json()
    assert "user" in {g["type"] for g in admin["groups"]}


def test_ai_inherits_permissions(os_seed):
    emp = signed_in("divya.patel@click.dev")
    r = emp.post("/api/v1/os/ai", {"question": "Show me everyone's salary"}, format="json").json()
    assert r["denied"] is True and "don’t have access" in r["answer"]
    r = emp.post("/api/v1/os/ai", {"question": "What's the revenue this month?"}, format="json").json()
    assert r["denied"] is True
    r = signed_in("ananya.rao@click.dev").post("/api/v1/os/ai", {"question": "How are orders and revenue?"}, format="json").json()
    assert r["tool"] == "business" and "Payments captured" in r["answer"]
    r = signed_in("karthik.reddy@click.dev").post("/api/v1/os/ai", {"question": "What is waiting for my approval?"}, format="json").json()
    assert r["tool"] == "approvals" and r["items"]


def test_notifications_read_and_mute_rules(os_seed):
    c = signed_in("karthik.reddy@click.dev")
    data = c.get("/api/v1/os/notifications").json()
    assert data["unread"] >= 1
    c.post("/api/v1/os/notifications/read-all")
    assert c.get("/api/v1/os/notifications/summary").json()["unread"] == 0
    c.patch("/api/v1/os/me/preferences", {"notifications": {"muted": ["business", "security"]}}, format="json")
    muted = c.get("/api/v1/os/me/context").json()["account"]["preferences"]["notifications"]["muted"]
    assert muted == ["business"]  # security is essential and can't be muted
    assert WorkNotification.ESSENTIAL


def test_module_foundation_pages(os_seed):
    emp = signed_in("divya.patel@click.dev")
    assert emp.get("/api/v1/os/modules/legal").status_code == 403
    fin = emp.get("/api/v1/os/modules/finance").json()
    exp = next(r for r in fin["resources"] if r["key"] == "expense")
    assert {a["action"]: a["allowed"] for a in exp["actions"]}["create"] is True
    assert {a["action"]: a["allowed"] for a in exp["actions"]}["approve"] is False


def test_onboarding_cannot_change_org_placement(os_seed):
    c = signed_in("divya.patel@click.dev")
    r = c.post("/api/v1/os/me/onboarding", {"fullName": "Divya P", "timezone": "Asia/Kolkata", "language": "te",
                                            "department": "FIN", "correctionNote": "My team is wrong"}, format="json")
    ctx = r.json()
    assert ctx["account"]["onboardingRequired"] is False and ctx["user"]["fullName"] == "Divya P"
    assert ctx["orgContext"]["department"]["code"] == "OPS"
    assert WorkNotification.objects.filter(recipient__email="sneha.iyer@click.dev", title__startswith="Profile correction").exists()
