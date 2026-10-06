from django import forms
from django.conf import settings
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError

from apps.accounts import totp
from apps.accounts.models import AdminTOTPDevice


class OTPAdminAuthenticationForm(AdminAuthenticationForm):
    """Password + authenticator code. Staff without a confirmed device are refused when 2FA is required."""

    otp = forms.CharField(label="Código de verificación (2FA)", required=False, max_length=6,
                          widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}))

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        device = AdminTOTPDevice.objects.filter(user=user, confirmed=True).first()
        if device is None:
            if settings.ADMIN_REQUIRE_2FA:
                raise ValidationError("Esta cuenta necesita 2FA. Pide que ejecuten: manage.py enable_admin_2fa", code="2fa_required")
            return
        step = totp.verify(device.secret, self.cleaned_data.get("otp", ""), device.last_used_step)
        if step is None:
            raise ValidationError("Código 2FA inválido.", code="2fa_invalid")
        AdminTOTPDevice.objects.filter(pk=device.pk).update(last_used_step=step)
