from django.contrib.postgres.operations import CreateExtension, TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    initial = True
    dependencies: list = []
    operations = [CreateExtension("postgis"), TrigramExtension()]
