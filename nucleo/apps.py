from django.apps import AppConfig


class NucleoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nucleo"

    def ready(self):
        from nucleo import senales  # noqa: F401
