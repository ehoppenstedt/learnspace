from django.contrib.gis.geos import Point
from django.db import migrations

from apps.catalog.reference_data import CATEGORIES, CDMX_AREAS, STANDARD_POLICY


def load(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Area = apps.get_model("catalog", "Area")
    Policy = apps.get_model("catalog", "CancellationPolicy")
    Rule = apps.get_model("catalog", "CancellationRule")

    for order, (slug, es, en, icon) in enumerate(CATEGORIES):
        Category.objects.update_or_create(
            slug=slug, defaults={"name_es": es, "name_en": en, "icon": icon, "sort_order": order}
        )
    for slug, name, borough, lat, lng in CDMX_AREAS:
        Area.objects.update_or_create(
            slug=slug, defaults={"name": name, "borough": borough, "centroid": Point(lng, lat, srid=4326)}
        )
    data = dict(STANDARD_POLICY)
    rules = data.pop("rules")
    policy, _ = Policy.objects.update_or_create(code=data.pop("code"), defaults={**data, "is_default": True})
    policy.rules.all().delete()
    for applies_to, min_h, max_h, pct, refund_fee in rules:
        Rule.objects.create(
            policy=policy, applies_to=applies_to, min_hours_before=min_h, max_hours_before=max_h,
            listed_refund_pct=pct, refund_fee=refund_fee,
        )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
