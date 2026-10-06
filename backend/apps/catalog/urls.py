from django.urls import path

from apps.catalog import views

urlpatterns = [
    path("config", views.ConfigView.as_view()),
    path("geo/areas", views.AreasView.as_view()),
    path("experiences", views.FeedView.as_view()),
    path("experiences/map", views.MapView.as_view()),
    path("experiences/<uuid:pk>", views.ExperienceDetailView.as_view()),
    path("providers/<uuid:pk>", views.ProviderPublicView.as_view()),
    path("spaces/<uuid:pk>", views.SpacePublicView.as_view()),
    path("media/uploads", views.MediaUploadView.as_view()),
    path("media/<uuid:pk>", views.MediaStatusView.as_view()),
    path("media/<uuid:pk>/complete", views.MediaCompleteView.as_view()),
    path("provider/spaces", views.ProviderSpacesView.as_view()),
    path("provider/spaces/<uuid:pk>", views.ProviderSpaceDetailView.as_view()),
    path("provider/experiences", views.ProviderExperiencesView.as_view()),
    path("provider/experiences/<uuid:pk>", views.ProviderExperienceDetailView.as_view()),
    path("provider/experiences/<uuid:pk>/sessions", views.ProviderSessionsView.as_view()),
    path("provider/experiences/<uuid:pk>/<str:action>", views.ProviderExperienceActionView.as_view()),
    path("provider/sessions/<uuid:pk>", views.ProviderSessionDetailView.as_view()),
]
