"""GET / PATCH /customer/preferences {language, personalized} — stored on the account so they follow the customer."""

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from .models import CustomerProfile

LANGUAGES = [{"code": c, "label": l} for c, l in CustomerProfile._meta.get_field("language").choices]


class PreferencesInput(serializers.Serializer):
    language = serializers.ChoiceField(choices=[x["code"] for x in LANGUAGES], required=False)
    personalized = serializers.BooleanField(required=False)


class PreferencesView(APIView):
    permission_classes = [IsCustomer]

    def _out(self, c):
        return {"language": c.language, "personalized": c.personalized, "languages": LANGUAGES}

    def get(self, request):
        return Response(self._out(request.user.customer_profile))

    def patch(self, request):
        s = PreferencesInput(data=request.data)
        s.is_valid(raise_exception=True)
        c = request.user.customer_profile
        for k, v in s.validated_data.items():
            setattr(c, k, v)
        c.save(update_fields=[*s.validated_data.keys(), "updated_at"])
        if s.validated_data.get("personalized") is False:
            c.search_history.all().delete()  # turning it off also forgets what we kept for it
        return Response(self._out(c))
