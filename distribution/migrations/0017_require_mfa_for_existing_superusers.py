from django.conf import settings
from django.db import migrations


def require_mfa_for_superusers(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    SecurityProfile = apps.get_model("distribution", "SecurityProfile")
    SecurityProfile.objects.filter(user_id__in=User.objects.filter(is_superuser=True).values("pk")).update(mfa_required=True)


class Migration(migrations.Migration):
    dependencies = [("distribution", "0016_create_security_profiles")]

    operations = [migrations.RunPython(require_mfa_for_superusers, migrations.RunPython.noop)]
