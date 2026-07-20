from django.apps import AppConfig


class DistributionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "distribution"
    verbose_name = "Dystrybucja filmowa"

    def ready(self):
        from . import audit_registry, signals  # noqa: F401
