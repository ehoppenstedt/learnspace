from django.db import migrations
from django.utils import timezone


def load(apps, schema_editor):
    FeeConfig = apps.get_model("payments", "FeeConfig")
    FeeConfig.objects.create(fee_bps=1000, effective_from=timezone.now(), note="Launch fee: 10% (IVA included). Decided 2026-10-06.")


class Migration(migrations.Migration):
    dependencies = [("payments", "0003_providertaxprofile_withholdingconfig_payment_and_more")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
