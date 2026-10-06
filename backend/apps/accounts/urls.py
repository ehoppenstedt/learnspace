from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("auth/otp/request", views.OTPRequestView.as_view()),
    path("auth/otp/verify", views.OTPVerifyView.as_view()),
    path("auth/apple", views.AppleLoginView.as_view()),
    path("auth/google", views.GoogleLoginView.as_view()),
    path("auth/refresh", views.RefreshView.as_view()),
    path("auth/logout", views.LogoutView.as_view()),
    path("me", views.MeView.as_view()),
    path("me/complete-profile", views.CompleteProfileView.as_view()),
    path("me/phone", views.PhoneRequestView.as_view()),
    path("me/phone/verify", views.PhoneVerifyView.as_view()),
    path("me/filters", views.FiltersView.as_view()),
    path("me/interests", views.InterestsView.as_view()),
    path("me/consents", views.ConsentsView.as_view()),
    path("me/consents/<str:purpose>", views.ConsentRevokeView.as_view()),
    path("provider/activate", views.ProviderActivateView.as_view()),
    path("provider/profile", views.ProviderProfileView.as_view()),
    path("provider/verification-docs", views.VerificationDocsView.as_view()),
]
