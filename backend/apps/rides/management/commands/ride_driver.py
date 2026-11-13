"""
DEVELOPMENT ONLY: act as the driver for a ride, exactly as the Partner App would through the Partner API.

    python manage.py ride_driver latest accept      # nearest offered driver accepts
    python manage.py ride_driver CLK-R-ABC1234 arrived
    python manage.py ride_driver latest start
    python manage.py ride_driver latest complete
Refuses to run unless DEBUG is on. Uses the same services as the real driver endpoints.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.rides import services
from apps.rides.models import Ride, RideStatus

STEPS = {"arrived": RideStatus.DRIVER_ARRIVED, "start": RideStatus.IN_PROGRESS, "complete": RideStatus.COMPLETED}


class Command(BaseCommand):
    help = "DEVELOPMENT ONLY: perform a driver action on a ride (accept|arrived|start|complete)."

    def add_arguments(self, parser):
        parser.add_argument("ride", help="Ride number, or 'latest' for the most recent ride")
        parser.add_argument("action", choices=["accept", *STEPS])

    def handle(self, ride, action, **_):
        if not settings.DEBUG:
            raise CommandError("ride_driver is a development tool and only runs with DJANGO_DEBUG=true.")
        r = Ride.objects.order_by("-created_at").first() if ride == "latest" else Ride.objects.filter(number=ride).first()
        if r is None:
            raise CommandError("Ride not found.")
        if action == "accept":
            offer = r.driver_offers.filter(response="pending").order_by("distance_km").select_related("driver").first()
            if offer is None:
                raise CommandError(f"{r.number} has no pending driver offers (status: {r.status}).")
            r = services.driver_accept(r, offer.driver)
        else:
            if r.driver is None:
                raise CommandError(f"{r.number} has no driver yet.")
            r = services.driver_step(r, r.driver, STEPS[action])
        self.stdout.write(f"{r.number}: {r.status}")
