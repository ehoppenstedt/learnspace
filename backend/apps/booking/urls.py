from django.urls import path

from apps.booking import views

urlpatterns = [
    path("holds", views.HoldsView.as_view()),
    path("holds/<uuid:pk>", views.HoldDetailView.as_view()),
    path("bookings", views.BookingsView.as_view()),
    path("bookings/<uuid:pk>", views.BookingDetailView.as_view()),
    path("bookings/<uuid:pk>/cancellation-quote", views.CancellationQuoteView.as_view()),
    path("bookings/<uuid:pk>/cancel", views.CancelView.as_view()),
    path("bookings/<uuid:pk>/dispute-no-show", views.DisputeNoShowView.as_view()),
    path("calendar/<str:token>.ics", views.CalendarView.as_view()),
    path("provider/sessions/<uuid:pk>/roster", views.RosterView.as_view()),
    path("provider/sessions/<uuid:pk>/attendance", views.AttendanceView.as_view()),
    path("provider/sessions/<uuid:pk>/cancel", views.ProviderCancelSessionView.as_view()),
    path("provider/cohorts/<uuid:pk>/cancel", views.ProviderCancelCohortView.as_view()),
    path("provider/bookings", views.ProviderBookingsView.as_view()),
    path("provider/bookings/<uuid:pk>/<str:decision>", views.ProviderBookingDecisionView.as_view()),
]
