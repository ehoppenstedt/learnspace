from django.urls import path

from apps.messaging import views

urlpatterns = [
    path("threads", views.ThreadsView.as_view()),
    path("threads/unread", views.UnreadCountView.as_view()),
    path("threads/<uuid:pk>/messages", views.ThreadMessagesView.as_view()),
]
