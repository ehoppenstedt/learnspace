from django.urls import path

from apps.payments import views

urlpatterns = [
    path("webhooks/payments/<str:gateway>", views.webhook),
    path("webhooks/app-store", views.app_store_notification),
    path("bookings/<uuid:pk>/app-store-transaction", views.StoreTransactionView.as_view()),
    path("me/credits", views.CreditsView.as_view()),
    path("dev/app-store/<uuid:booking_id>/simulate", views.dev_simulate_store_purchase),
    path("me/payment-methods", views.PaymentMethodsView.as_view()),
    path("me/payment-methods/<str:pm_id>", views.PaymentMethodDetailView.as_view()),
    path("provider/payments/onboarding", views.OnboardingView.as_view()),
    path("provider/tax-profile", views.TaxProfileView.as_view()),
    path("provider/earnings", views.EarningsView.as_view()),
    path("bookings/<uuid:pk>/receipt", views.BookingReceiptLinkView.as_view()),
    path("provider/statements", views.StatementLinkView.as_view()),
    path("receipts/<str:token>", views.receipt_document),
    path("dev/payments/<uuid:booking_id>/simulate", views.dev_simulate_payment),
    path("dev/onboarding/<str:account_id>/complete", views.dev_complete_onboarding),
]
