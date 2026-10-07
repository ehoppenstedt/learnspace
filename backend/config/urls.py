from django.contrib import admin
from django.urls import include, path

from apps.accounts.admin_auth import OTPAdminAuthenticationForm
from apps.catalog.views import local_media
from apps.core.views import health

admin.site.login_form = OTPAdminAuthenticationForm
admin.site.site_header = "learnspace admin"
admin.site.site_title = "learnspace admin"
admin.site.index_title = "Operación"

urlpatterns = [
    path("healthz", health),
    path("admin/", admin.site.urls),
    path("media-local/<str:action>", local_media),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.catalog.urls")),
    # Before booking: its provider/bookings/<pk>/<decision> route would swallow conduct-rating.
    path("api/v1/", include("apps.reviews.urls")),
    path("api/v1/", include("apps.booking.urls")),
    path("api/v1/", include("apps.payments.urls")),
    path("api/v1/", include("apps.notifications.urls")),
    path("api/v1/", include("apps.messaging.urls")),
    path("api/v1/", include("apps.moderation.urls")),
]
