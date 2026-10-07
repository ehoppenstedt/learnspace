from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import totp
from apps.accounts.models import AdminTOTPDevice, User


class Command(BaseCommand):
    help = "Enroll a staff user in admin 2FA. Step 1: no --code (prints secret). Step 2: --code from the app to confirm."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--code", help="Current 6-digit code from the authenticator app")
        parser.add_argument("--reset", action="store_true", help="Discard the existing device and start over")

    def handle(self, email, code=None, reset=False, **opts):
        user = User.objects.filter(email=email.lower(), is_staff=True).first()
        if user is None:
            raise CommandError("No staff user with that email.")
        device = AdminTOTPDevice.objects.filter(user=user).first()
        if reset and device:
            device.delete()
            device = None
        if device is None:
            device = AdminTOTPDevice.objects.create(user=user, secret=totp.generate_secret())
        if code:
            step = totp.verify(device.secret, code, device.last_used_step)
            if step is None:
                raise CommandError("Code does not match. Check the phone's clock and try again.")
            device.confirmed, device.last_used_step = True, step
            device.save()
            self.stdout.write(self.style.SUCCESS("2FA confirmed. The next admin login will ask for the code."))
            return
        self.stdout.write("Add this to Google Authenticator / 1Password / Authy (manual entry or as a QR code):")
        self.stdout.write(f"  secret: {device.secret}")
        self.stdout.write(f"  uri:    {totp.provisioning_uri(device.secret, email, settings.BRAND_NAME + ' admin')}")
        self.stdout.write(f"Then run: python manage.py enable_admin_2fa {email} --code <6 digits>")
