from django.urls import path

from .views import TicketCatalogueView, TicketSuggestView

app_name = "tickets"

urlpatterns = [
    path("cities/<str:city>/tickets/", TicketCatalogueView.as_view(), name="list"),
    path("cities/<str:city>/tickets/suggest/", TicketSuggestView.as_view(), name="suggest"),
]
