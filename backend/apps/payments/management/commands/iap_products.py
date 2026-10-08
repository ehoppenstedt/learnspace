"""Prints the consumable In-App Purchase products to create in App Store Connect (CSV)."""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.payments.pricing import product_id_for


class Command(BaseCommand):
    help = "List the App Store consumable products (one per MXN price point) as CSV."

    def handle(self, *args, **opts):
        self.stdout.write("product_id,reference_name,price_mxn")
        for pesos in sorted(settings.IAP_PRICE_POINTS_MXN):
            self.stdout.write(f"{product_id_for(pesos)},Clase en línea ${pesos},{pesos}")
