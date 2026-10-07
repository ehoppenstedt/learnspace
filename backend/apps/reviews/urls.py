from django.urls import path

from apps.reviews import views

urlpatterns = [
    path("experiences/<uuid:pk>/reviews", views.ExperienceReviewsView.as_view()),
    path("bookings/<uuid:pk>/review", views.BookingReviewView.as_view()),
    path("provider/bookings/<uuid:pk>/conduct-rating", views.ConductRatingView.as_view()),
    path("provider/reviews", views.ProviderReviewsView.as_view()),
    path("me/reviews/pending", views.PendingView.as_view()),
    path("me/conduct", views.MyConductView.as_view()),
    path("me/conduct/<uuid:pk>/appeal", views.AppealView.as_view()),
]
