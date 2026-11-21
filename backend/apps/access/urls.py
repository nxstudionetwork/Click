"""/api/v1/os/access/* — Identity & Access workspace (mounted inside the one Business OS surface)."""

from django.urls import path

from . import governance_views as g

urlpatterns = [
    path("nav", g.NavView.as_view(), name="os-access-nav"),
    path("home", g.HomeView.as_view(), name="os-access-home"),
    path("me", g.MyAccessView.as_view(), name="os-access-me"),
    path("effective/<uuid:pk>", g.EffectiveAccessView.as_view(), name="os-access-effective"),
    path("identities/<uuid:pk>", g.IdentityView.as_view(), name="os-access-identity"),
    path("who-has", g.WhoHasView.as_view(), name="os-access-who-has"),
    path("simulate", g.SimulateView.as_view(), name="os-access-simulate"),
    path("compare", g.CompareView.as_view(), name="os-access-compare"),
    path("matrix", g.MatrixView.as_view(), name="os-access-matrix"),
    path("roles/<uuid:pk>/versions", g.RoleVersionsView.as_view(), name="os-access-role-versions"),
    path("packages", g.PackagesView.as_view(), name="os-access-packages"),
    path("packages/<uuid:pk>", g.PackageDetailView.as_view(), name="os-access-package"),
    path("packages/<uuid:pk>/assign", g.PackageAssignView.as_view(), name="os-access-package-assign"),
    path("requests", g.RequestsView.as_view(), name="os-access-requests"),
    path("requestable", g.RequestableView.as_view(), name="os-access-requestable"),
    path("reviews", g.ReviewsView.as_view(), name="os-access-reviews"),
    path("reviews/<uuid:pk>", g.ReviewDetailView.as_view(), name="os-access-review"),
    path("review-items/<uuid:pk>/decide", g.ReviewItemDecideView.as_view(), name="os-access-review-decide"),
    path("sod", g.SoDView.as_view(), name="os-access-sod"),
    path("sod/rules/<uuid:pk>", g.SoDRuleDetailView.as_view(), name="os-access-sod-rule"),
    path("sod/exceptions/<uuid:pk>/revoke", g.SoDExceptionRevokeView.as_view(), name="os-access-sod-exception-revoke"),
    path("emergency", g.EmergencyView.as_view(), name="os-access-emergency"),
    path("emergency/<uuid:pk>/<slug:action>", g.EmergencyActionView.as_view(), name="os-access-emergency-action"),
    path("privileged", g.PrivilegedView.as_view(), name="os-access-privileged"),
    path("hygiene", g.HygieneView.as_view(), name="os-access-hygiene"),
    path("security", g.SecurityEventsView.as_view(), name="os-access-security"),
]
