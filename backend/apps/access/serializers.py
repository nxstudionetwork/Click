from rest_framework import serializers

from apps.organization.models import Department, OrgUnit, Team

from .models import OSAccount, OSSession, Role, RoleAssignment
from .registry import SCOPES


def avatar_url(account) -> str | None:
    return account.avatar.url if account and account.avatar else None


def session_user_payload(user) -> dict:
    acct = getattr(user, "os_account", None)
    return {"id": str(user.pk), "full_name": user.full_name, "email": user.email, "avatar_url": avatar_url(acct),
            "kind": acct.kind if acct else None}


def unit_brief(u: OrgUnit | None):
    return {"id": str(u.pk), "name": u.name, "code": u.code, "type": u.unit_type, "type_label": u.get_unit_type_display()} if u else None


def dept_brief(d: Department | None):
    return {"id": str(d.pk), "name": d.name, "code": d.code} if d else None


def team_brief(t: Team | None):
    return {"id": str(t.pk), "name": t.name} if t else None


class SessionSerializer(serializers.ModelSerializer):
    current = serializers.SerializerMethodField()

    class Meta:
        model = OSSession
        fields = ["id", "device_label", "ip", "created_at", "last_seen_at", "expires_at", "mfa_verified", "current"]

    def get_current(self, s):
        cur = getattr(self.context.get("request"), "os_session", None)
        return bool(cur and cur.pk == s.pk)


class AssignmentSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    org_unit = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    team = serializers.SerializerMethodField()
    granted_by = serializers.SerializerMethodField()

    class Meta:
        model = RoleAssignment
        fields = ["id", "role", "org_unit", "department", "team", "valid_from", "valid_until", "granted_by", "note", "created_at"]

    def get_role(self, a):
        return {"id": str(a.role_id), "name": a.role.name, "key": a.role.key}

    def get_org_unit(self, a):
        return unit_brief(a.org_unit)

    def get_department(self, a):
        return dept_brief(a.department)

    def get_team(self, a):
        return team_brief(a.team)

    def get_granted_by(self, a):
        return a.granted_by.full_name if a.granted_by else None


class AccountListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name")
    email = serializers.EmailField(source="user.email")
    user_id = serializers.UUIDField(source="user.id")
    employee = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    mfa_enabled = serializers.BooleanField()
    is_locked = serializers.BooleanField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = OSAccount
        fields = ["id", "user_id", "full_name", "email", "kind", "status", "employee", "roles", "mfa_enabled", "is_locked",
                  "last_login_at", "created_at", "avatar_url"]

    def get_employee(self, a):
        e = getattr(a.user, "employee", None)
        if not e:
            return None
        return {"id": str(e.pk), "employee_id": e.employee_id, "designation": e.designation.name if e.designation else None,
                "department": dept_brief(e.department), "org_unit": unit_brief(e.org_unit)}

    def get_roles(self, a):
        return [{"id": str(x.role_id), "name": x.role.name} for x in a.user.role_assignments.all() if x.is_active]

    def get_avatar_url(self, a):
        return avatar_url(a)


class RoleListSerializer(serializers.ModelSerializer):
    permission_count = serializers.IntegerField(read_only=True)
    holder_count = serializers.IntegerField(read_only=True)
    parent = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "key", "name", "description", "audience", "is_system", "requires_mfa", "parent", "priority",
                  "permission_count", "holder_count", "is_active"]

    def get_parent(self, r):
        return {"id": str(r.parent_id), "name": r.parent.name} if r.parent_id else None


class GrantInput(serializers.Serializer):
    code = serializers.CharField()
    scope = serializers.ChoiceField(choices=SCOPES)


class LimitInput(serializers.Serializer):
    approval_type = serializers.CharField()
    max_amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, required=False)
    currency = serializers.CharField(max_length=3, required=False, default="INR")


class RoleWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    key = serializers.SlugField(max_length=60, required=False)
    description = serializers.CharField(max_length=300, required=False, allow_blank=True)
    audience = serializers.ChoiceField(choices=Role.Audience.choices, required=False)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    requires_mfa = serializers.BooleanField(required=False)
    priority = serializers.IntegerField(required=False, min_value=0, max_value=1000)
    home_widgets = serializers.ListField(child=serializers.CharField(), required=False)
    grants = GrantInput(many=True, required=False)
    approval_limits = LimitInput(many=True, required=False)
