from django.db import migrations


def load(apps, schema_editor):
    FeeConfig = apps.get_model("payments", "FeeConfig")
    if not FeeConfig.objects.exists():
        FeeConfig.objects.create(fee_bps=500, note="Launch fee: 5% (IVA included)")


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
