"""
/api/v1/os/* — the one Business OS API surface. Every future module mounts its routes here, on the same
authentication, permission engine, error envelope and pagination (see apps/access/api.py).
"""

from django.urls import path

from apps.access import admin_views as adm
from apps.access import auth_views as auth
from apps.audit import views as audit_views
from apps.organization import views as org
from apps.workflows import views as wf

from . import views as ws

urlpatterns = [
    # Sign-in
    path("auth/identify", auth.IdentifyView.as_view(), name="os-auth-identify"),
    path("auth/password", auth.PasswordView.as_view(), name="os-auth-password"),
    path("auth/mfa", auth.MfaView.as_view(), name="os-auth-mfa"),
    path("auth/refresh", auth.RefreshView.as_view(), name="os-auth-refresh"),
    path("auth/logout", auth.LogoutView.as_view(), name="os-auth-logout"),
    path("auth/logout-all", ws.LogoutAllView.as_view(), name="os-auth-logout-all"),
    path("auth/invite", auth.InviteView.as_view(), name="os-auth-invite"),
    path("auth/dev-personas", auth.DevPersonasView.as_view(), name="os-auth-dev-personas"),
    # Me
    path("me/context", ws.ContextView.as_view(), name="os-me-context"),
    path("me/profile", ws.ProfileView.as_view(), name="os-me-profile"),
    path("me/preferences", ws.PreferencesView.as_view(), name="os-me-preferences"),
    path("me/avatar", ws.AvatarView.as_view(), name="os-me-avatar"),
    path("me/onboarding", ws.OnboardingView.as_view(), name="os-me-onboarding"),
    path("me/password", ws.PasswordView.as_view(), name="os-me-password"),
    path("me/mfa/setup", ws.MfaSetupView.as_view(), name="os-me-mfa-setup"),
    path("me/mfa/confirm", ws.MfaConfirmView.as_view(), name="os-me-mfa-confirm"),
    path("me/mfa/disable", ws.MfaDisableView.as_view(), name="os-me-mfa-disable"),
    path("me/mfa/recovery-codes", ws.RecoveryCodesView.as_view(), name="os-me-recovery-codes"),
    path("me/sessions", ws.SessionsView.as_view(), name="os-me-sessions"),
    path("me/sessions/<uuid:pk>", ws.SessionDetailView.as_view(), name="os-me-session"),
    path("me/activity", ws.MyActivityView.as_view(), name="os-me-activity"),
    # Workspace
    path("home", ws.HomeView.as_view(), name="os-home"),
    path("home/widgets/<slug:key>", ws.WidgetView.as_view(), name="os-home-widget"),
    path("notifications", ws.NotificationsView.as_view(), name="os-notifications"),
    path("notifications/summary", ws.NotificationSummaryView.as_view(), name="os-notifications-summary"),
    path("notifications/read-all", ws.NotificationReadView.as_view(), name="os-notifications-read-all"),
    path("notifications/<uuid:pk>/read", ws.NotificationReadView.as_view(), name="os-notification-read"),
    path("search", ws.SearchView.as_view(), name="os-search"),
    path("calendar", ws.CalendarView.as_view(), name="os-calendar"),
    path("modules", ws.ModulesView.as_view(), name="os-modules"),
    path("modules/<slug:key>", ws.ModuleDetailView.as_view(), name="os-module"),
    path("ai", ws.AIView.as_view(), name="os-ai"),
    path("people/picker", wf.PeoplePickerView.as_view(), name="os-people-picker"),
    path("people/<uuid:pk>", ws.EmployeeView.as_view(), name="os-employee"),
    # Approvals & tasks
    path("approvals", wf.ApprovalsView.as_view(), name="os-approvals"),
    path("approvals/policies", wf.SubmittablePoliciesView.as_view(), name="os-approval-policies"),
    path("approvals/delegations", wf.DelegationsView.as_view(), name="os-delegations"),
    path("approvals/delegations/<uuid:pk>", wf.DelegationDetailView.as_view(), name="os-delegation"),
    path("approvals/<uuid:pk>", wf.ApprovalDetailView.as_view(), name="os-approval"),
    path("approvals/<uuid:pk>/<slug:action>", wf.ApprovalActionView.as_view(), name="os-approval-action"),
    path("tasks", wf.TasksView.as_view(), name="os-tasks"),
    path("tasks/<uuid:pk>", wf.TaskDetailView.as_view(), name="os-task"),
    # Organization
    path("org/tree", org.OrgTreeView.as_view(), name="os-org-tree"),
    path("org/units", org.UnitsView.as_view(), name="os-org-units"),
    path("org/units/<uuid:pk>", org.UnitDetailView.as_view(), name="os-org-unit"),
    path("org/departments", org.DepartmentsView.as_view(), name="os-org-departments"),
    path("org/teams", org.TeamsView.as_view(), name="os-org-teams"),
    # Administration
    path("admin/users", adm.UsersView.as_view(), name="os-admin-users"),
    path("admin/users/<uuid:pk>", adm.UserDetailView.as_view(), name="os-admin-user"),
    path("admin/users/<uuid:pk>/status", adm.UserStatusView.as_view(), name="os-admin-user-status"),
    path("admin/users/<uuid:pk>/roles", adm.UserRolesView.as_view(), name="os-admin-user-roles"),
    path("admin/users/<uuid:pk>/roles/<uuid:assignment_id>", adm.UserRoleDetailView.as_view(), name="os-admin-user-role"),
    path("admin/roles", adm.RolesView.as_view(), name="os-admin-roles"),
    path("admin/roles/<uuid:pk>", adm.RoleDetailView.as_view(), name="os-admin-role"),
    path("admin/roles/<uuid:pk>/duplicate", adm.RoleDuplicateView.as_view(), name="os-admin-role-duplicate"),
    path("admin/permissions", adm.PermissionCatalogView.as_view(), name="os-admin-permissions"),
    path("admin/service-accounts", adm.ServiceAccountsView.as_view(), name="os-admin-service-accounts"),
    path("admin/service-accounts/<uuid:pk>", adm.ServiceAccountDetailView.as_view(), name="os-admin-service-account"),
    path("admin/workflows", wf.PoliciesAdminView.as_view(), name="os-admin-workflows"),
    path("admin/workflows/<uuid:pk>", wf.PolicyAdminDetailView.as_view(), name="os-admin-workflow"),
    path("audit", audit_views.AuditView.as_view(), name="os-audit"),
    path("system/health", ws.SystemHealthView.as_view(), name="os-system-health"),
    path("system/integrations", ws.IntegrationsView.as_view(), name="os-system-integrations"),
]
