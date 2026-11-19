"""
The one base for every Business OS endpoint (today's foundation and every future module).

    class InvoiceListView(OSView):
        permissions = {"GET": "finance.invoice.view", "POST": "finance.invoice.create"}

        def get(self, request):
            scope = self.authz.scope("finance.invoice.view")
            qs = scope.filter(Invoice.objects.all(), unit="org_unit", owner="created_by")
            return self.paginate(qs, InvoiceSerializer)

Authentication (OS session or service key), authorization (permission per method, then scope in the queryset),
camelCase JSON, the error envelope, pagination and throttling all come from here, never re-implemented per page.
"""

from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from apps.core.api.pagination import DefaultPagination

from .authentication import OSJWTAuthentication, ServiceKeyAuthentication
from .authz import AuthContext, context_for


class IsOSPrincipal(BasePermission):
    """An active OS account (session-verified by the authentication class) or a usable service account."""

    message = "Sign in to Click Business OS."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        ctx = context_for(request)
        if ctx.service is not None:
            return bool(getattr(view, "allow_service_accounts", False))
        return ctx.account is not None


class MethodPermission(BasePermission):
    """`view.permissions` maps HTTP method → permission code (any scope). Record-level checks use the scope."""

    message = "You don’t have permission to do this."

    def has_permission(self, request, view):
        code = (getattr(view, "permissions", None) or {}).get(request.method)
        if request.method == "HEAD":
            code = (view.permissions or {}).get("GET")
        if not code:
            return True
        context_for(request).require(code)  # raises with mfa_required / permission_denied
        return True


class OSView(APIView):
    authentication_classes = [OSJWTAuthentication, ServiceKeyAuthentication]
    permission_classes = [IsOSPrincipal, MethodPermission]
    permissions: dict[str, str] = {}
    allow_service_accounts = False

    @property
    def authz(self) -> AuthContext:
        return context_for(self.request)

    def paginate(self, queryset, serializer_class, **ctx):
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        data = serializer_class(page, many=True, context={"request": self.request, **ctx}).data
        return paginator.get_paginated_response(data)
