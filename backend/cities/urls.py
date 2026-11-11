from django.urls import path

from .views import CityDetailView, CityListView

app_name = "cities"

urlpatterns = [
    path("cities/", CityListView.as_view(), name="list"),
    path("cities/<str:city>/", CityDetailView.as_view(), name="detail"),
]
