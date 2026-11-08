"""
Role-based access for the three Click surfaces sharing one API:

  /api/v1/customer/...   -> IsCustomer   (owns a CustomerProfile)
  /api/v1/partner/...    -> IsAuthenticated; partner resolved from the user's owner membership
  /api/v1/os/...         -> (Phase 6) staff + explicit Django permissions

Object ownership is always enforced in querysets, never only in the UI.
"""

from rest_framework.permissions import BasePermission


class IsCustomer(BasePermission):
    message = "A customer account is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and hasattr(user, "customer_profile"))
