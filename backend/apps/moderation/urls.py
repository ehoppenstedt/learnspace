from django.urls import path

from apps.moderation import views

urlpatterns = [path("reports", views.ReportsView.as_view())]
