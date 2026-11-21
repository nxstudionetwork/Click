from django.apps import AppConfig


class GroceriesConfig(AppConfig):
    name = "apps.groceries"
    label = "groceries"
    verbose_name = "Click. Groceries"

    def ready(self) -> None:
        from . import signals  # noqa: F401
