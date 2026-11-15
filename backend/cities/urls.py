from django.urls import path

from .views import CityDetailView, CityListView, DataSourcesView

app_name = "cities"

urlpatterns = [
    path("data-sources/", DataSourcesView.as_view(), name="data-sources"),
    path("cities/", CityListView.as_view(), name="list"),
    path("cities/<str:city>/", CityDetailView.as_view(), name="detail"),
]
