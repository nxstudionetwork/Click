from django.apps import AppConfig


class StreamingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.streaming"
    label = "streaming"
    verbose_name = "Click. Live (series, films and live streams)"
