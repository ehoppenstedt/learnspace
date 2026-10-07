from django.urls import path

from apps.notifications import views

urlpatterns = [
    path("me/devices", views.DevicesView.as_view()),
    path("me/notification-prefs", views.NotificationPrefsView.as_view()),
]
