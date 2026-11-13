"""GET /customer/activity?category=&q=&status=ok|bad|pending&cursor= — the customer's own Click. timeline (scoped server side)."""

from datetime import datetime

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from .timeline import timeline


class ActivityView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        qp = request.query_params
        before = timezone.now()
        if qp.get("cursor"):
            try:
                before = datetime.fromisoformat(qp["cursor"])
            except ValueError:
                raise DomainError("Invalid cursor.", code="validation_error")
        return Response(timeline(request.user.customer_profile, qp.get("category"), before, (qp.get("q") or "").strip()[:60], qp.get("status") or ""))
