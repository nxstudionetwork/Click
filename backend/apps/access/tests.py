"""Business OS foundation: sign-in, sessions, MFA, permissions, scopes, navigation, administration safeguards."""

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.access import security
from apps.access.authz import load_context
from apps.access.models import OSAccount, OSSession, Role, ServiceAccount
from apps.audit.models import AuditEvent
from apps.organization.models import Organization, OrgUnit
from apps.users.models import User

PW = "ClickOS-dev-2026!"
H = {"HTTP_X_CLICK_CLIENT": "business-os"}


@pytest.fixture
def os_seed(db):
    call_command("seed_os_dev", verbosity=0)
    return Organization.objects.get(code="click")


def login(client: APIClient, email: str, access_type="employee", password=PW):
    r = client.post("/api/v1/os/auth/identify", {"identifier": email, "accessType": access_type}, format="json")
    assert r.status_code == 200, r.content
    return client.post("/api/v1/os/auth/password", {"flowToken": r.json()["flowToken"], "password": password}, format="json")


def signed_in(email, access_type="employee") -> APIClient:
    c = APIClient()
    r = login(c, email, access_type)
    assert r.status_code == 200 and r.json()["status"] == "authenticated", r.content
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    return c


# --- sign-in ---------------------------------------------------------------------
def test_identify_same_answer_for_unknown(os_seed):
    c = APIClient()
    a = c.post("/api/v1/os/auth/identify", {"identifier": "nobody@click.dev"}, format="json").json()
    b = c.post("/api/v1/os/auth/identify", {"identifier": "divya.patel@click.dev"}, format="json").json()
    assert a["methods"] == b["methods"] == ["password"] and set(a) == set(b)


def test_login_by_employee_id_and_context(os_seed):
    c = signed_in("EMP-000009")
    ctx = c.get("/api/v1/os/me/context").json()
    assert ctx["employee"]["employeeId"] == "EMP-000009"
    assert [u["code"] for u in ctx["orgContext"]["units"]] == ["IN", "SOUTH", "TG", "HYD", "HYD-BR"]
    assert ctx["account"]["onboardingRequired"] is True
    assert c.cookies.get("click_os_refresh")


def test_wrong_password_generic_then_lockout(os_seed):
    c = APIClient()
    for _ in range(5):
        r = login(c, "divya.patel@click.dev", password="wrong-password")
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    r = login(c, "divya.patel@click.dev")
    assert r.status_code == 423
    assert AuditEvent.objects.filter(action="auth.account_locked").exists()


def test_customer_token_is_not_an_os_session(os_seed):
    c = APIClient()
    r = c.post("/api/v1/auth/login", {"email": "divya.patel@click.dev", "password": PW}, format="json")
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    r = c.get("/api/v1/os/me/context")
    assert r.status_code == 401 and r.json()["error"]["code"] == "os_session_required"


def test_access_type_mismatch(os_seed):
    r = login(APIClient(), "divya.patel@click.dev", access_type="administrator")
    assert r.status_code == 403 and r.json()["error"]["code"] == "access_type_mismatch"
    assert login(APIClient(), "vikram.shah@click.dev", access_type="administrator").status_code == 200
    assert login(APIClient(), "divya.patel@click.dev", access_type="partner").status_code == 403


def test_refresh_rotates_and_logout_revokes(os_seed):
    c = signed_in("divya.patel@click.dev")
    r = c.post("/api/v1/os/auth/refresh", **H)
    assert r.status_code == 200 and r.json()["access"]
    old_cookie = c.cookies["click_os_refresh"].value
    assert c.post("/api/v1/os/auth/logout", **H).status_code == 204
    assert c.get("/api/v1/os/me/context").json()["error"]["code"] == "session_expired"  # immediate, not at token expiry
    c2 = APIClient()
    c2.cookies["click_os_refresh"] = old_cookie
    assert c2.post("/api/v1/os/auth/refresh", **H).status_code == 401


def test_logout_all_and_suspension_are_immediate(os_seed):
    a, b = signed_in("divya.patel@click.dev"), signed_in("divya.patel@click.dev")
    assert a.post("/api/v1/os/auth/logout-all").json()["sessionsEnded"] == 2
    assert b.get("/api/v1/os/me/context").status_code == 401
    d = signed_in("divya.patel@click.dev")
    admin = signed_in("vikram.shah@click.dev")
    acct = OSAccount.objects.get(user__email="divya.patel@click.dev")
    r = admin.post(f"/api/v1/os/admin/users/{acct.pk}/status", {"action": "suspend"}, format="json")
    assert r.status_code == 200, r.content
    r = d.get("/api/v1/os/me/context")
    assert r.status_code == 401
    assert login(APIClient(), "divya.patel@click.dev").json()["error"]["code"] == "account_suspended"


def test_mfa_enrolment_and_sign_in(os_seed):
    c = signed_in("divya.patel@click.dev")
    secret = c.post("/api/v1/os/me/mfa/setup").json()["secret"]
    r = c.post("/api/v1/os/me/mfa/confirm", {"code": security.totp_now(secret)}, format="json")
    assert r.status_code == 200 and len(r.json()["recoveryCodes"]) == 10
    codes = r.json()["recoveryCodes"]
    r = login(APIClient(), "divya.patel@click.dev")
    assert r.json()["status"] == "mfa_required"
    bad = APIClient().post("/api/v1/os/auth/mfa", {"mfaToken": r.json()["mfaToken"], "code": "000000"}, format="json")
    assert bad.status_code == 401
    ok = APIClient().post("/api/v1/os/auth/mfa", {"mfaToken": r.json()["mfaToken"], "code": codes[0]}, format="json")
    assert ok.json()["status"] == "authenticated"
    again = APIClient().post("/api/v1/os/auth/mfa", {"mfaToken": r.json()["mfaToken"], "code": codes[0]}, format="json")
    assert again.status_code == 401  # recovery codes are single-use


def test_invitation_flow(os_seed):
    admin = signed_in("vikram.shah@click.dev")
    r = admin.post("/api/v1/os/admin/users", {"email": "new.joiner@click.dev", "fullName": "New Joiner"}, format="json")
    assert r.status_code == 201, r.content
    token = r.json()["inviteUrl"].rsplit("/", 1)[-1]
    assert login(APIClient(), "new.joiner@click.dev").status_code == 401  # no password yet
    c = APIClient()
    assert c.get("/api/v1/os/auth/invite", {"token": token}).json()["fullName"] == "New Joiner"
    r = c.post("/api/v1/os/auth/invite", {"token": token, "password": "Brand-new-pass-91"}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "authenticated"
    assert c.post("/api/v1/os/auth/invite", {"token": token, "password": "Brand-new-pass-91"}, format="json").status_code == 400


# --- permissions & navigation ----------------------------------------------------------
def _nav_keys(c):
    return {i["key"] for g in c.get("/api/v1/os/me/context").json()["navigation"] for i in g["items"]}


def test_navigation_is_permission_aware(os_seed):
    emp, ceo, admin = _nav_keys(signed_in("divya.patel@click.dev")), _nav_keys(signed_in("ananya.rao@click.dev")), _nav_keys(signed_in("vikram.shah@click.dev"))
    assert {"home", "approvals", "finance"} <= emp and not emp & {"identity", "access", "system", "people"} - {"people"}
    assert "identity" not in emp and "audit" not in emp
    assert {"finance", "partners", "operations", "analytics"} <= ceo and "identity" not in ceo
    assert {"identity", "access", "organization", "system", "audit"} <= admin and "finance" in admin  # admin holds expense *create* (own) only
    assert not load_context(User.objects.get(email="vikram.shah@click.dev")).has("finance.invoice.view")


def test_backend_blocks_what_navigation_hides(os_seed):
    emp = signed_in("divya.patel@click.dev")
    for url in ("/api/v1/os/admin/users", "/api/v1/os/admin/roles", "/api/v1/os/audit", "/api/v1/os/system/health", "/api/v1/os/org/tree"):
        r = emp.get(url)
        assert r.status_code == 403 and r.json()["error"]["code"] == "permission_denied", url
    assert signed_in("vikram.shah@click.dev").get("/api/v1/os/admin/users").status_code == 200


def test_sensitive_permissions_need_mfa_when_enforced(os_seed, settings):
    settings.CLICK_OS_SENSITIVE_REQUIRES_MFA = True
    admin = signed_in("vikram.shah@click.dev")
    r = admin.get("/api/v1/os/admin/users")
    assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_required"
    assert "identity.user.view" in admin.get("/api/v1/os/me/context").json()["mfaBlocked"]


def test_scope_resolution_region_branch_department(os_seed):
    hyd = OrgUnit.objects.get(code="HYD-BR")
    delhi = OrgUnit.objects.get(code="DEL-BR")
    karthik = load_context(User.objects.get(email="karthik.reddy@click.dev"))  # finance-manager @ region, anchored Hyderabad
    assert karthik.can("finance.expense.approve", unit=hyd) and not karthik.can("finance.expense.approve", unit=delhi)
    arjun = load_context(User.objects.get(email="arjun.kumar@click.dev"))  # branch-manager @ branch
    assert arjun.can("people.employee.view", unit=hyd) and not arjun.can("people.employee.view", unit=OrgUnit.objects.get(code="CORP"))


def test_partner_accounts_are_clamped_to_their_partner(os_seed):
    from apps.partners.models import Partner, PartnerCategory, PartnerType

    ptype = PartnerType.objects.first() or PartnerType.objects.create(slug="test-type", name="Test type")
    cat = PartnerCategory.objects.filter(partner_type=ptype).first() or PartnerCategory.objects.create(partner_type=ptype, slug="test-cat", name="Test")
    partner = Partner.objects.create(partner_type=ptype, category=cat, business_name="Test Kitchen")
    user = User.objects.create_user("owner@kitchen.test", PW, full_name="Kitchen Owner")
    from apps.access.models import RoleAssignment

    OSAccount.objects.create(user=user, organization=os_seed, kind="partner", status="active", partner=partner)
    RoleAssignment.objects.create(user=user, role=Role.objects.get(key="partner-business"))
    ctx = load_context(user)
    s = ctx.scope("partners.partner.view")
    assert not s.org_wide and s.partner_ids == {partner.pk}
    keys = _nav_keys(signed_in("owner@kitchen.test", access_type="partner"))
    assert "partners" in keys and "calendar" not in keys and "finance" not in keys


# --- administration safeguards ------------------------------------------------------------
def test_anti_escalation_and_no_self_changes(os_seed):
    admin = signed_in("vikram.shah@click.dev")
    divya = OSAccount.objects.get(user__email="divya.patel@click.dev")
    exec_role = Role.objects.get(key="executive")
    r = admin.post(f"/api/v1/os/admin/users/{divya.pk}/roles", {"roleId": str(exec_role.pk)}, format="json")
    assert r.status_code == 403 and r.json()["error"]["code"] == "escalation_denied"
    me = OSAccount.objects.get(user__email="vikram.shah@click.dev")
    r = admin.post(f"/api/v1/os/admin/users/{me.pk}/roles", {"roleId": str(Role.objects.get(key="employee").pk)}, format="json")
    assert r.status_code == 403
    r = admin.patch(f"/api/v1/os/admin/roles/{exec_role.pk}", {"name": "Hacked"}, format="json")
    assert r.status_code == 403 and r.json()["error"]["code"] == "system_role"
    r = admin.post("/api/v1/os/admin/roles", {"name": "Payroll peek", "grants": [{"code": "people.payroll.view", "scope": "organization"}]}, format="json")
    assert r.status_code == 403


def test_role_revocation_is_immediate(os_seed):
    admin = signed_in("vikram.shah@click.dev")
    karthik = signed_in("karthik.reddy@click.dev")
    assert karthik.get("/api/v1/os/approvals").json()["results"]
    acct = OSAccount.objects.get(user__email="karthik.reddy@click.dev")
    from apps.access.models import RoleAssignment

    a = RoleAssignment.objects.get(user=acct.user, role__key="finance-manager")
    # The admin can't grant finance, but anyone with access.role.assign can remove a role.
    assert admin.delete(f"/api/v1/os/admin/users/{acct.pk}/roles/{a.pk}").status_code == 204
    assert karthik.get("/api/v1/os/approvals").json()["results"] == []


def test_service_accounts_cannot_use_interactive_endpoints(os_seed):
    _, key = ServiceAccount.issue(organization=os_seed, name="ERP sync")
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"ClickKey {key}")
    assert c.get("/api/v1/os/me/context").status_code == 403
    c.credentials(HTTP_AUTHORIZATION="ClickKey nope.nope")
    assert c.get("/api/v1/os/me/context").status_code == 401


def test_org_unit_move_reroots_descendants(os_seed):
    north = OrgUnit.objects.get(code="NORTH")
    tg = OrgUnit.objects.get(code="TG")
    tg.parent = north
    tg.save()
    assert OrgUnit.objects.get(code="HYD-BR").path.startswith(north.path)


def test_audit_is_append_only(os_seed):
    e = AuditEvent.objects.first()
    with pytest.raises(RuntimeError):
        e.save()
    with pytest.raises(RuntimeError):
        e.delete()


def test_sessions_list_and_remote_revoke(os_seed):
    a, b = signed_in("divya.patel@click.dev"), signed_in("divya.patel@click.dev")
    rows = a.get("/api/v1/os/me/sessions").json()["results"]
    assert len(rows) == 2 and sum(r["current"] for r in rows) == 1
    other = next(r for r in rows if not r["current"])
    assert a.delete(f"/api/v1/os/me/sessions/{other['id']}").status_code == 204
    assert b.get("/api/v1/os/me/context").status_code == 401
    assert OSSession.objects.filter(revoked_at__isnull=False).count() == 1
