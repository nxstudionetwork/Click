from django.urls import path

from apps.identity.views import IdentityExchangeView, OtpRequestView, IdentityPartnerSignupView, IdentitySignupView

from . import views

urlpatterns = [
    path("auth/otp/request", OtpRequestView.as_view(), name="auth-otp-request"),
    path("auth/identity/exchange", IdentityExchangeView.as_view(), name="auth-identity-exchange"),
    path("auth/identity/signup", IdentitySignupView.as_view(), name="auth-identity-signup"),
    path("auth/identity/partner-signup", IdentityPartnerSignupView.as_view(), name="auth-identity-partner-signup"),
    path("auth/register", views.RegisterView.as_view(), name="auth-register"),
    path("auth/login", views.LoginView.as_view(), name="auth-login"),
    path("auth/refresh", views.RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/dev-login", views.DevLoginView.as_view(), name="auth-dev-login"),  # 404 unless DEBUG
    path("me", views.MeView.as_view(), name="me"),
    path("me/avatar", views.AvatarView.as_view(), name="me-avatar"),
]
