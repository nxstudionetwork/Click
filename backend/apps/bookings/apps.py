from django.apps import AppConfig


class BookingsConfig(AppConfig):
    name = "apps.bookings"
    label = "bookings"

    def ready(self):
        from django.db import transaction
        from django.db.models.signals import post_save

        from .models import Event, Show

        def _maybe_notify(event_id):
            from .engagement import notify_booking_open

            event = Event.objects.filter(pk=event_id).first()
            if event is not None:
                notify_booking_open(event)

        def on_show(sender, instance, created, **kwargs):
            # A new bookable showtime opens booking for customers who said they're interested (once each).
            if created and instance.status == Show.Status.SCHEDULED:
                transaction.on_commit(lambda: _maybe_notify(instance.event_id))

        def on_event(sender, instance, **kwargs):
            if instance.status in (Event.Status.NOW_SHOWING, Event.Status.COMING_SOON):
                transaction.on_commit(lambda: _maybe_notify(instance.pk))

        post_save.connect(on_show, sender=Show, dispatch_uid="bookings.interest.on_show")
        post_save.connect(on_event, sender=Event, dispatch_uid="bookings.interest.on_event")
