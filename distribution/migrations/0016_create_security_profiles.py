from django.conf import settings
from django.db import migrations


def create_security_profiles(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    SecurityProfile = apps.get_model("distribution", "SecurityProfile")
    existing = set(SecurityProfile.objects.values_list("user_id", flat=True))
    SecurityProfile.objects.bulk_create(
        [SecurityProfile(user_id=user_id) for user_id in User.objects.exclude(pk__in=existing).values_list("pk", flat=True)],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [("distribution", "0015_securityprofile_auditevent_loginevent")]

    operations = [migrations.RunPython(create_security_profiles, migrations.RunPython.noop)]
