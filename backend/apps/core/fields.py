from django.db import models

from apps.core import crypto


class EncryptedTextField(models.BinaryField):
    """Stores text encrypted with AES-GCM. Not searchable or orderable by design."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("editable", True)
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        return crypto.decrypt(value)

    def to_python(self, value):
        if value is None or isinstance(value, str):
            return value
        return crypto.decrypt(value)

    def get_prep_value(self, value):
        if value is None or value == "":
            return None
        return crypto.encrypt(str(value))

    def get_db_prep_value(self, value, connection, prepared=False):
        if not prepared:
            value = self.get_prep_value(value)
        return connection.Database.Binary(value) if value is not None else None

    def value_to_string(self, obj):
        return "[encrypted]"

    def formfield(self, **kwargs):
        from django import forms

        return forms.CharField(widget=forms.Textarea, required=not self.blank, **kwargs)
