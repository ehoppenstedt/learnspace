from django.urls import path

from apps.payments import views

urlpatterns = [
    path("webhooks/payments/<str:gateway>", views.webhook),
    path("me/payment-methods", views.PaymentMethodsView.as_view()),
    path("me/payment-methods/<str:pm_id>", views.PaymentMethodDetailView.as_view()),
    path("provider/payments/onboarding", views.OnboardingView.as_view()),
    path("provider/tax-profile", views.TaxProfileView.as_view()),
    path("provider/earnings", views.EarningsView.as_view()),
    path("dev/payments/<uuid:booking_id>/simulate", views.dev_simulate_payment),
    path("dev/onboarding/<str:account_id>/complete", views.dev_complete_onboarding),
]
