from django.urls import path

from .views import (
    LineListView,
    LineRouteView,
    StopDeparturesView,
    StopSearchView,
    StopTimetableView,
    TripView,
)

app_name = "timetable"

# Ids are `{feed_id}:{gtfs_id}` and GTFS ids may contain "/" (sent URL-encoded as %2F, which
# arrives decoded), so id segments use the `path` converter. `path` is greedy, but Django's
# regex backtracks to the fixed suffix (`/route/`, `/stops/.../timetable/`), so ids work as
# long as they do not themselves contain `/stops/` followed by `/timetable/`.
urlpatterns = [
    path("cities/<str:city>/lines/", LineListView.as_view(), name="lines"),
    path(
        "cities/<str:city>/lines/<path:line_id>/route/",
        LineRouteView.as_view(),
        name="line-route",
    ),
    path(
        "cities/<str:city>/lines/<path:line_id>/stops/<path:stop_id>/timetable/",
        StopTimetableView.as_view(),
        name="stop-timetable",
    ),
    path("cities/<str:city>/trips/<path:trip_id>/", TripView.as_view(), name="trip"),
    path("cities/<str:city>/stops/", StopSearchView.as_view(), name="stops"),
    path(
        "cities/<str:city>/stops/<path:stop_id>/departures/",
        StopDeparturesView.as_view(),
        name="stop-departures",
    ),
]
