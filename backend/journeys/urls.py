from django.urls import path

from .views import JourneySearchView

app_name = "journeys"

urlpatterns = [
    path(
        "cities/<str:city>/journeys/search/",
        JourneySearchView.as_view(),
        name="search",
    ),
]
